"""The /api/v2 service layer: plain functions over a V2 context. Routes are thin wrappers around these (spec 8)."""

from __future__ import annotations

import base64
import json
import uuid
from fractions import Fraction
from typing import Any, Optional

from open_apprentice.api.v2 import records
from open_apprentice.api.v2.context import V2
from open_apprentice.drawio import mapping as mp
from open_apprentice.drawio.classify import Classified, classify
from open_apprentice.drawio.parse import DrawioFile, DrawioRefused, load_drawio
from open_apprentice.drawio.patch import apply_edits, plan_edits
from open_apprentice.drawio.render import Rendered, parse_render
from open_apprentice.drawio.scene import DrawioScene, build_scene
from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import scene_from_payload


class Conflict(Exception):
    """A request that cannot apply to the resource's current state (409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _s(v: Fraction) -> str:
    return str(v)


def scene_digest(scene: dict) -> str:
    """The same normalisation the event log uses for registered scenes."""
    return codec.digest(scene_from_payload(codec.loads(codec.dumps(scene))))


# ---- documents ---------------------------------------------------------------------------------------------------------


def _doc_key(doc_id: str) -> str:
    return f"documents/{doc_id}.json"


def _page_key(doc_id: str, page_id: str, name: str) -> str:
    return f"documents/{doc_id}/pages/{page_id}/{name}"


def _source(v: V2, doc_id: str) -> DrawioFile:
    b = v.store.get(f"documents/{doc_id}/source.drawio")
    if b is None:
        raise records.NotFound(doc_id)
    return load_drawio(b.data)


def import_document(v: V2, owner: str, name: str, raw: bytes) -> dict:
    f = load_drawio(raw)  # whole-file refusals raise DrawioRefused
    doc_id = uuid.uuid4().hex
    pages = []
    for p in f.pages:
        entry: dict[str, Any] = {"page_id": p.id, "index": p.index, "name": p.name}
        try:
            c = classify(p)
            entry.update(
                status="ok", movable=list(c.movable), fixed=list(c.fixed), reasons=c.reasons
            )
        except DrawioRefused as e:
            entry.update(status="refused", reason=str(e))
        pages.append(entry)
    v.store.create(f"documents/{doc_id}/source.drawio", raw)
    body = {
        "doc_id": doc_id,
        "name": name[:200],
        "doc_hash": f.doc_hash,
        "pages": pages,
        "render": "pending",
    }
    records.put_new(v.store, _doc_key(doc_id), owner, body)
    v.dispatcher.submit(f"render:{doc_id}", lambda: render_document(v, owner, doc_id))
    return body


def _render_json(r: Rendered) -> dict:
    def box(b: Any) -> dict:
        return {"x": _s(b.x), "y": _s(b.y), "w": _s(b.w), "h": _s(b.h)}

    return {
        "labels": {k: {"box": box(b), "lines": n} for k, (b, n) in r.labels.items()},
        "nodes": {
            k: {"state": box(s), "element": box(e) if e is not None else None, "stroke": _s(st)}
            for k, (s, e, st) in r.nodes.items()
        },
        "missing": list(r.missing),
        "profile": r.profile,
    }


def render_document(v: V2, owner: str, doc_id: str) -> None:
    doc, _ = records.load(v.store, _doc_key(doc_id), owner)
    f = _source(v, doc_id)
    try:
        for entry in doc["pages"]:
            if entry["status"] != "ok":
                continue
            page = next(p for p in f.pages if p.id == entry["page_id"])
            r = v.render(page)
            v.store.put(
                _page_key(doc_id, page.id, "render.json"),
                records.dumps(_render_json(r)),
                if_generation=None,
            )
            if r.png is not None:
                v.store.put(_page_key(doc_id, page.id, "preview.png"), r.png, if_generation=None)
            m = mp.propose(classify(page), r, f.doc_hash)
            v.store.put(
                _page_key(doc_id, page.id, "mapping.json"),
                records.dumps(mp.to_json(m)),
                if_generation=None,
            )
    except DrawioRefused as e:
        reason = str(e)
        records.update(
            v.store,
            _doc_key(doc_id),
            owner,
            lambda d: {**d, "render": "failed", "render_error": reason},
        )
        return
    records.update(v.store, _doc_key(doc_id), owner, lambda d: {**d, "render": "done"})


def _stored_render(v: V2, doc_id: str, page_id: str) -> Rendered:
    b = v.store.get(_page_key(doc_id, page_id, "render.json"))
    if b is None:
        raise Conflict("NOT_RENDERED", "this page has not been rendered yet")
    return parse_render(json.loads(b.data))


def _stored_mapping(v: V2, doc_id: str, page_id: str) -> tuple[mp.Mapping, int]:
    b = v.store.get(_page_key(doc_id, page_id, "mapping.json"))
    if b is None:
        raise Conflict("NOT_RENDERED", "this page has not been rendered yet")
    return mp.from_json(json.loads(b.data)), b.generation


def _page_entry(doc: dict, page_id: str) -> dict:
    entry = next((p for p in doc["pages"] if p["page_id"] == page_id), None)
    if entry is None:
        raise records.NotFound(page_id)
    if entry["status"] != "ok":
        raise Conflict("PAGE_REFUSED", entry.get("reason", "this page is not supported"))
    return entry


def get_document(v: V2, owner: str, doc_id: str) -> dict:
    doc, _ = records.load(v.store, _doc_key(doc_id), owner)
    out = {k: doc[k] for k in ("doc_id", "name", "doc_hash", "render")}
    if "render_error" in doc:
        out["render_error"] = doc["render_error"]
    pages = []
    for entry in doc["pages"]:
        p = dict(entry)
        p.update(mapping=None, mapping_hash=None, scene_hash=None)
        if entry["status"] == "ok" and doc["render"] == "done":
            m, _ = _stored_mapping(v, doc_id, entry["page_id"])
            p["mapping"] = {
                "labels": m.labels,
                "proposed": sorted(m.proposed),
                "confirmed": m.confirmed_by_event is not None,
            }
            if m.confirmed_by_event is not None:
                p["mapping_hash"] = mp.digest(m)
                p["scene_hash"] = scene_digest(
                    page_scene(v, owner, doc_id, entry["page_id"], p["mapping_hash"])[3].scene
                )
        pages.append(p)
    out["pages"] = pages
    return out


def preview_png(v: V2, owner: str, doc_id: str, page_id: str) -> bytes:
    doc, _ = records.load(v.store, _doc_key(doc_id), owner)
    _page_entry(doc, page_id)
    b = v.store.get(_page_key(doc_id, page_id, "preview.png"))
    if b is None:
        raise Conflict("NOT_RENDERED", "no preview for this page yet")
    return b.data


def save_mapping(
    v: V2, owner: str, doc_id: str, page_id: str, edits: dict[str, dict], confirm: bool
) -> dict:
    doc, _ = records.load(v.store, _doc_key(doc_id), owner)
    _page_entry(doc, page_id)
    m, gen = _stored_mapping(v, doc_id, page_id)
    nodes = frozenset(n for n in classify_page(v, doc_id, page_id).fixed)
    for cell, e in edits.items():
        try:
            m = mp.edit(m, cell, node_id=e.get("node_id"), role=e.get("role"), nodes=nodes)
        except ValueError as err:
            raise Conflict("BAD_MAPPING", str(err)) from err
    if confirm:
        m = mp.confirm(m, f"mapping-{uuid.uuid4().hex}")
    v.store.put(
        _page_key(doc_id, page_id, "mapping.json"), records.dumps(mp.to_json(m)), if_generation=gen
    )
    return {
        "mapping_hash": mp.digest(m) if m.confirmed_by_event else None,
        "confirmed": m.confirmed_by_event is not None,
        "labels": m.labels,
    }


def classify_page(v: V2, doc_id: str, page_id: str) -> Classified:
    f = _source(v, doc_id)
    page = next((p for p in f.pages if p.id == page_id), None)
    if page is None:
        raise records.NotFound(page_id)
    return classify(page)


def page_scene(
    v: V2, owner: str, doc_id: str, page_id: str, mapping_hash: str
) -> tuple[DrawioFile, int, Classified, DrawioScene]:
    doc, _ = records.load(v.store, _doc_key(doc_id), owner)
    _page_entry(doc, page_id)
    f = _source(v, doc_id)
    page = next(p for p in f.pages if p.id == page_id)
    c = classify(page)
    r = _stored_render(v, doc_id, page_id)
    m, _ = _stored_mapping(v, doc_id, page_id)
    if m.confirmed_by_event is None or mp.digest(m) != mapping_hash:
        raise Conflict(
            "STALE_MAPPING", "the label mapping changed or is not confirmed; confirm it again"
        )
    scene = build_scene(c, r, mp.as_scene_mapping(m, f.doc_hash, page.id, c.movable), f.doc_hash)
    return f, page.index, c, scene


def _boxes(raw: dict[str, Any]) -> dict[str, tuple[Fraction, Fraction]]:
    try:
        return {k: (Fraction(str(v[0])), Fraction(str(v[1]))) for k, v in raw.items()}
    except (ValueError, TypeError, IndexError, ZeroDivisionError) as e:
        raise Conflict("BAD_BOXES", f"label positions must be [x, y] numbers ({e})") from e


def draft_render(
    v: V2, owner: str, doc_id: str, page_id: str, mapping_hash: str, raw_boxes: dict
) -> dict:
    """A deterministic render of the document with labels at the given boxes (no model, nothing stored), spec 8."""
    f, idx, _, scene = page_scene(v, owner, doc_id, page_id, mapping_hash)
    boxes = _boxes(raw_boxes)
    unknown = sorted(set(boxes) - set(scene.movable))
    if unknown:
        raise Conflict("NOT_MOVABLE", f"these labels cannot be moved: {unknown}")
    new = apply_edits(f, idx, plan_edits(f.pages[idx], scene.offsets, boxes), f.doc_hash)
    page = load_drawio(new).pages[idx]
    r = v.render(page)
    return {
        "png": base64.b64encode(r.png).decode() if r.png else None,
        "boxes": {
            k: {"x": _s(b.x), "y": _s(b.y), "w": _s(b.w), "h": _s(b.h)}
            for k, (b, _) in r.labels.items()
        },
    }


# ---- teaching sessions ---------------------------------------------------------------------------------------------------

LIVE_UNAVAILABLE = "Live inference is unavailable. Open the recorded example."


class LiveUnavailable(Conflict):
    def __init__(self) -> None:
        super().__init__("LIVE_UNAVAILABLE", LIVE_UNAVAILABLE)


class _Deferred:
    """The teacher for API sessions: a person answers later through POST /responses."""

    def ask(self, req: Any) -> None:
        return None


def _meta_key(sid: str) -> str:
    return f"sessions/{sid}/meta.json"


def _digest(body: dict) -> str:
    return codec.digest(body)


def _scene_id(ref: dict) -> str:
    return f"{ref['doc_id']}:{ref['page_id']}"


def create_session(
    v: V2,
    owner: str,
    documents: list[dict],
    demonstrations: list[dict],
    live: bool,
    idempotency_key: str,
) -> dict:
    body = {"documents": documents, "demonstrations": demonstrations, "live": live}
    return records.idempotent(
        v.store,
        owner,
        f"session:{idempotency_key}",
        _digest(body),
        lambda: _create_session(v, owner, documents, demonstrations, live),
    )


def _create_session(
    v: V2, owner: str, documents: list[dict], demonstrations: list[dict], live: bool
) -> dict:
    from open_apprentice.teaching.events import SessionLog

    if live and not v.live_available():
        raise LiveUnavailable()
    if not documents or not demonstrations:
        raise Conflict("BAD_REQUEST", "a session needs at least one document and one demonstration")
    scenes = []
    for ref in documents:
        _, _, _, sc = page_scene(v, owner, ref["doc_id"], ref["page_id"], ref["mapping_hash"])
        scenes.append(sc)
    demo_outputs: dict[int, dict] = {}
    for d in demonstrations:
        i = d.get("document_ref")
        if not isinstance(i, int) or not 0 <= i < len(scenes):
            raise Conflict("BAD_REQUEST", "document_ref must index the documents list")
        sc = scenes[i]
        if d.get("before_scene_hash") != scene_digest(sc.scene):
            raise Conflict(
                "STALE", "the document changed since this demonstration was made; reload it"
            )
        boxes = _boxes(d.get("boxes", {}))
        unknown = sorted(set(boxes) - set(sc.movable))
        if unknown:
            raise Conflict("NOT_MOVABLE", f"these labels cannot be moved: {unknown}")
        labels = {o["id"]: (o["x"], o["y"]) for o in sc.scene["objects"] if o["id"] in sc.movable}
        demo_outputs[i] = {**labels, **boxes}  # the whole document is approved as shown
    if len(demo_outputs) == len(scenes):
        # the step policy only commits after a preview on a document the user did not demonstrate (spec 4 rule 6)
        raise Conflict(
            "NEED_BATCH",
            "add at least one more document that you did not edit, so the learned rule can be previewed on it",
        )
    sid = uuid.uuid4().hex
    log = SessionLog(v.store, sid)
    log.create(owner=owner)
    for i, (ref, sc) in enumerate(zip(documents, scenes)):
        log.append(
            "SceneRegistered",
            "system",
            {
                "scene_id": _scene_id(ref),
                "scene_hash": scene_digest(sc.scene),
                "scene": codec.loads(codec.dumps(sc.scene)),
                "role": "demo" if i in demo_outputs else "batch",
            },
        )
        log.append(
            "MappingRecorded", "human", {k: ref[k] for k in ("doc_id", "page_id", "mapping_hash")}
        )
    for i, out in demo_outputs.items():
        log.append(
            "DemonstrationRecorded",
            "human",
            {
                "scene_id": _scene_id(documents[i]),
                "output": codec.loads(codec.dumps({k: list(p) for k, p in out.items()})),
            },
        )
    meta = {
        "sid": sid,
        "kind": "teaching",
        "skill_id": f"sk-{uuid.uuid4().hex}",
        "documents": documents,
        "model": v.model if live else "Fixture",
        "teacher": "You",
        "live": live,
    }
    records.put_new(v.store, _meta_key(sid), owner, meta)
    v.dispatcher.submit(sid, lambda: advance(v, sid))
    return {"session_id": sid, "operation": "advance", "status_url": f"/api/v2/sessions/{sid}"}


def _raw_meta(v: V2, sid: str) -> dict:
    b = v.store.get(_meta_key(sid))
    if b is None:
        raise records.NotFound(sid)
    return json.loads(b.data)


def advance(v: V2, sid: str) -> None:
    """Run the session's executor until it needs a person, a result, or ends; activate a new skill's first version."""
    from open_apprentice.skills.versions import ActivationRejected, SkillStore
    from open_apprentice.teaching.events import SessionLog
    from open_apprentice.teaching.executor import Executor
    from open_apprentice.teaching.step import StepConfig

    meta = _raw_meta(v, sid)
    log = SessionLog(v.store, sid)
    if meta["kind"] != "teaching":
        return advance_correction(v, sid)
    status = Executor(
        v.store, log, v.proposer if meta["live"] else _offline(v), _Deferred(), v.ledger,
        StepConfig(), worst_usd=v.worst_usd if meta["live"] else Fraction(0), skill_id=meta["skill_id"],
    ).run()  # fmt: skip
    if status != "committed":
        return
    evs = log.events()
    if any(e.type in ("VersionActivated", "ActivationRejected") for e in evs):
        return
    version = next(e.payload["version"] for e in evs if e.type == "VersionStored")
    try:
        records.put_new(
            v.store, f"skills/{meta['skill_id']}/owner.json", log.manifest()[0]["owner"], {}
        )
    except FileExistsError:
        pass
    try:
        rid = SkillStore(v.store).activate(meta["skill_id"], version, None, sid, sid)
    except ActivationRejected as e:
        log.append(
            "ActivationRejected",
            "system",
            {"action_id": sid, "reason": str(e), "stored_version": version},
        )
        return
    log.append(
        "VersionActivated",
        "system",
        {"operation_id": sid, "from": None, "to": version, "record_id": rid},
    )


def _offline(v: V2) -> Any:
    from open_apprentice.concepts.label_enumerative import LabelEnumerator

    return v.proposer if v.model == "Fixture" else LabelEnumerator()


def advance_correction(v: V2, sid: str) -> None:  # completed in Task 8
    raise NotImplementedError


def _open_request(evs: list) -> tuple[Optional[dict], Optional[str]]:
    from open_apprentice.teaching.teacher import response_from_json

    answered = {
        response_from_json(e.payload["response"]).request_id
        for e in evs
        if e.type == "ResponseRecorded"
    }
    for e in evs:
        if e.type == "RequestIssued" and e.payload["request"]["request_id"] not in answered:
            return e.payload["request"], e.payload["action_id"]
    return None, None


def _approve_all(req: dict) -> dict:
    t = req["type"]
    if t == "ChooseOutput":
        return {"kind": "choose", "selected": req["alternatives"][0][0]}
    if t == "ConfirmPreview":
        return {"kind": "items", "per_item": [[it[0], "approve"] for it in req["items"]]}
    if t == "ConfirmCorrectionScope":
        first = next(
            (i["interp_id"] for i in req["interpretations"] if i["kind"] == "revise"), "ov"
        )
        return {"kind": "select", "selected": first}
    return {"kind": "cancel"}


def session_state(v: V2, owner: str, sid: str) -> dict:
    from open_apprentice.teaching.events import SessionLog

    meta, _ = records.load(v.store, _meta_key(sid), owner)
    log = SessionLog(v.store, sid)
    manifest, _ = log.manifest()
    evs = log.events()
    types = [e.type for e in evs]
    req, _ = _open_request(evs)
    issued = {
        e.payload["action_id"]
        for e in evs
        if e.type == "ActionIssued" and e.payload.get("kind") == "RequestModelProposal"
    }
    resolved = {
        e.payload.get("action_id")
        for e in evs
        if e.type in ("ModelProposalReturned", "ModelCallFailed")
    }
    abstain = next((e.payload for e in evs if e.type == "Abstained"), None)
    error = next((e.payload for e in evs if e.type == "Errored"), None)
    result: dict[str, Any] = {}
    if meta["kind"] == "correction":
        state = _correction_state(types, req, issued - resolved, abstain, error)
    elif abstain is not None:
        state = "cancelled" if abstain.get("reason") == CANCELLED else "failed"
        result = {"reason": abstain.get("reason")}
    elif error is not None:
        state, result = "failed", {"reason": error.get("reason")}
    elif "VersionStored" in types:
        state = "committed"
        stored = next(e.payload for e in evs if e.type == "VersionStored")
        result = {
            "skill_id": meta["skill_id"],
            "version": stored["version"],
            "activated": "VersionActivated" in types,
        }
    elif req is not None:
        state = "preview_ready" if req["type"] == "ConfirmPreview" else "waiting_for_answer"
    elif issued - resolved:
        state = "waiting_for_model"
    else:
        state = "teaching"
    action_ids = {e.payload["action_id"] for e in evs if e.type == "ActionIssued"}
    spend = v.ledger.exposure(action_ids)
    outstanding = None
    if req is not None and state in ("waiting_for_answer", "preview_ready", "review"):
        outstanding = {
            "request_id": req["request_id"],
            "intent_revision": manifest["intent_revision"],
            "request": req,
            "approve_all_answer": _approve_all(req),
        }
    return {
        "session_id": sid,
        "kind": meta["kind"],
        "state": state,
        "outstanding": outstanding,
        "budgets": {
            "choose_used": sum(
                1
                for e in evs
                if e.type == "RequestIssued" and e.payload["request"]["type"] == "ChooseOutput"
            ),
            "previews_used": sum(
                1
                for e in evs
                if e.type == "RequestIssued" and e.payload["request"]["type"] == "ConfirmPreview"
            ),
            "attempts_used": len(issued)
            + sum(1 for e in evs if e.type == "ModelCallFailed" and not e.payload.get("terminal")),
        },
        "spend": {
            "recorded": _s(spend["settled"]),
            "reserved": _s(spend["reserved"]),
            "uncertain": _s(spend["uncertain"]),
        },
        "manifest_revision": manifest["manifest_revision"],
        "provenance": {"model": meta["model"], "teacher": meta["teacher"]},
        "result": result,
    }


CANCELLED = "cancelled by the user"


def _correction_state(
    types: list, req: Optional[dict], waiting_model: set, abstain: Any, error: Any
) -> str:  # Task 8
    return "draft"
