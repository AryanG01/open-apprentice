"""Teaching scene from one classified, rendered page and a confirmed mapping. A label's scene box is its measured box; the offset
d = box − geometry is stored so a target box can be turned back into geometry (spec 6 arithmetic)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from open_apprentice.drawio.classify import Classified
from open_apprentice.drawio.parse import DrawioRefused
from open_apprentice.drawio.render import Box, Rendered

NODE_TOLERANCE = Fraction(1, 2)


@dataclass(frozen=True)
class DrawioScene:
    scene: dict
    offsets: dict[str, tuple[Fraction, Fraction]]
    movable: tuple[str, ...]
    demoted: dict[str, str]


def _obj(cid: str, kind: str, b: Box, role: str = "", attached: str = "") -> dict:
    return {
        "id": cid,
        "kind": kind,
        "role": role,
        "attached": attached,
        "x": b.x,
        "y": b.y,
        "w": b.w,
        "h": b.h,
    }


def build_scene(c: Classified, r: Rendered, mapping: dict[str, tuple[str, str]]) -> DrawioScene:
    objects: list[dict] = []
    offsets: dict[str, tuple[Fraction, Fraction]] = {}
    movable: list[str] = []
    demoted: dict[str, str] = {}
    for cid in c.fixed:
        if cid in r.nodes:
            state, element, stroke = r.nodes[cid]
            if element is not None:
                err = max(
                    abs(state.x - element.x),
                    abs(state.y - element.y),
                    abs(state.x + state.w - element.x - element.w),
                    abs(state.y + state.h - element.y - element.h),
                )
                if err > NODE_TOLERANCE + stroke / 2:
                    raise DrawioRefused(
                        f"cell {cid!r}: its rendered shape disagrees with its geometry by {float(err):.2f} units"
                    )
            objects.append(_obj(cid, "obstacle" if cid in c.reasons else "node", state))
        elif cid in r.labels:
            objects.append(_obj(cid, "obstacle", r.labels[cid][0]))
        else:
            raise DrawioRefused(
                f"cell {cid!r} could not be measured, so labels cannot be placed safely"
            )
    for cid in c.movable:
        if cid not in r.labels:
            raise DrawioRefused(f"label {cid!r} could not be measured")
        box, lines = r.labels[cid]
        if lines > 1:
            demoted[cid] = "renders on more than one line with the bundled font"
            objects.append(_obj(cid, "obstacle", box))
            continue
        if cid not in mapping:
            raise ValueError(f"label {cid!r} has no confirmed mapping")
        node_id, role = mapping[cid]
        gx, gy = c.absolute[cid][:2]
        offsets[cid] = (box.x - gx, box.y - gy)
        movable.append(cid)
        objects.append(_obj(cid, "label", box, role, node_id))
    for o in objects:
        if o["x"] < 0 or o["y"] < 0 or o["x"] + o["w"] > c.width or o["y"] + o["h"] > c.height:
            raise DrawioRefused(
                f"cell {o['id']!r} renders outside the page (0, 0, {c.width}, {c.height})"
            )
    return DrawioScene(
        {"objects": objects, "canvas": {"w": c.width, "h": c.height}},
        offsets,
        tuple(movable),
        demoted,
    )
