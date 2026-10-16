"""The /api/v2 service layer: plain functions over a V2 context. Routes are thin wrappers around these (spec 8)."""

from __future__ import annotations

import base64
import json
import uuid
from fractions import Fraction
from typing import Any

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
