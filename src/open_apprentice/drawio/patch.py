"""Write label targets into <mxGeometry> x/y by byte-span replacement (spec 6). Coordinates are serialized in whole document
units, half rounding up, because draw.io renders HTML labels at whole units (round-trip spike). The exact target, the serialized
value and the old raw value are kept separately. The input is never modified: the result is new bytes."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from open_apprentice.drawio.parse import MAX_UPLOAD, DrawioFile, DrawioRefused, Page


@dataclass(frozen=True)
class Edit:
    cell_id: str
    exact: tuple[Fraction, Fraction]
    serialized: tuple[int, int]
    expected_old: tuple[Optional[str], Optional[str]]  # raw x/y attribute strings, None when absent


def round_half_up(v: Fraction) -> int:
    return math.floor(v + Fraction(1, 2))


def plan_edits(
    page: Page,
    offsets: dict[str, tuple[Fraction, Fraction]],
    target_boxes: dict[str, tuple[Fraction, Fraction]],
) -> list[Edit]:
    """Target geometry = target box − offset d, per label."""
    cells = {c.id: c for c in page.cells}
    out = []
    for cid, (bx, by) in sorted(target_boxes.items()):
        dx, dy = offsets[cid]
        ex, ey = bx - dx, by - dy
        g = cells[cid].geometry
        out.append(
            Edit(cid, (ex, ey), (round_half_up(ex), round_half_up(ey)), (g.get("x"), g.get("y")))
        )
    return out


def _set_attr(tag: str, key: str, value: int) -> str:
    pat = re.compile(rf'(\s{key}=")[^"]*(")')
    if pat.search(tag):
        return pat.sub(lambda m: f"{m.group(1)}{value}{m.group(2)}", tag, count=1)
    return tag.replace("<mxGeometry", f'<mxGeometry {key}="{value}"', 1)


def _patch_xml(page: Page, edits: list[Edit]) -> tuple[bytes, list[tuple[int, int, bytes]]]:
    """The page XML with edits applied, plus the (start, end, new tag) replacements relative to page.xml."""
    cells = {c.id: c for c in page.cells}
    reps = []
    for e in edits:
        c = cells.get(e.cell_id)
        if c is None or c.geometry_span is None:
            raise DrawioRefused(f"cell {e.cell_id!r} has no geometry to edit")
        if (c.geometry.get("x"), c.geometry.get("y")) != e.expected_old:
            raise DrawioRefused(
                f"cell {e.cell_id!r} is not where expected {e.expected_old}; the document changed"
            )
        s, t = c.geometry_span
        tag = page.xml[s:t].decode("utf-8")
        tag = _set_attr(_set_attr(tag, "x", e.serialized[0]), "y", e.serialized[1])
        reps.append((s, t, tag.encode("utf-8")))
    xml = page.xml
    for s, t, new in sorted(reps, reverse=True):
        xml = xml[:s] + new + xml[t:]
    return xml, reps


def apply_edits(f: DrawioFile, page_index: int, edits: list[Edit], source_hash: str) -> bytes:
    if f.doc_hash != source_hash:
        raise DrawioRefused("the document changed since it was measured; measure it again")
    page = f.pages[page_index]
    new_xml, reps = _patch_xml(page, edits)
    s0, e0 = page.content_span
    if page.compressed:
        # the edited page is written uncompressed (model-level preservation); other pages keep their bytes
        out = f.raw[:s0] + new_xml + f.raw[e0:]
    else:
        out = f.raw
        for s, t, new in sorted(reps, reverse=True):
            out = out[: s0 + s] + new + out[s0 + t :]
    if len(out) > MAX_UPLOAD:
        raise DrawioRefused("the edited file would exceed the 2 MB upload limit")
    return out
