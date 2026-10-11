"""Apply a LEARNED rule to a real SVG by producing a typed patch (no model involved).

The badge rule (objects[0] = card, objects[1] = badge prototype) is evaluated with exact rational arithmetic on the WORLD geometry of an existing card element and an
existing badge element. The badge is MOVED (set_attribute x/y, and width/height only if the rule says so) to where the rule puts it; nothing is inserted or deleted.
World geometry accounts for translate() transforms on the element and its ancestors; any other transform makes an element non-editable and the request is refused.
"""

from __future__ import annotations

from fractions import Fraction

from open_apprentice.concepts.rules import RuleError, evaluate_rule
from open_apprentice.svg.document import Document, parse_number
from open_apprentice.svg.patch import Op, Patch, fmt


class RuleNotApplicable(ValueError):
    pass


def _geometry(doc: Document, ident: str) -> tuple[dict, tuple[float, float]]:
    if ident not in doc.by_id:
        raise RuleNotApplicable(f"no element with id {ident!r}")
    e = doc.get(ident)
    if e.tag != "rect" or e.in_defs:
        raise RuleNotApplicable(f"{ident!r} is not an editable rectangle")
    x, y, w, h = (
        parse_number(e.attrs.get(k, "0" if k in "xy" else None))
        for k in ("x", "y", "width", "height")
    )
    if None in (x, y, w, h):
        raise RuleNotApplicable(f"{ident!r}: x, y, width and height must be plain numbers")
    off, why = doc.world_offset(e)
    if off is None:
        raise RuleNotApplicable(f"{ident!r}: {why}")
    return {"x": x + off[0], "y": y + off[1], "w": w, "h": h}, off


def _canvas(doc: Document) -> dict:
    root = doc.elements[0].attrs
    return {
        "w": Fraction(parse_number(root.get("width")) or 800),
        "h": Fraction(parse_number(root.get("height")) or 600),
    }


def patch_for_pairs(
    doc: Document, rule: list, pairs: list[tuple[str, str]]
) -> tuple[Patch, list[dict]]:
    """pairs: [(card_id, badge_id)]. Returns the patch and, per pair, the expected WORLD geometry the rule requires (for independent verification)."""
    ops: list[Op] = []
    expected: list[dict] = []
    used: set[str] = set()
    for card_id, badge_id in pairs:
        if badge_id in used or badge_id == card_id:
            raise RuleNotApplicable(f"{badge_id!r} is used more than once")
        used.add(badge_id)
        card, _ = _geometry(doc, card_id)
        badge, off = _geometry(doc, badge_id)
        objects = [{"id": "card", **{k: Fraction(v).limit_denominator(10_000) for k, v in card.items()}},
                   {"id": "proto", **{k: Fraction(v).limit_denominator(10_000) for k, v in badge.items()}}]  # fmt: skip
        try:
            out = evaluate_rule(rule, objects, _canvas(doc))
        except RuleError as e:
            raise RuleNotApplicable(f"the rule cannot be evaluated here: {e}") from e
        emitted = [(k, g) for k, g in out.items() if k not in ("card", "proto")]
        if len(emitted) != 1:
            raise RuleNotApplicable("this lane applies rules that place exactly one badge per card")
        g = emitted[0][1]
        wx, wy = float(g["x"]), float(g["y"])
        e = doc.get(badge_id)
        want = {"x": wx - off[0], "y": wy - off[1]}
        if "w" in g and float(g["w"]) != badge["w"]:
            want["width"] = float(g["w"])
        if "h" in g and float(g["h"]) != badge["h"]:
            want["height"] = float(g["h"])
        for attr, val in want.items():
            current = e.attrs.get(attr)
            if current is None or abs((parse_number(current) or 0.0) - val) > 1e-6:
                ops.append(Op(element=badge_id, attribute=attr, expected_old=current, new=fmt(val)))
        expected.append(
            {
                "card": card_id,
                "badge": badge_id,
                "world": {
                    "x": wx,
                    "y": wy,
                    "width": float(g.get("w", badge["w"])),
                    "height": float(g.get("h", badge["h"])),
                },
            }
        )
    return Patch(doc_hash=doc.hash, ops=ops), expected
