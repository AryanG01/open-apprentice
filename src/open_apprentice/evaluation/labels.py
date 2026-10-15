"""Label-placement task family for the redesign experiment (evaluator side).

A scene is nodes (fixed rectangles) plus labels, each attached to one node. The hidden intent moves labels relative to
their node. Three intents, all with exact rational arithmetic:

  right        every label goes right of its node, centre-aligned vertically, with gap g
  right_else_below   right if that fits inside the canvas and overlaps nothing else, otherwise below (centre-aligned)
  notes_only   like `right`, but only labels with role "note"; role "warning" labels never move

`intended_after` is the ORACLE: plain Python, deliberately not the rule evaluator, so a rule written in the language is
judged against an implementation that shares no code with it. `rule_for` builds the same behaviour as a rule AST for
tests and the symbolic-free reference; it is never shown to a learner. Everything here is evaluator code: agent-visible
modules must not import it.
"""

from __future__ import annotations

import random
from fractions import Fraction as F
from dataclasses import dataclass
from typing import Any

GAP_DEFAULT = F(12)
CANVAS = {"w": F(1200), "h": F(800)}
INTENTS = ("right", "right_else_below", "notes_only")
CELL_W, CELL_H = F(190), F(170)
COLS, ROWS = 5, 4


def _box(o: dict) -> tuple[F, F, F, F]:
    return F(o["x"]), F(o["y"]), F(o["w"]), F(o["h"])


