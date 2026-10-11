"""Rule ASTs used ONLY as test fixtures / evaluator-side references (origin=fixture).
The live learner generates its own candidates; nothing here is ever passed to it."""

from typing import Any

R = lambda p: {"ref": p}


def op(name, *a):
    return {"op": name, "args": list(a)}


def get(o, f):
    return op("get", o, f)


RAT = lambda s: {"rat": s}


def badge_rule(margin: Any) -> list[dict]:
    """objects[0]=card, objects[1]=badge prototype. Badge goes in the card's top-right, inset by `margin`."""
    card, proto = R("objects.0"), R("objects.1")
    return [
        {"op": "let", "name": "m", "value": margin},
        {
            "op": "emit_target",
            "kind": "clone_place",
            "proto": proto,
            "symbol": "badge",
            "x": op(
                "sub",
                op("add", get(card, "x"), get(card, "w")),
                op("add", R("locals.m"), get(proto, "w")),
            ),
            "y": op("add", get(card, "y"), R("locals.m")),
        },
    ]


CONST_MARGIN = badge_rule(12)
PROP_MARGIN = lambda: badge_rule(op("mul", get(R("objects.0"), "w"), RAT("2/25")))  # 8% of width
CLAMPED_MARGIN = lambda: badge_rule(
    op("min", 24, op("max", 8, op("mul", get(R("objects.0"), "w"), RAT("2/25"))))
)


def gap_rule(gap: Any = 24, left: Any = 80, top: Any = 120) -> list[dict]:
    """Equal EDGE gaps."""
    return [
        {"op": "let", "name": "cursor", "value": left},
        {
            "op": "for_each",
            "var": "o",
            "body": [
                {
                    "op": "emit_target",
                    "kind": "move_existing",
                    "target": R("locals.o"),
                    "x": R("locals.cursor"),
                    "y": top,
                },
                {
                    "op": "let",
                    "name": "cursor",
                    "value": op("add", R("locals.cursor"), op("add", get(R("locals.o"), "w"), gap)),
                },
            ],
            "over": R("objects"),
        },
    ]


def center_spacing_rule(pitch: Any = 100, left: Any = 80, top: Any = 120) -> list[dict]:
    """Equal CENTER-to-CENTER spacing: coincides with equal edge gaps when widths are equal."""
    return [
        {
            "op": "let",
            "name": "c",
            "value": op("add", left, op("div", get(R("objects.0"), "w"), 2)),
        },
        {
            "op": "for_each",
            "var": "o",
            "body": [
                {
                    "op": "emit_target",
                    "kind": "move_existing",
                    "target": R("locals.o"),
                    "x": op("sub", R("locals.c"), op("div", get(R("locals.o"), "w"), 2)),
                    "y": top,
                },
                {"op": "let", "name": "c", "value": op("add", R("locals.c"), pitch)},
            ],
            "over": R("objects"),
        },
    ]
