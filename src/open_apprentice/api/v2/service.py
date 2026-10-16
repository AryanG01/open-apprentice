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
        "translate": {"x": _s(r.translate[0]), "y": _s(r.translate[1])},
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
    if "probe_of" in doc:
        out["probe_of"] = doc["probe_of"]
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
        "image_offset": {"x": _s(r.translate[0]), "y": _s(r.translate[1])},
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
    owner = log.manifest()[0]["owner"]
    status = Executor(
        v.store, log, v.proposer if meta["live"] else _offline(v), _Deferred(), v.ledger,
        StepConfig(probes=True), worst_usd=v.worst_usd if meta["live"] else Fraction(0), skill_id=meta["skill_id"],
        probe_renderer=make_probe_renderer(v, owner, sid),
    ).run()  # fmt: skip
    if status != "committed":
        return
    evs = log.events()
    if any(e.type in ("VersionActivated", "ActivationRejected") for e in evs):
        return
    version = next(e.payload["version"] for e in evs if e.type == "VersionStored")
    try:
        records.put_new(
            v.store,
            f"skills/{meta['skill_id']}/owner.json",
            log.manifest()[0]["owner"],
            {"provenance": {"model": meta["model"], "teacher": meta["teacher"]}, "session_id": sid},
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


def _open_request(evs: list) -> tuple[Optional[dict], Optional[str]]:
    from open_apprentice.teaching.executor import ENDED
    from open_apprentice.teaching.teacher import response_from_json

    if any(e.type in ENDED for e in evs):
        return None, None

    answered = {
        response_from_json(e.payload["response"]).request_id
        for e in evs
        if e.type == "ResponseRecorded"
    }
    for e in evs:
        if e.type == "RequestIssued" and e.payload["request"]["request_id"] not in answered:
            return e.payload["request"], e.payload["action_id"]
    return None, None


def _approve_all(req: dict, checks: Optional[dict] = None) -> dict:
    t = req["type"]
    ok = {i: c["ok"] for i, c in (checks or {}).items()}
    if t == "ChooseOutput":
        return {"kind": "choose", "selected": req["alternatives"][0][0]}
    if t == "ConfirmPreview":
        return {
            "kind": "items",
            "per_item": [
                [it[0], "approve" if ok.get(it[0], True) else "reject"] for it in req["items"]
            ],
        }
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
        checks = item_checks(evs, req)
        outstanding = {
            "request_id": req["request_id"],
            "intent_revision": manifest["intent_revision"],
            "request": req,
            "item_ids": list(item_outputs(req)),
            "checks": checks,
            "approve_all_answer": _approve_all(req, checks),
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
) -> str:
    """Spec 8 correction states: draft → (waiting_for_model | waiting_for_answer)* → review → stored → activated |
    activation_rejected | failed; override / dismissed are the non-learning outcomes; cancellation is terminal.
    """
    for t, state in (
        ("VersionActivated", "activated"),
        ("ActivationRejected", "activation_rejected"),
        ("OverrideRecorded", "override"),
        ("CorrectionDismissed", "dismissed"),
        ("CorrectionAbandoned", "cancelled"),
    ):
        if t in types:
            return state
    if abstain is not None or error is not None:
        return "failed"
    if "VersionStored" in types:
        return "stored"
    if req is not None:
        return "review" if req["type"] == "ConfirmPreview" else "waiting_for_answer"
    if waiting_model:
        return "waiting_for_model"
    return "draft"


# ---- answers and cancellation --------------------------------------------------------------------------------------------


def _norm_response(d: dict) -> tuple:
    return (d.get("kind"), d.get("selected"), [list(p) for p in d.get("per_item") or []])


def _same_response(stored: dict, new: dict) -> bool:
    return _norm_response(stored) == _norm_response(new)


def submit_answer(v: V2, owner: str, sid: str, body: dict) -> dict:
    from open_apprentice.teaching.events import SessionLog
    from open_apprentice.teaching.executor import submit_response
    from open_apprentice.teaching.teacher import Response

    records.load(v.store, _meta_key(sid), owner)
    log = SessionLog(v.store, sid)
    manifest, _ = log.manifest()
    evs = log.events()
    rid = body.get("request_id")
    prior = next(
        (
            e.payload["response"]
            for e in evs
            if e.type == "ResponseRecorded" and e.payload["response"]["request_id"] == rid
        ),
        None,
    )
    if prior is not None:
        if _same_response(prior, body):
            return {"accepted": True, "duplicate": True}
        raise Conflict("NOT_OUTSTANDING", "this question was already answered differently")
    req, _ = _open_request(evs)
    if (
        req is None
        or req["request_id"] != rid
        or body.get("intent_revision") != manifest["intent_revision"]
    ):
        raise Conflict("NOT_OUTSTANDING", "this question is no longer open; reload the session")
    if req["type"] == "ConfirmPreview":
        checks = item_checks(evs, req)
        for p in body.get("per_item") or []:
            item = str(p[0]) if isinstance(p, (list, tuple)) and len(p) == 2 else ""
            if p[1:] == ["approve"] and not checks.get(item, {"ok": True})["ok"]:
                raise Conflict(
                    "BLOCKED_ITEM",
                    "this document cannot be approved: " + "; ".join(checks[item]["reasons"]),
                )
    try:
        resp = Response(
            rid,
            str(body.get("kind", "")),
            body.get("selected"),
            tuple((str(p[0]), str(p[1])) for p in body.get("per_item") or []),
            None,
            "human",
        )
    except (TypeError, IndexError) as e:
        raise Conflict("INVALID_ANSWER", f"the answer is malformed ({e})") from e
    if not submit_response(log, resp):
        raise Conflict(
            "INVALID_ANSWER", "the answer does not fit the question (or it was answered meanwhile)"
        )
    v.dispatcher.submit(sid, lambda: advance(v, sid))
    return {"accepted": True, "duplicate": False}


TERMINAL_TYPES = (
    "Abstained",
    "Errored",
    "VersionStored",
    "OverrideRecorded",
    "CorrectionDismissed",
    "ActivationRejected",
)


def cancel_session(v: V2, owner: str, sid: str) -> dict:
    """Stop new authorizations (spec 8). Late provider usage is still booked by the executor; late results cannot resume."""
    from open_apprentice.teaching.events import Conflict as LogConflict
    from open_apprentice.teaching.events import SessionLog

    meta, _ = records.load(v.store, _meta_key(sid), owner)
    log = SessionLog(v.store, sid)
    for _ in range(20):
        if any(e.type in TERMINAL_TYPES for e in log.events()):
            return {"cancelled": False}
        try:
            if meta["kind"] == "correction":
                log.append("CorrectionAbandoned", "human", {})
            else:
                log.append(
                    "Abstained", "human", {"action_id": f"cancel-{sid}", "reason": CANCELLED}
                )
            return {"cancelled": True}
        except LogConflict:
            continue  # the session moved; look again
    raise Conflict("BUSY", "the session is busy; try again")


# ---- apply runs and export -----------------------------------------------------------------------------------------------


def _run_key(run_id: str) -> str:
    return f"runs/{run_id}.json"


def _skill_owner(v: V2, owner: str, skill_id: str) -> dict:
    return records.load(v.store, f"skills/{skill_id}/owner.json", owner)[0]


def _version(v: V2, skill_id: str, version: int) -> dict:
    from open_apprentice.skills.versions import SkillStore

    try:
        return SkillStore(v.store).version(skill_id, version)
    except KeyError as e:
        raise records.NotFound(f"{skill_id} v{version}") from e


def apply_version(
    v: V2, owner: str, skill_id: str, version: int, documents: list[dict], idempotency_key: str
) -> dict:
    provenance = _skill_owner(v, owner, skill_id).get(
        "provenance", {"model": "Fixture", "teacher": "You"}
    )
    _version(v, skill_id, version)
    body = {"skill_id": skill_id, "version": version, "documents": documents}

    def produce() -> dict:
        run_id = uuid.uuid4().hex
        records.put_new(
            v.store,
            _run_key(run_id),
            owner,
            {**body, "run_id": run_id, "status": "running", "results": {},
             "provenance": provenance},
        )  # fmt: skip
        v.dispatcher.submit(f"run:{run_id}", lambda: run_apply(v, owner, run_id))
        return {"run_id": run_id, "status_url": f"/api/v2/runs/{run_id}"}

    return records.idempotent(v.store, owner, f"apply:{idempotency_key}", _digest(body), produce)


def _reasons(rec: Any) -> list[str]:
    out = [f"label {k}: measured {r['measured']} vs target {r['exact']} (tolerance {r['tolerance']})"
           for k, r in rec.conformance["labels"].items() if not r["ok"]]  # fmt: skip
    out += rec.preservation["differences"]
    out += [f"{c} would lie outside the page" for c in rec.layout["outside"]]
    out += [f"{a} would overlap {b}" for a, b in rec.layout["overlaps"]]
    return out


def _apply_one(v: V2, owner: str, run: dict, ref: dict, rule: list) -> dict:
    import dataclasses

    from open_apprentice.drawio.publish import publish
    from open_apprentice.teaching.step import run_output

    try:
        f, idx, _, scene = page_scene(v, owner, ref["doc_id"], ref["page_id"], ref["mapping_hash"])
        out = run_output(rule, scene.scene)
        if out is None:
            return {
                "status": "failed",
                "reasons": ["the skill's rule could not run on this document"],
            }
        now = {o["id"]: (o["x"], o["y"]) for o in scene.scene["objects"]}
        targets = {k: p for k, p in out.items() if k in scene.movable and p != now[k]}
        if not targets:
            return {"status": "unchanged", "reasons": []}
        edits = plan_edits(f.pages[idx], scene.offsets, targets)
        key = f"runs/{run['run_id']}/{ref['doc_id']}-{ref['page_id']}.drawio"
        rec = publish(
            v.store, key, f, idx, edits, targets, scene, v.render,
            intent={"source": "approved examples of the skill", "skill": run["skill_id"], "version": run["version"]},
        )  # fmt: skip
        receipt = dataclasses.asdict(rec)
        if rec.published:
            return {"status": "published", "key": key, "receipt": receipt, "reasons": []}
        return {"status": "blocked", "receipt": receipt, "reasons": _reasons(rec)}
    except (DrawioRefused, Conflict) as e:
        return {"status": "blocked", "reasons": [str(e)]}


def run_apply(v: V2, owner: str, run_id: str) -> None:
    run, _ = records.load(v.store, _run_key(run_id), owner)
    try:
        _run_documents(v, owner, run_id, run)
    except Exception as e:  # never leave a run "running" forever
        reason = f"{type(e).__name__}: {e}"[:200]
        records.update(
            v.store, _run_key(run_id), owner, lambda d: {**d, "status": "failed", "error": reason}
        )
        raise


def _run_documents(v: V2, owner: str, run_id: str, run: dict) -> None:
    rule = _version(v, run["skill_id"], run["version"])["program"]["rule"]
    for i, ref in enumerate(run["documents"]):
        if records.load(v.store, _run_key(run_id), owner)[0]["status"] == "cancelled":
            return
        if not isinstance(ref, dict) or not all(
            isinstance(ref.get(x), str) for x in ("doc_id", "page_id", "mapping_hash")
        ):
            k, result = f"invalid:{i}", {
                "status": "failed",
                "reasons": ["not a document reference (doc_id, page_id, mapping_hash)"],
            }
        else:
            k = f"{ref['doc_id']}:{ref['page_id']}"
            try:
                result = _apply_one(v, owner, run, ref, rule)
            except records.NotFound:
                result = {"status": "failed", "reasons": ["no such document"]}
        records.update(
            v.store,
            _run_key(run_id),
            owner,
            lambda d: {**d, "results": {**d["results"], k: result}},
        )
    records.update(
        v.store, _run_key(run_id), owner,
        lambda d: d if d["status"] == "cancelled" else {**d, "status": "done"},
    )  # fmt: skip


def get_run(v: V2, owner: str, run_id: str) -> dict:
    return {
        k: x for k, x in records.load(v.store, _run_key(run_id), owner)[0].items() if k != "owner"
    }


def cancel_run(v: V2, owner: str, run_id: str) -> dict:
    d = records.update(
        v.store, _run_key(run_id), owner,
        lambda d: {**d, "status": "cancelled"} if d["status"] == "running" else d,
    )  # fmt: skip
    return {"status": d["status"]}


def export(
    v: V2, owner: str, run_id: str, doc_id: str, page_id: str, fmt: str
) -> tuple[bytes, str]:
    run, _ = records.load(v.store, _run_key(run_id), owner)
    res = run["results"].get(f"{doc_id}:{page_id}")
    if res is None:
        raise records.NotFound(f"{doc_id}:{page_id}")
    if fmt == "receipt":
        if "receipt" not in res:
            raise Conflict(
                "NO_RECEIPT", "this document has no receipt: " + "; ".join(res["reasons"])
            )
        return json.dumps(res["receipt"], indent=1).encode(), "application/json"
    if res["status"] != "published":
        raise Conflict(
            "NOT_PUBLISHED", "nothing was published for this document: " + "; ".join(res["reasons"])
        )
    data = v.store.get(res["key"])
    if data is None:
        raise records.NotFound(res["key"])
    if fmt == "drawio":
        return data.data, "application/vnd.jgraph.mxfile"
    if fmt == "svg":
        if v.render_svg is None:
            raise Conflict("SVG_UNAVAILABLE", "SVG export is not available on this server")
        doc = load_drawio(data.data)
        page = next(p for p in doc.pages if p.id == page_id)
        svg = v.render_svg(page)
        if svg is None:
            raise Conflict("SVG_UNAVAILABLE", "the renderer returned no SVG")
        return svg.encode(), "image/svg+xml"
    raise Conflict("BAD_FORMAT", "format must be drawio, svg or receipt")


# ---- corrections and activation ------------------------------------------------------------------------------------------


def start_correction_session(v: V2, owner: str, skill_id: str, body: dict) -> dict:
    keys = (
        "base_version",
        "base_pointer_generation",
        "run_id",
        "doc_id",
        "page_id",
        "boxes",
        "mask",
        "full_approval",
    )
    req = {k: body.get(k) for k in keys}
    return records.idempotent(
        v.store,
        owner,
        f"correction:{body.get('idempotency_key', '')}",
        _digest(req),
        lambda: _start_correction(v, owner, skill_id, req),
    )


def _start_correction(v: V2, owner: str, skill_id: str, req: dict) -> dict:
    from open_apprentice.skills.versions import SkillStore
    from open_apprentice.teaching.correction_executor import start_correction
    from open_apprentice.teaching.step import run_output

    provenance = _skill_owner(v, owner, skill_id).get(
        "provenance", {"model": "Fixture", "teacher": "You"}
    )
    version, _, generation = SkillStore(v.store).active(skill_id)
    if (version, generation) != (req["base_version"], req["base_pointer_generation"]):
        raise Conflict(
            "STALE_BASE", "the skill changed since this run; reload and correct the current version"
        )
    run, _ = records.load(v.store, _run_key(req["run_id"]), owner)
    if run["skill_id"] != skill_id:
        raise Conflict("BAD_REQUEST", "this run did not use this skill")
    if run["version"] != req["base_version"]:
        raise Conflict(
            "STALE_BASE",
            f"this run used version {run['version']}; corrections apply to the output you saw, so apply the current "
            "version again and correct that",
        )
    refs = {(d["doc_id"], d["page_id"]): d for d in run["documents"]}
    ref = refs.get((req["doc_id"], req["page_id"]))
    if ref is None:
        raise records.NotFound(f"{req['doc_id']}:{req['page_id']}")
    _, _, _, scene = page_scene(v, owner, ref["doc_id"], ref["page_id"], ref["mapping_hash"])
    rule = _version(v, skill_id, version)["program"]["rule"]
    produced = run_output(rule, scene.scene) or {}
    boxes = _boxes(req["boxes"] or {})
    mask = [str(m) for m in (req["mask"] or [])]
    if not mask or set(mask) - set(boxes) or set(boxes) - set(scene.movable):
        raise Conflict("BAD_REQUEST", "the corrected labels must be movable labels with positions")
    now = {o["id"]: (o["x"], o["y"]) for o in scene.scene["objects"] if o["id"] in scene.movable}
    corrected = {**now, **{k: p for k, p in produced.items() if k in now}, **boxes}
    extra = {}
    for d in run["documents"]:
        if (d["doc_id"], d["page_id"]) != (ref["doc_id"], ref["page_id"]):
            try:
                extra[_scene_id(d)] = page_scene(
                    v, owner, d["doc_id"], d["page_id"], d["mapping_hash"]
                )[3].scene
            except (Conflict, DrawioRefused, records.NotFound):
                continue  # a document that can no longer be read is left out of the checks
    sid = uuid.uuid4().hex
    start_correction(
        v.store, sid, skill_id, _scene_id(ref), scene.scene, corrected, mask, extra,
        full_approval=bool(req["full_approval"]), owner=owner,
    )  # fmt: skip
    meta = {"sid": sid, "kind": "correction", "skill_id": skill_id, "run_id": run["run_id"],
            "model": "Fixture", "teacher": "You", "live": False, "skill_provenance": provenance}  # fmt: skip
    records.put_new(v.store, _meta_key(sid), owner, meta)
    v.dispatcher.submit(sid, lambda: advance(v, sid))
    return {"session_id": sid, "operation": "advance", "status_url": f"/api/v2/sessions/{sid}"}


def advance_correction(v: V2, sid: str) -> None:
    from open_apprentice.teaching.correction_executor import CorrectionExecutor
    from open_apprentice.teaching.events import SessionLog

    meta = _raw_meta(v, sid)
    scope = v.scope_proposer if meta["live"] else _offline(v)
    worst = v.worst_usd if meta["live"] else Fraction(0)
    CorrectionExecutor(
        v.store, SessionLog(v.store, sid), scope, _Deferred(), v.ledger, worst_usd=worst
    ).run()


def skill_status(v: V2, owner: str, skill_id: str) -> dict:
    from open_apprentice.skills.versions import SkillStore

    rec = _skill_owner(v, owner, skill_id)
    skills = SkillStore(v.store)
    version, _, generation = skills.active(skill_id)
    versions, n = [], 1
    while True:
        try:
            art = skills.version(skill_id, n)
        except KeyError:
            break
        versions.append({"version": n, "parent_version": art.get("parent_version"),
                         "summary": art.get("program", {}).get("summary", "")})  # fmt: skip
        n += 1
    return {
        "skill_id": skill_id,
        "active": {"version": version, "generation": generation},
        "versions": versions,
        "history": skills.history(skill_id),
        "provenance": rec.get("provenance"),
    }


def activate(
    v: V2, owner: str, skill_id: str, version: int, expected_generation: Optional[int], key: str
) -> dict:
    from open_apprentice.skills.versions import ActivationRejected, SkillStore

    _skill_owner(v, owner, skill_id)
    _version(v, skill_id, version)

    def produce() -> dict:
        try:
            rid = SkillStore(v.store).activate(
                skill_id, version, expected_generation, f"activate-{key}", "api"
            )
        except ActivationRejected as e:
            raise Conflict("ACTIVATION_REJECTED", str(e)) from e
        return {"activated": version, "record_id": rid}

    return records.idempotent(
        v.store,
        owner,
        f"activate:{key}",
        _digest({"skill": skill_id, "v": version, "g": expected_generation}),
        produce,
    )


def page_scene_view(v: V2, owner: str, doc_id: str, page_id: str, mapping_hash: str) -> dict:
    """Scene geometry for the overlay, plus where document coordinates land in the preview image."""
    _, _, _, sc = page_scene(v, owner, doc_id, page_id, mapping_hash)
    r = _stored_render(v, doc_id, page_id)
    keys = ("id", "kind", "role", "attached")
    return {
        "scene_hash": scene_digest(sc.scene),
        "canvas": {k: _s(x) for k, x in sc.scene["canvas"].items()},
        "image_offset": {"x": _s(r.translate[0]), "y": _s(r.translate[1])},
        "objects": [
            {**{k: o[k] for k in keys}, **{k: _s(o[k]) for k in ("x", "y", "w", "h")}}
            for o in sc.scene["objects"]
        ],
        "movable": list(sc.movable),
    }


# ---- rendered question items and their checks ----------------------------------------------------------------------------


def item_outputs(req: dict) -> dict[str, tuple[str, dict]]:
    """Every renderable item of a question: id → (scene id, output)."""
    t = req["type"]
    if t == "ChooseOutput":
        return {a: (req["scene_id"], out) for a, out in req["alternatives"]}
    if t == "ConfirmPreview":
        return {i: (sid, out) for i, sid, _, out in req["items"]}
    if t == "ConfirmCorrectionScope":
        return {
            f"{it['interp_id']}:{k}": (sid, out)
            for it in req["interpretations"]
            for k, (sid, _, out) in enumerate(it["consequences"])
        }
    return {}


def _session_scenes(evs: list) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in evs:
        if e.type == "SceneRegistered":
            out[e.payload["scene_id"]] = scene_from_payload(e.payload["scene"])
        elif e.type == "CorrectionStarted":
            out[e.payload["scene_id"]] = scene_from_payload(e.payload["scene"])
    return out


def _layout_check(scene: dict, output: dict) -> dict:
    """Geometric layout safety of an output on its scene: positioned labels inside the page, no overlap (touching allowed)."""
    placed = {k: (Fraction(str(p[0])), Fraction(str(p[1]))) for k, p in output.items()}
    boxes = {
        o["id"]: (*placed.get(o["id"], (o["x"], o["y"])), o["w"], o["h"]) for o in scene["objects"]
    }
    W, H = scene["canvas"]["w"], scene["canvas"]["h"]
    reasons = []
    for k in sorted(placed):
        if k not in boxes:
            continue
        x, y, w, h = boxes[k]
        if x < 0 or y < 0 or x + w > W or y + h > H:
            reasons.append(f"label {k} would lie outside the page")
        for other, (ox, oy, ow, oh) in sorted(boxes.items()):
            if other != k and x < ox + ow and ox < x + w and y < oy + oh and oy < y + h:
                reasons.append(f"label {k} would overlap {other}")
    return {"ok": not reasons, "reasons": reasons}


def item_checks(evs: list, req: dict) -> dict[str, dict]:
    scenes = _session_scenes(evs)
    out = {}
    for item, (sid, output) in item_outputs(req).items():
        sc = scenes.get(sid)
        out[item] = (
            _layout_check(sc, output)
            if sc is not None
            else {"ok": False, "reasons": ["unknown document"]}
        )
    return out


def _ref_for_scene(v: V2, owner: str, meta: dict, scene_id: str) -> dict:
    refs = list(meta.get("documents") or [])
    if meta["kind"] == "correction":
        refs = list(records.load(v.store, _run_key(meta["run_id"]), owner)[0]["documents"])
    refs += meta.get("probe_refs") or []
    ref = next((r for r in refs if isinstance(r, dict) and _scene_id(r) == scene_id), None)
    if ref is None:
        raise records.NotFound(scene_id)
    return ref


def item_png(v: V2, owner: str, sid: str, request_id: str, item_id: str) -> bytes:
    import hashlib

    from open_apprentice.teaching.events import SessionLog

    meta, _ = records.load(v.store, _meta_key(sid), owner)
    evs = SessionLog(v.store, sid).events()
    req = next(
        (
            e.payload["request"]
            for e in evs
            if e.type == "RequestIssued" and e.payload["request"]["request_id"] == request_id
        ),
        None,
    )
    if req is None or item_id not in item_outputs(req):
        raise records.NotFound(item_id)
    key = f"sessions/{sid}/renders/{request_id}/{hashlib.sha256(item_id.encode()).hexdigest()}.png"
    cached = v.store.get(key)
    if cached is not None:
        return cached.data
    scene_id, output = item_outputs(req)[item_id]
    ref = _ref_for_scene(v, owner, meta, scene_id)
    draft = draft_render(v, owner, ref["doc_id"], ref["page_id"], ref["mapping_hash"], output)
    if not draft["png"]:
        raise Conflict("NO_PREVIEW", "the renderer returned no image")
    data = base64.b64decode(draft["png"])
    v.store.create(key, data)
    return data


def config(v: V2) -> dict:
    from open_apprentice.drawio.parse import MAX_UPLOAD

    return {
        "live_available": bool(v.live_available()),
        "model": v.model,
        "max_upload_bytes": MAX_UPLOAD,
    }


# ---- generated probes ---------------------------------------------------------------------------------------------------

PROBE_TOLERANCE = Fraction(1, 2)


def make_probe_renderer(v: V2, owner: str, sid: str) -> Any:
    """Turn a generated probe into a real document: patch the source .drawio, render it in the locked engine, and accept it
    only if every measured box matches the probe's selection geometry within 0.5 (spec 4 rule 3)."""
    from open_apprentice.drawio.patch import apply_geometry
    from open_apprentice.teaching.probes import Probe, ProbeResult

    def render(probe: Probe) -> ProbeResult:
        meta = _raw_meta(v, sid)
        try:
            ref = _ref_for_scene(v, owner, meta, probe.source_scene_id)
            f = _source(v, ref["doc_id"])
            idx = next(p.index for p in f.pages if p.id == ref["page_id"])
            cells = {cid: {k: Fraction(val) for k, val in attrs} for cid, attrs in probe.edits}
            width = Fraction(probe.canvas_w) if probe.canvas_w is not None else None
            raw, _ = apply_geometry(f, idx, cells, width, f.doc_hash)
            pid = _import_probe_document(v, owner, sid, probe.probe_id, ref, raw)
            m, _ = _stored_mapping(v, pid, ref["page_id"])
            _, _, _, scene = page_scene(v, owner, pid, ref["page_id"], mp.digest(m))
        except (DrawioRefused, Conflict, records.NotFound, StopIteration) as e:
            return ProbeResult(False, reason=f"the probe document could not be built: {e}"[:200])
        want = {o["id"]: o for o in probe.scene["objects"]}
        worst = Fraction(0)
        for o in scene.scene["objects"]:
            w = want.get(o["id"])
            if w is None:
                return ProbeResult(
                    False, reason=f"the rendered probe has an unexpected object {o['id']}"
                )
            for k in ("x", "y", "w", "h"):
                worst = max(worst, abs(Fraction(o[k]) - Fraction(w[k])))
        if worst > PROBE_TOLERANCE:
            return ProbeResult(
                False,
                reason=f"measured geometry differs by {float(worst):.2f} from the selected probe",
            )
        new_ref = {"doc_id": pid, "page_id": ref["page_id"], "mapping_hash": mp.digest(m)}
        records.update(
            v.store,
            _meta_key(sid),
            owner,
            lambda d: {**d, "probe_refs": [*d.get("probe_refs", []), new_ref]},
        )
        return ProbeResult(True, _scene_id(new_ref), scene.scene)

    return render


def _import_probe_document(
    v: V2, owner: str, sid: str, probe_id: str, src: dict, raw: bytes
) -> str:
    """A probe document: owned by the session owner, rendered now, its mapping copied from the source and confirmed."""
    f = load_drawio(raw)
    doc_id = uuid.uuid4().hex
    page = next(p for p in f.pages if p.id == src["page_id"])
    c = classify(page)
    v.store.create(f"documents/{doc_id}/source.drawio", raw)
    entry = {"page_id": page.id, "index": page.index, "name": page.name, "status": "ok",
             "movable": list(c.movable), "fixed": list(c.fixed), "reasons": c.reasons}  # fmt: skip
    body = {"doc_id": doc_id, "name": f"probe {probe_id[:8]}", "doc_hash": f.doc_hash, "pages": [entry],
            "render": "pending", "probe_of": {"sid": sid, "probe_id": probe_id}}  # fmt: skip
    records.put_new(v.store, _doc_key(doc_id), owner, body)
    render_document(v, owner, doc_id)
    source_map, _ = _stored_mapping(v, src["doc_id"], src["page_id"])
    m = mp.confirm(
        mp.Mapping(f.doc_hash, page.id, dict(source_map.labels), frozenset(), None),
        f"probe-{probe_id}",
    )
    v.store.put(
        _page_key(doc_id, page.id, "mapping.json"),
        records.dumps(mp.to_json(m)),
        if_generation=_stored_mapping(v, doc_id, page.id)[1],
    )
    return doc_id
