"""Shared layout check for every commit path (spec 7 "convention forcing overlap or off-canvas: refuse to apply").
The same geometry as the evaluator's layout check, written here because teaching may not import the evaluator."""

from __future__ import annotations

from fractions import Fraction

from open_apprentice.teaching.step import run_output


def _box(o: dict) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    return Fraction(o["x"]), Fraction(o["y"]), Fraction(o["w"]), Fraction(o["h"])


def _overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def layout_problems(rule: list, scenes: dict[str, dict]) -> list[str]:
    """Labels the rule moves off the page, or onto any object other than the label and its own node, on each scene.
    Positions are the rule's final layout; edge contact is not overlap."""
    out: list[str] = []
    for sid in sorted(scenes):
        scene = scenes[sid]
        moved = run_output(rule, scene) or {}
        objs = {o["id"]: dict(o) for o in scene["objects"]}
        changed = [k for k, (x, y) in moved.items() if (x, y) != (objs[k]["x"], objs[k]["y"])]
        for k, (x, y) in moved.items():
            objs[k]["x"], objs[k]["y"] = x, y
        cw, ch = Fraction(scene["canvas"]["w"]), Fraction(scene["canvas"]["h"])
        for k in sorted(changed):
            b = _box(objs[k])
            if b[0] < 0 or b[1] < 0 or b[0] + b[2] > cw or b[1] + b[3] > ch:
                out.append(f"{sid}: {k} leaves the page")
                continue
            hit = next(
                (
                    j
                    for j in sorted(objs)
                    if j not in (k, objs[k]["attached"]) and _overlap(b, _box(objs[j]))
                ),
                None,
            )
            if hit is not None:
                out.append(f"{sid}: {k} overlaps {hit}")
    return out


HAND_PLACED = ("demonstration", "requested_demonstration", "correction")


def hand_placed(items: list) -> dict[str, dict]:
    """Documents where the person placed labels by hand: the demonstrated convention. Choices and preview approvals
    are judgements between shown outputs (a generated obstacle probe may make the right answer collide).
    """
    return {i.scene_id: i.scene for i in items if i.source in HAND_PLACED}


def refusal(problems: list[str]) -> str:
    return "refusing to apply: " + "; ".join(problems[:3])
