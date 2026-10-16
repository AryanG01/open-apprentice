"""Publish a patched .drawio only if it parses, renders and passes every output check (spec 6). Conformance, preservation and
layout safety are separate axes; intent is passed through from the caller and never merged into them or used as a gate here."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Optional

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioFile, DrawioRefused, Page, load_drawio
from open_apprentice.drawio.patch import Edit, apply_edits
from open_apprentice.drawio.render import Box, Rendered
from open_apprentice.drawio.scene import DrawioScene
from open_apprentice.storage.store import Store

CONFORMANCE_TOLERANCE = Fraction(1, 2)  # spec 3.6; each label's rounding error is added to it
NOTES = ("connector crossings are not checked",)


@dataclass(frozen=True)
class Receipt:
    published: bool
    key: Optional[str]
    conformance: dict
    preservation: dict
    layout: dict
    intent: Optional[dict]
    profile: dict
    notes: tuple[str, ...]


def _overlap(a: Box, b: Box) -> bool:
    return (
        a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h
    )  # touching is allowed


def _preservation(before: Page, after: Page, edited: set[str]) -> dict:
    diffs = []
    if before.model != after.model:
        diffs.append("page settings changed")
    if [c.id for c in before.cells] != [c.id for c in after.cells]:
        diffs.append("cells added, removed or reordered")
    for a, b in zip(before.cells, after.cells):
        same = (a.parent, a.vertex, a.edge, a.style, a.value, a.wrapper) == (
            b.parent,
            b.vertex,
            b.edge,
            b.style,
            b.value,
            b.wrapper,
        )
        moved = ("x", "y") if a.id in edited else ()
        ga = {k: v for k, v in a.geometry.items() if k not in moved}
        gb = {k: v for k, v in b.geometry.items() if k not in moved}
        if not same or ga != gb:
            diffs.append(f"cell {a.id!r} changed beyond its x/y")
    return {"ok": not diffs, "differences": diffs}


def publish(
    store: Store,
    key: str,
    f: DrawioFile,
    page_index: int,
    edits: list[Edit],
    targets: dict[str, tuple[Fraction, Fraction]],
    before: DrawioScene,
    render: Callable[[Page], Rendered],
    intent: Optional[dict] = None,
    drift: Optional[str] = None,
) -> Receipt:
    new = apply_edits(f, page_index, edits, before.doc_hash)
    g = load_drawio(new)
    others_ok = all(
        new[q.content_span[0] : q.content_span[1]] == f.raw[p.content_span[0] : p.content_span[1]]
        for p, q in zip(f.pages, g.pages)
        if p.index != page_index
    )
    page = g.pages[page_index]
    c = classify(page)
    r = render(page)
    profile = dict(r.profile)
    notes = NOTES + (
        f"measured under profile {str(profile.get('viewer_sha256', '?'))[:12]}/{profile.get('font', '?')}; "
        + (drift or "drift against other font environments was not measured"),
    )
    old = {o["id"]: o for o in before.scene["objects"]}
    rows: dict[str, dict] = {}
    conf_ok = True
    for e in edits:
        if e.cell_id not in r.labels:
            raise DrawioRefused(f"label {e.cell_id!r} could not be measured after the edit")
        m, lines = r.labels[e.cell_id]
        tx, ty = targets[e.cell_id]
        rounding = max(abs(e.serialized[0] - e.exact[0]), abs(e.serialized[1] - e.exact[1]))
        err = max(abs(m.x - tx), abs(m.y - ty))
        size = max(abs(m.w - old[e.cell_id]["w"]), abs(m.h - old[e.cell_id]["h"]))
        ok = (
            err <= CONFORMANCE_TOLERANCE + rounding and size <= CONFORMANCE_TOLERANCE and lines == 1
        )
        conf_ok = conf_ok and ok
        rows[e.cell_id] = {
            "exact": [str(v) for v in e.exact],
            "serialized": list(e.serialized),
            "measured": [str(m.x), str(m.y)],
            "error": str(err),
            "tolerance": str(CONFORMANCE_TOLERANCE + rounding),
            "size_change": str(size),
            "lines": lines,
            "ok": ok,
        }
    pres = _preservation(f.pages[page_index], page, {e.cell_id for e in edits})
    if not others_ok:
        pres = {"ok": False, "differences": pres["differences"] + ["another page's bytes changed"]}
    finals = {cid: r.labels[cid][0] for cid in c.movable if cid in r.labels}
    finals.update({cid: r.nodes[cid][0] for cid in c.fixed if cid in r.nodes})
    finals.update({cid: r.labels[cid][0] for cid in c.fixed if cid in r.labels})
    outside = [
        cid
        for cid, b in finals.items()
        if b.x < 0 or b.y < 0 or b.x + b.w > c.width or b.y + b.h > c.height
    ]
    overlaps = sorted(
        {
            tuple(sorted((e.cell_id, o)))
            for e in edits
            if e.cell_id in finals
            for o, b in finals.items()
            if o != e.cell_id and _overlap(finals[e.cell_id], b)
        }
    )
    layout = {
        "ok": not outside and not overlaps,
        "outside": outside,
        "overlaps": [list(p) for p in overlaps],
    }
    passed = conf_ok and pres["ok"] and layout["ok"]
    published = passed and store.create(key, new)
    return Receipt(
        published,
        key if published else None,
        {"ok": conf_ok, "labels": rows},
        pres,
        layout,
        intent,
        profile,
        notes,
    )
