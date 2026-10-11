"""Editable SVG export of an executed layout (spec 17.7: the primary completion action).

The file is plain, script-free SVG 1.1: one <rect> per scene object with its original id, grouped by role, geometry exactly as the
ENGINE reported it (not recomputed). Provenance travels inside the file as <metadata> so a layout handed to someone else says which rule,
backend and binding produced it and what the independent verifier concluded. Nothing here executes or fetches anything.
"""

from __future__ import annotations

import re
from typing import Any
from xml.sax.saxutils import quoteattr

_ID = re.compile(r"[^A-Za-z0-9_.:-]")
_FILL = {"card": "#dfe5d6", "prototype": "#ffffff", "badge": "#76b900", "object": "#cfd6e4"}
_STROKE = {"card": "#8b987a", "prototype": "#8b987a", "badge": "#3d7a00", "object": "#7a869a"}


def safe_id(raw: str) -> str:
    """XML ids must start with a letter or underscore; anything outside the safe set is replaced, never passed through."""
    s = _ID.sub("_", str(raw))[:80] or "node"
    return s if re.match(r"[A-Za-z_]", s) else f"n_{s}"


def _num(v: Any) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:.4f}".rstrip("0").rstrip(".")


def build_svg(boxes: list[dict], canvas: dict, meta: dict[str, Any]) -> str:
    """boxes: [{id,x,y,w,h,role}] in canvas coordinates. meta: flat string-able provenance fields."""
    cw, ch = _num(canvas["w"]), _num(canvas["h"])
    seen: set[str] = set()
    groups: dict[str, list[str]] = {}
    for b in boxes:
        ident = safe_id(b["id"])
        while ident in seen:  # ids stay unique even if the input collides after sanitising
            ident += "_"
        seen.add(ident)
        role = b.get("role", "object") if b.get("role") in _FILL else "object"
        groups.setdefault(role, []).append(
            f'    <rect id={quoteattr(ident)} x="{_num(b["x"])}" y="{_num(b["y"])}" width="{_num(b["w"])}" height="{_num(b["h"])}" '
            f'fill="{_FILL[role]}" stroke="{_STROKE[role]}" stroke-width="1"/>'
        )
    body = []
    for role in ("card", "object", "prototype", "badge"):
        if role in groups:
            body.append(
                f'  <g id="layer_{role}" data-role="{role}">\n'
                + "\n".join(groups[role])
                + "\n  </g>"
            )
    meta_lines = "\n".join(
        f"    <oa:{safe_id(k)}>{_esc(str(v))}</oa:{safe_id(k)}>" for k, v in meta.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:oa="https://open-apprentice.invalid/ns" version="1.1" '
        f'width="{cw}" height="{ch}" viewBox="0 0 {cw} {ch}">\n'
        "  <title>Open Apprentice layout</title>\n"
        "  <desc>Editable layout produced by a learned rule. Geometry is what the graphics engine reported after execution.</desc>\n"
        f"  <metadata>\n{meta_lines}\n  </metadata>\n" + "\n".join(body) + "\n</svg>\n"
    )


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
