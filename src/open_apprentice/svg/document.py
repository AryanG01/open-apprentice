"""Element inventory and byte-exact attribute editing for a VALIDATED SVG document.

Editing works on the ORIGINAL BYTES: each start tag is located with the XML parser's own byte offsets, and only the targeted attribute inside that tag is
replaced or inserted. Everything else (comments, whitespace, ordering, other attributes, inert vector detail) is untouched, so "no unrelated changes" is a byte
comparison, not a hope. Geometry is computed by composing translate-only transforms; anything else makes an element non-editable (and the reason is reported).
"""

from __future__ import annotations

import hashlib
import re
import xml.parsers.expat as expat
from dataclasses import dataclass, field
from typing import Optional

from open_apprentice.svg.safety import local, validate_svg

NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_NUM_ONLY = re.compile(rf"^\s*({NUM})\s*(?:px)?\s*$")
_TRANSLATE = re.compile(rf"^\s*translate\(\s*({NUM})(?:[\s,]+({NUM}))?\s*\)\s*$")


def doc_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_number(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    m = _NUM_ONLY.match(v)
    return float(m.group(1)) if m else None


def parse_translate(v: Optional[str]) -> Optional[tuple[float, float]]:
    """None -> (0, 0) is the caller's job; this returns None for any transform that is not a lone translate()."""
    if v is None:
        return (0.0, 0.0)
    m = _TRANSLATE.match(v)
    return (float(m.group(1)), float(m.group(2) or 0.0)) if m else None


@dataclass
class Element:
    index: int
    tag: str
    attrs: dict[str, str]
    parent: Optional[int]
    start: int  # byte offset of '<'
    end: int  # byte offset just after the start tag's '>'
    in_defs: bool = False
    children: list[int] = field(default_factory=list)


@dataclass
class Document:
    text: str
    elements: list[Element]
    by_id: dict[str, int]
    hash: str

    def get(self, ident: str) -> Element:
        return self.elements[self.by_id[ident]]

    def ancestors(self, e: Element) -> list[Element]:
        out, p = [], e.parent
        while p is not None:
            out.append(self.elements[p])
            p = self.elements[p].parent
        return out

    def world_offset(self, e: Element) -> tuple[Optional[tuple[float, float]], str]:
        """Sum of translate() transforms from the root to this element's PARENT, plus this element's own. (None, reason) if any is unsupported."""
        tx = ty = 0.0
        for a in [e, *self.ancestors(e)]:
            t = parse_translate(a.attrs.get("transform"))
            if t is None:
                return (
                    None,
                    f"<{a.tag}> has a transform other than a plain translate(): {a.attrs.get('transform')!r}",
                )
            tx, ty = tx + t[0], ty + t[1]
        return (tx, ty), ""


def _end_of_start_tag(raw: bytes, start: int) -> int:
    i, quote = start + 1, None
    while i < len(raw):
        c = raw[i : i + 1]
        if quote:
            if c == quote:
                quote = None
        elif c in (b'"', b"'"):
            quote = c
        elif c == b">":
            return i + 1
        i += 1
    raise ValueError("unterminated start tag")


def parse_document(text: str) -> Document:
    validate_svg(text)  # always: nothing is indexed, edited or rendered before it has been accepted
    raw = text.encode("utf-8")
    elements: list[Element] = []
    stack: list[int] = []
    p = expat.ParserCreate(namespace_separator="}")

    def start(name: str, attrs: dict) -> None:
        s = p.CurrentByteIndex
        t = local(name)
        parent = stack[-1] if stack else None
        in_defs = bool(stack) and (elements[stack[-1]].in_defs or elements[stack[-1]].tag == "defs")
        e = Element(
            len(elements),
            t,
            {local(k): v for k, v in attrs.items()},
            parent,
            s,
            _end_of_start_tag(raw, s),
            in_defs,
        )
        elements.append(e)
        if parent is not None:
            elements[parent].children.append(e.index)
        stack.append(e.index)

    p.StartElementHandler = start
    p.EndElementHandler = lambda _n: stack.pop()
    p.Parse(raw, True)
    by_id = {e.attrs["id"]: e.index for e in elements if "id" in e.attrs}
    return Document(text, elements, by_id, doc_hash(text))


# ------------------------------------------------------------------------------------------------- inventory
EDITABLE_TAGS = {"rect"}


def inventory(doc: Document) -> dict:
    items, vector = [], 0
    for e in doc.elements:
        if e.tag in ("rect", "g") and "id" in e.attrs and not e.in_defs:
            row = {
                "id": e.attrs["id"],
                "tag": e.tag,
                "children": [
                    doc.elements[c].attrs.get("id")
                    for c in e.children
                    if "id" in doc.elements[c].attrs
                ],
            }
            if e.tag == "rect":
                x, y, w, h = (
                    parse_number(e.attrs.get(k, "0" if k in "xy" else None))
                    for k in ("x", "y", "width", "height")
                )
                off, why = doc.world_offset(e)
                if None in (x, y, w, h):
                    row.update(
                        editable=False,
                        reason="x, y, width and height must be plain numbers (no %, em or other units)",
                    )
                elif off is None:
                    row.update(editable=False, reason=why)
                else:
                    row.update(
                        editable=True,
                        local={"x": x, "y": y, "width": w, "height": h},
                        world={"x": x + off[0], "y": y + off[1], "width": w, "height": h},
                    )
                row["fill"] = e.attrs.get("fill")
            else:
                row["editable"] = False
                row["reason"] = "groups are listed for context; this lane edits rectangles"
            items.append(row)
        elif e.tag in ("path", "circle", "ellipse", "line", "polyline", "polygon", "text"):
            vector += 1
    root = doc.elements[0]
    return {
        "hash": doc.hash,
        "size": {
            "width": parse_number(root.attrs.get("width")),
            "height": parse_number(root.attrs.get("height")),
            "viewBox": root.attrs.get("viewBox"),
        },
        "elements": items,
        "inert_vector_elements": vector,
        "coverage": {"editable": sum(1 for r in items if r.get("editable")), "listed": len(items)},
    }
