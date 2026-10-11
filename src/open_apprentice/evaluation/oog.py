"""Out-of-grammar battery (development only): badge rules the bounded symbolic search CANNOT express.

The enumerator's grammar is `corner x inset-expression-of-card-WIDTH`. These rules depend on card height, centre the badge, or resize it, so a search-only
learner must fail or abstain on them; any success is the model's. Authored by us, evaluator-side: the learner never sees a rule, a name or a template label.
Purpose: test whether the model adds value where search cannot (decisions #46 left that open).
"""

from __future__ import annotations

from fractions import Fraction

from open_apprentice.concepts.rules import evaluate_rule, validate_rule

CARD, PROTO = {"ref": "objects.0"}, {"ref": "objects.1"}


def _op(name: str, *args):
    return {"op": name, "args": list(args)}


def _get(o, f):
    return _op("get", o, f)


def _rat(s: str):
    return {"rat": s}


def _clone(x, y, **size):
    return {
        "op": "emit_target",
        "kind": "clone_place",
        "proto": PROTO,
        "symbol": "badge",
        "x": x,
        "y": y,
        **size,
    }


def _top_right(margin):
    x = _op(
        "sub",
        _op("add", _get(CARD, "x"), _get(CARD, "w")),
        _op("add", {"ref": "locals.m"}, _get(PROTO, "w")),
    )
    return [
        {"op": "let", "name": "m", "value": margin},
        _clone(x, _op("add", _get(CARD, "y"), {"ref": "locals.m"})),
    ]


_CENTER_X = _op(
    "add", _get(CARD, "x"), _op("div", _op("sub", _get(CARD, "w"), _get(PROTO, "w")), 2)
)


def _sized_top_right():
    size = _op("mul", _get(CARD, "h"), _rat("1/4"))
    x = _op("sub", _op("add", _get(CARD, "x"), _get(CARD, "w")), _op("add", 12, size))
    return [_clone(x, _op("add", _get(CARD, "y"), 12), w=size, h=size)]


RULES: list[tuple[str, list]] = [
    ("inset is 10% of card height", _top_right(_op("mul", _get(CARD, "h"), _rat("1/10")))),
    (
        "inset is 10% of the shorter side",
        _top_right(_op("mul", _op("min", _get(CARD, "w"), _get(CARD, "h")), _rat("1/10"))),
    ),
    (
        "centred on the top edge, straddling it",
        [_clone(_CENTER_X, _op("sub", _get(CARD, "y"), _op("div", _get(PROTO, "h"), 2)))],
    ),
    (
        "bottom centre, 8 px above the edge",
        [
            _clone(
                _CENTER_X,
                _op(
                    "sub",
                    _op("add", _get(CARD, "y"), _get(CARD, "h")),
                    _op("add", _get(PROTO, "h"), 8),
                ),
            )
        ],
    ),
    ("top-right inset 12, badge sized to a quarter of card height", _sized_top_right()),
    (
        "inset is one twentieth of width plus height",
        _top_right(_op("div", _op("add", _get(CARD, "w"), _get(CARD, "h")), 20)),
    ),
]


def demonstration(index: int) -> dict:
    """A neutral demonstration (card and prototype only) with the rule's resulting state, in the same shape the benchmark episodes use."""
    rule = RULES[index][1]
    validate_rule(rule)
    objs = [
        {
            "id": "card0",
            "x": Fraction(100),
            "y": Fraction(100),
            "w": Fraction(160),
            "h": Fraction(80),
        },
        {"id": "proto", "x": Fraction(0), "y": Fraction(0), "w": Fraction(20), "h": Fraction(20)},
    ]
    canvas = {"w": Fraction(800), "h": Fraction(600)}
    after = {o["id"]: {k: o[k] for k in ("x", "y", "w", "h")} for o in objs}
    after.update(evaluate_rule(rule, objs, canvas))
    return {"scene": {"objects": objs, "canvas": canvas}, "after": after}
