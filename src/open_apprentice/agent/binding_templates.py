"""DECLARED binding-template library for the non-LLM reference (spec 21.11). Hand-written, two entries, published.
Not learned and never counted as learned skills (origin=reference). It exists so the reference can execute and
repair natively without a model; a stronger or weaker library would change the reference's numbers."""

from __future__ import annotations

from open_apprentice.concepts.transfer import BindingOut


def _E(p):
    return {"ref": p}


def _B(o, *a):
    return {"op": o, "args": list(a)}


# T1: trust the documented contract - place everything with move_node / clone_node.
DIRECT = [
    {
        "op": "for_each",
        "var": "t",
        "over": _E("inputs.targets"),
        "body": [
            {
                "op": "if",
                "cond": _B("eq", _E("locals.t.kind"), "clone_place"),
                "then": [
                    {
                        "op": "call",
                        "tool": "clone_node",
                        "args": {"node_id": _E("locals.t.proto"), "new_id": _E("locals.t.symbol")},
                    },
                    {
                        "op": "call",
                        "tool": "move_node",
                        "args": {
                            "node_id": _E("locals.t.symbol"),
                            "x": _E("locals.t.x"),
                            "y": _E("locals.t.y"),
                        },
                    },
                ],
                "else": [
                    {
                        "op": "call",
                        "tool": "move_node",
                        "args": {
                            "node_id": _E("locals.t.id"),
                            "x": _E("locals.t.x"),
                            "y": _E("locals.t.y"),
                        },
                    }
                ],
            }
        ],
    }
]

# T2: place, OBSERVE the world top-left, and correct by the measured error (works under any constant anchor offset).
CALIBRATING = [
    {
        "op": "for_each",
        "var": "t",
        "over": _E("inputs.targets"),
        "body": [
            {
                "op": "if",
                "cond": _B("eq", _E("locals.t.kind"), "clone_place"),
                "then": [
                    {
                        "op": "call",
                        "tool": "clone_node",
                        "args": {"node_id": _E("locals.t.proto"), "new_id": _E("locals.t.symbol")},
                    },
                    {"op": "let", "name": "nid", "value": _E("locals.t.symbol")},
                ],
                "else": [{"op": "let", "name": "nid", "value": _E("locals.t.id")}],
            },
            {
                "op": "call",
                "tool": "move_node",
                "args": {"node_id": _E("locals.nid"), "x": _E("locals.t.x"), "y": _E("locals.t.y")},
            },
            {
                "op": "call",
                "tool": "observe_geometry",
                "args": {"node_ids": _B("list", _E("locals.nid"))},
                "bind": "obs",
            },
            {
                "op": "let",
                "name": "b",
                "value": _B("index", _B("get", _E("locals.obs"), "bounds"), 0),
            },
            {
                "op": "let",
                "name": "dx",
                "value": _B("sub", _E("locals.t.x"), _B("get", _E("locals.b"), "left")),
            },
            {
                "op": "let",
                "name": "dy",
                "value": _B("sub", _E("locals.t.y"), _B("get", _E("locals.b"), "top")),
            },
            {
                "op": "if",
                "cond": _B(
                    "or",
                    _B("gt", _E("locals.dx"), 0.25),
                    _B("lt", _E("locals.dx"), -0.25),
                    _B("gt", _E("locals.dy"), 0.25),
                    _B("lt", _E("locals.dy"), -0.25),
                ),
                "then": [
                    {
                        "op": "call",
                        "tool": "move_node",
                        "args": {
                            "node_id": _E("locals.nid"),
                            "x": _B("add", _E("locals.t.x"), _E("locals.dx")),
                            "y": _B("add", _E("locals.t.y"), _E("locals.dy")),
                        },
                    }
                ],
            },
        ],
    }
]


async def template_source(role: str, payload: dict) -> list[BindingOut]:
    """binding: try the direct template first, then the calibrating one. repair: calibrating only (the direct one failed)."""
    if role == "binding_repair":
        return [
            BindingOut(
                diagnosis="reference template: calibrate by observed error", program=CALIBRATING
            )
        ]
    return [
        BindingOut(diagnosis="reference template: direct", program=DIRECT),
        BindingOut(diagnosis="reference template: calibrating", program=CALIBRATING),
    ]
