"""Cell statuses for one page (spec 6 table) and the release-1 page limitations, each refused with a reason."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from open_apprentice.drawio.parse import Cell, DrawioRefused, Page

MAX_OBJECTS = 400  # a learned skill can be applied to large pages; teaching sessions stay at TEACH_MAX_OBJECTS
MAX_MOVABLE = 200
TEACH_MAX_OBJECTS = 32  # what a teaching session (and its model prompt) handles
FONTS = frozenset({"", "Helvetica"})


@dataclass(frozen=True)
class Classified:
    page: Page
    movable: tuple[str, ...]
    fixed: tuple[str, ...]
    edges: tuple[str, ...]
    reasons: dict[str, str]  # why a label is not movable
    width: Fraction
    height: Fraction
    absolute: dict[
        str, tuple[Fraction, Fraction, Fraction, Fraction]
    ]  # geometry box in document coordinates


NUMBER = re.compile(
    r"-?\d{1,9}(\.\d{1,9})?"
)  # what draw.io writes; anything else is refused before Fraction sees it


def _num(v: Optional[str]) -> Fraction:
    if v in (None, ""):
        return Fraction(0)
    if not NUMBER.fullmatch(v):
        raise DrawioRefused(f"a geometry value {v[:40]!r} is not a number")
    return Fraction(v)


def _label_problem(c: Cell, layers: set[str]) -> str:
    if c.wrapper:
        return "labels inside a UserObject/object wrapper are not moved in release 1"
    if c.parent not in layers:
        return "labels inside a group or container are not moved in release 1"
    if _num(c.style.get("rotation")) != 0:
        return "rotated labels are not moved in release 1"
    if not c.value.strip():
        return "empty labels cannot be measured"
    return ""


def classify(page: Page) -> Classified:
    m = page.model
    if m.get("pageScale", "1") not in ("1", "1.0"):
        raise DrawioRefused(
            f"pageScale={m.get('pageScale')} is not supported in release 1 (only 1)"
        )
    if m.get("page", "1") == "0":
        raise DrawioRefused(
            "the page view is switched off (page=0); release 1 needs a page to define the editing area"
        )
    width, height = _num(m.get("pageWidth", "850")), _num(m.get("pageHeight", "1100"))
    by_id = {c.id: c for c in page.cells}
    roots = {c.id for c in page.cells if not c.parent}
    layers = {c.id for c in page.cells if c.parent in roots}
    movable: list[str] = []
    fixed: list[str] = []
    edges: list[str] = []
    reasons: dict[str, str] = {}
    absolute: dict[str, tuple[Fraction, Fraction, Fraction, Fraction]] = {}
    for c in page.cells:
        if c.edge:
            edges.append(c.id)
            continue
        if not c.vertex:
            continue
        font = c.style.get("fontFamily", "")
        if font not in FONTS:
            raise DrawioRefused(
                f"cell {c.id!r} uses the font {font!r}; release 1 bundles only Helvetica (Liberation Sans)"
            )
        if c.geometry.get("relative") == "1":
            reasons[c.id] = "labels with relative geometry are not moved in release 1"
            fixed.append(c.id)  # measured from its rendered state, not its geometry
            continue
        x, y = _num(c.geometry.get("x")), _num(c.geometry.get("y"))
        p = by_id.get(c.parent)
        while p is not None and p.id not in layers and p.id not in roots:
            x, y = x + _num(p.geometry.get("x")), y + _num(p.geometry.get("y"))
            p = by_id.get(p.parent)
        absolute[c.id] = (x, y, _num(c.geometry.get("width")), _num(c.geometry.get("height")))
        if "group" in c.style:
            continue  # a container is not double-counted; its children are the obstacles
        if "text" in c.style:
            problem = _label_problem(c, layers)
            if not problem:
                movable.append(c.id)
                continue
            reasons[c.id] = problem
        fixed.append(c.id)
    for cid, (x, y, w, h) in absolute.items():
        if (cid in movable or cid in fixed) and (x < 0 or y < 0 or x + w > width or y + h > height):
            raise DrawioRefused(
                f"cell {cid!r} lies outside the page (0, 0, {width}, {height}); release 1 edits only inside it"
            )
    if len(movable) + len(fixed) > MAX_OBJECTS:
        raise DrawioRefused(
            f"the page has {len(movable) + len(fixed)} objects; release 1 supports up to {MAX_OBJECTS} objects"
        )
    if len(movable) > MAX_MOVABLE:
        raise DrawioRefused(
            f"the page has {len(movable)} movable labels; release 1 supports up to {MAX_MOVABLE} movable labels"
        )
    return Classified(
        page, tuple(movable), tuple(fixed), tuple(edges), reasons, width, height, absolute
    )