def overlaps(a: tuple, b: tuple) -> bool:
    """Strict positive-area overlap; edge contact is not overlap."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def inside(box: tuple, canvas: dict = CANVAS) -> bool:
    x, y, w, h = box
    return x >= 0 and y >= 0 and x + w <= canvas["w"] and y + h <= canvas["h"]


def pose(side: str, anchor: dict, label: dict, gap: F) -> tuple[F, F]:
    xa, ya, wa, ha = _box(anchor)
    wl, hl = F(label["w"]), F(label["h"])
    if side == "right":
        return xa + wa + gap, ya + (ha - hl) / 2
    if side == "below":
        return xa + (wa - wl) / 2, ya + ha + gap
    raise ValueError(side)


@dataclass(frozen=True)
class Spec:
    """A placement behaviour: try `primary`; if blocked (off canvas or overlapping another object) use `fallback`
    (None = place there regardless); only labels in `scope` move ("all" or "notes")."""

    primary: str = "right"
    fallback: str | None = None
    scope: str = "all"
    gap: F = F(12)


NAMED = {
    "right": Spec("right", None, "all"),
    "right_else_below": Spec("right", "below", "all"),
    "notes_only": Spec("right", None, "notes"),
}


def _blocked(box: tuple, lab: dict, anchor: dict, objs: list[dict], canvas: dict = CANVAS) -> bool:
    return not inside(box, canvas) or any(
        overlaps(box, _box(o)) for o in objs if o["id"] not in (lab["id"], anchor["id"])
    )


def oracle(spec: Spec, scene: dict) -> dict[str, tuple[F, F]]:
    """Final (x, y) of every label the behaviour moves. Labels not in the result must stay where they are."""
    objs = scene["objects"]
    byid = {o["id"]: o for o in objs}
    out: dict[str, tuple[F, F]] = {}
    for lab in objs:
        if lab["kind"] != "label" or (spec.scope == "notes" and lab["role"] != "note"):
            continue
        anchor = byid[lab["attached"]]
        px, py = pose(spec.primary, anchor, lab, spec.gap)
        if spec.fallback and _blocked(
            (px, py, F(lab["w"]), F(lab["h"])), lab, anchor, objs, scene["canvas"]
        ):
            px, py = pose(spec.fallback, anchor, lab, spec.gap)
        out[lab["id"]] = (px, py)
    return out


def intended_after(intent: str, gap: F, scene: dict) -> dict[str, tuple[F, F]]:
    s = NAMED[intent]
    return oracle(Spec(s.primary, s.fallback, s.scope, gap), scene)


def _n(f: F) -> Any:
    return int(f) if f.denominator == 1 else {"rat": f"{f.numerator}/{f.denominator}"}


def _op(name: str, *args: Any) -> dict:
    return {"op": name, "args": list(args)}


def _get(o: Any, field: str) -> dict:
    return _op("get", o, field)


def rule_for_spec(spec: Spec) -> list:
    """Any catalogue behaviour written in the rule language. Test/reference use only; never shown to a learner."""
    g = _n(spec.gap)
    o = {"ref": "locals.o"}
    a = {"ref": "locals.a"}

    def local(name: str) -> dict:
        return {"ref": f"locals.{name}"}

    def pose_xy(side: str) -> tuple[Any, Any]:
        if side == "right":
            return (
                _op("add", _op("add", _get(a, "x"), _get(a, "w")), g),
                _op("add", _get(a, "y"), _op("div", _op("sub", _get(a, "h"), _get(o, "h")), 2)),
            )
        return (
            _op("add", _get(a, "x"), _op("div", _op("sub", _get(a, "w"), _get(o, "w")), 2)),
            _op("add", _op("add", _get(a, "y"), _get(a, "h")), g),
        )

    def move(x: Any, y: Any) -> dict:
        return {"op": "emit_target", "kind": "move_existing", "target": o, "x": x, "y": y}

    cond = _op("eq", _get(o, "kind"), "label")
    if spec.scope == "notes":
        cond = _op("and", cond, _op("eq", _get(o, "role"), "note"))
    body: list[Any] = [{"op": "let", "name": "a", "value": _op("by_id", _get(o, "attached"))}]
    px, py = pose_xy(spec.primary)
    if spec.fallback is None:
        body.append(move(px, py))
    else:
        fx, fy = pose_xy(spec.fallback)
        p = local("p")
        hit_one = _op(
            "and",
            _op("ne", _get(p, "id"), _get(o, "id")),
            _op("ne", _get(p, "id"), _get(a, "id")),
            _op("lt", local("px"), _op("add", _get(p, "x"), _get(p, "w"))),
            _op("lt", _get(p, "x"), _op("add", local("px"), _get(o, "w"))),
            _op("lt", local("py"), _op("add", _get(p, "y"), _get(p, "h"))),
            _op("lt", _get(p, "y"), _op("add", local("py"), _get(o, "h"))),
        )
        off_canvas = _op(
            "or",
            _op("lt", local("px"), 0),
            _op("lt", local("py"), 0),
            _op("gt", _op("add", local("px"), _get(o, "w")), {"ref": "canvas.w"}),
            _op("gt", _op("add", local("py"), _get(o, "h")), {"ref": "canvas.h"}),
        )
        body += [
            {"op": "let", "name": "px", "value": px},
            {"op": "let", "name": "py", "value": py},
            {"op": "let", "name": "blocked", "value": off_canvas},
            {
                "op": "for_each",
                "over": {"ref": "objects"},
                "var": "p",
                "body": [
                    {"op": "let", "name": "blocked", "value": _op("or", local("blocked"), hit_one)}
                ],
            },
            {
                "op": "if",
                "cond": local("blocked"),
                "then": [move(fx, fy)],
                "else": [move(local("px"), local("py"))],
            },
        ]
    return [
        {
            "op": "for_each",
            "over": {"ref": "objects"},
            "var": "o",
            "body": [{"op": "if", "cond": cond, "then": body}],
        }
    ]


def rule_for(intent: str, gap: F) -> list:
    s = NAMED[intent]
    return rule_for_spec(Spec(s.primary, s.fallback, s.scope, gap))


def make_scene(
    seed: int, n_nodes: int, warnings: int = 0, crowd: bool = True, canvas_w: int = 1200
) -> dict:
    """A document: nodes on a jittered grid (denser rows make the right-hand pose collide), one label per node."""
    rng = random.Random(seed)
    cols = COLS if canvas_w >= 1200 else 3
    cell_w = (
        CELL_W if canvas_w >= 1200 else F(canvas_w - 190, 2)
    )  # narrow canvas: last column ends near the right edge
    cells = [(c, r) for c in range(cols) for r in range(ROWS)]
    n_nodes = min(n_nodes, len(cells))
    rng.shuffle(cells)
    objs: list[dict] = []
    for i, (c, r) in enumerate(cells[:n_nodes]):
        w, h = rng.choice((70, 90, 100, 110)), rng.choice((40, 50, 60))
        jx, jy = rng.randrange(0, 20), rng.randrange(0, 30)
        x = 30 + c * (cell_w if crowd else cell_w + 40) + jx
        y = 30 + r * CELL_H + jy
        objs.append(
            {
                "id": f"n{i}",
                "kind": "node",
                "role": "",
                "attached": "",
                "x": int(x),
                "y": int(y),
                "w": w,
                "h": h,
            }
        )
    warn_ids = set(rng.sample(range(n_nodes), min(warnings, n_nodes)))
    for i in range(n_nodes):
        n = objs[i]
        w, h = rng.choice((56, 80, 110)), rng.choice((16, 20))
        objs.append(
            {
                "id": f"l{i}",
                "kind": "label",
                "role": "warning" if i in warn_ids else "note",
                "attached": n["id"],
                "x": n["x"],
                "y": n["y"] + n["h"] + 4,
                "w": w,
                "h": h,
            }
        )
    return {"objects": objs, "canvas": {"w": canvas_w, "h": 800}}


def apply_oracle(scene: dict, targets: dict[str, tuple[F, F]]) -> dict:
    new = [dict(o) for o in scene["objects"]]
    for o in new:
        if o["id"] in targets:
            o["x"], o["y"] = targets[o["id"]]
    return {"objects": new, "canvas": scene["canvas"]}


def _layout_violations(objs: dict[str, dict], moved: Any, canvas: dict = CANVAS) -> list[str]:
    out = []
    for i in moved:
        box = _box(objs[i])
        if not inside(box, canvas):
            out.append(f"{i}: leaves the canvas")
        for j, other in objs.items():
            if j not in (i, objs[i]["attached"]) and overlaps(box, _box(other)):
                out.append(f"{i}: overlaps {j}")
    return out


def check_after(
    before: dict, after: dict, expected: dict[str, tuple[F, F]], tol: F = F(1, 2)
) -> dict:
    """Independent outcome checks on final geometry. Axes are reported separately, never merged.

    intent: every label the intent moves is within `tol` of its oracle position.
    preservation: nothing else changed (position, size, kind, role, attachment, count) and moved labels kept their size.
    layout: moved labels stay inside the canvas and overlap nothing, EXCEPT problems the intended behaviour itself has
    (a behaviour that can only fit a label by overlapping is not blamed on the executor).
    """
    b = {o["id"]: o for o in before["objects"]}
    a = {o["id"]: o for o in after["objects"]}
    problems: dict[str, list[str]] = {"intent": [], "preservation": [], "layout": []}
    if set(b) != set(a):
        problems["preservation"].append("object set changed")
        return {k: not v for k, v in problems.items()} | {"problems": problems}
    for i, o in a.items():
        ob = b[i]
        static = ("kind", "role", "attached", "w", "h")
        if any(o[k] != ob[k] for k in static):
            problems["preservation"].append(f"{i}: non-position field changed")
        if i in expected:
            ex, ey = expected[i]
            if abs(F(o["x"]) - ex) > tol or abs(F(o["y"]) - ey) > tol:
                problems["intent"].append(f"{i}: at ({o['x']},{o['y']}), expected ({ex},{ey})")
        elif (o["x"], o["y"]) != (ob["x"], ob["y"]):
            problems["preservation"].append(f"{i}: moved but the intent leaves it alone")
    wanted = {o["id"]: o for o in apply_oracle(before, expected)["objects"]}
    problems["layout"] = [
        v
        for v in _layout_violations(a, expected, after["canvas"])
        if v not in _layout_violations(wanted, expected, after["canvas"])
    ]
    return {k: not v for k, v in problems.items()} | {"problems": problems}
