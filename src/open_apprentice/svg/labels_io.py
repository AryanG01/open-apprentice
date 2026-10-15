"""Real-file path for label placement: SVG <-> the scene the learner sees, and a learned rule -> typed patch.

Nodes are `<rect id=...>` (not the full-canvas background); labels are `<text id=... data-for=NODE data-role=ROLE>` with plain
numeric x/y. Label boxes are ESTIMATED (width = 0.55 * font-size * characters, top = baseline - 0.8 * font-size, height =
font-size): the model-free path has no font metrics; rendered measurement (the engine's getBBox lane) is a separate check.
Anything else (tspans, transforms other than translate, missing ids) is listed as not editable, never guessed at.
Edits touch only the `x`/`y` of label <text> start tags, byte-exactly (svg/patch.py).
"""

from __future__ import annotations

from fractions import Fraction

from open_apprentice.concepts.rules import RuleError, evaluate_rule
from open_apprentice.svg.document import Document, parse_document, parse_number
from open_apprentice.svg.patch import Op, Patch, apply_patch, fmt

CHAR_EM, ASCENT = Fraction(55, 100), Fraction(8, 10)


class LabelsNotApplicable(ValueError):
    pass


def _text_of(doc: Document, e) -> str | None:
    raw = doc.text.encode("utf-8")
    close = raw.find(b"</text>", e.end)
    body = raw[e.end : close].decode("utf-8") if close >= 0 else ""
    return None if "<" in body or close < 0 else body.strip()


def _canvas(doc: Document) -> dict:
    a = doc.elements[0].attrs
    return {
        "w": Fraction(parse_number(a.get("width")) or 800),
        "h": Fraction(parse_number(a.get("height")) or 600),
    }


def _q(v: float) -> Fraction:
    return Fraction(v).limit_denominator(1000)


def scene_from_svg(text: str) -> tuple[dict, dict]:
    """Returns (scene, report). scene = {objects, canvas} in the learner's format; report lists what was skipped and why."""
    doc = parse_document(text)
    canvas, skipped, nodes, labels = _canvas(doc), [], [], []
    for e in doc.elements:
        ident = e.attrs.get("id")
        if e.in_defs or ident is None:
            continue
        off, why = doc.world_offset(e)
        if e.tag == "rect":
            x, y, w, h = (
                parse_number(e.attrs.get(k, "0" if k in "xy" else None))
                for k in ("x", "y", "width", "height")
            )
            if None in (x, y, w, h) or off is None:
                skipped.append((ident, why or "x, y, width and height must be plain numbers"))
                continue
            if w * h >= 0.9 * float(canvas["w"] * canvas["h"]):
                continue  # the background
            nodes.append(
                {
                    "id": ident,
                    "kind": "node",
                    "role": "",
                    "attached": "",
                    "x": _q(x + off[0]),
                    "y": _q(y + off[1]),
                    "w": _q(w),
                    "h": _q(h),
                }
            )
        elif e.tag == "text":
            x, y, fs = (
                parse_number(e.attrs.get("x")),
                parse_number(e.attrs.get("y")),
                parse_number(e.attrs.get("font-size")),
            )
            body = _text_of(doc, e)
            if None in (x, y, fs) or off is None or not body or "data-for" not in e.attrs:
                skipped.append(
                    (ident, why or "needs numeric x, y, font-size, plain text and data-for")
                )
                continue
            f = _q(fs)
            labels.append({"id": ident, "kind": "label", "role": e.attrs.get("data-role", "note"), "attached": e.attrs["data-for"],
                           "x": _q(x + off[0]), "y": _q(y + off[1]) - ASCENT * f, "w": CHAR_EM * f * len(body), "h": f, "_fs": f})  # fmt: skip
    ids = {n["id"] for n in nodes}
    for lab in labels:
        if lab["attached"] not in ids:
            raise LabelsNotApplicable(
                f"label {lab['id']!r} is attached to {lab['attached']!r}, which is not a box in this file"
            )
    scene = {
        "objects": nodes + [{k: v for k, v in lab.items() if k != "_fs"} for lab in labels],
        "canvas": canvas,
    }
    return scene, {
        "nodes": len(nodes),
        "labels": len(labels),
        "not_editable": skipped,
        "font_sizes": {lab["id"]: lab["_fs"] for lab in labels},
    }


def patch_for_rule(text: str, rule: list) -> tuple[Patch, dict, dict]:
    """Evaluate the learned rule on the file's scene and write the label moves as a typed patch. Returns (patch, scene, targets)."""
    doc = parse_document(text)
    scene, rep = scene_from_svg(text)
    try:
        state = evaluate_rule(rule, scene["objects"], scene["canvas"])
    except RuleError as err:
        raise LabelsNotApplicable(f"the rule cannot be evaluated here: {err}") from err
    ops, targets = [], {}
    for o in scene["objects"]:
        if o["kind"] != "label":
            continue
        g, e = state[o["id"]], doc.get(o["id"])
        if (g["w"], g["h"]) != (o["w"], o["h"]):
            raise LabelsNotApplicable(f"the rule resizes {o['id']!r}; this lane only moves labels")
        if (g["x"], g["y"]) == (o["x"], o["y"]):
            continue
        targets[o["id"]] = (g["x"], g["y"])
        off, _ = doc.world_offset(e)
        new = {
            "x": float(g["x"]) - off[0],
            "y": float(g["y"] + ASCENT * rep["font_sizes"][o["id"]]) - off[1],
        }
        for attr, val in new.items():
            ops.append(
                Op(element=o["id"], attribute=attr, expected_old=e.attrs.get(attr), new=fmt(val))
            )
    for o in scene["objects"]:
        if o["kind"] == "node" and (state[o["id"]]["x"], state[o["id"]]["y"]) != (o["x"], o["y"]):
            raise LabelsNotApplicable("the rule moves a box; this lane only moves labels")
    return Patch(doc_hash=doc.hash, ops=ops), scene, targets


def apply_rule_to_svg(text: str, rule: list) -> dict:
    patch, scene, targets = patch_for_rule(text, rule)
    res = apply_patch(text, patch) if patch.ops else None
    return {
        "text": res.text if res else text,
        "scene": scene,
        "targets": targets,
        "patch": patch,
        "result": res,
    }
