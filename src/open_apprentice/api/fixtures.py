"""SCRIPTED native binding programs for the interactive demo (origin = fixture; never counted as learned).

The demo needs a working binding and a working repair without spending model credits, so these are written by hand:
NAIVE trusts the documented tool behaviour; PROBING measures the result and corrects it; HARDCODED_OFFSET is a deliberately
bad "fix" that the retained-case replay must reject. They are the same programs the integration tests use.
"""

from __future__ import annotations

E = lambda p: {"ref": p}  # noqa: E731
B = lambda o, *a: {"op": o, "args": list(a)}  # noqa: E731

NAIVE = [
    {
        "op": "for_each",
        "var": "t",
        "over": E("inputs.targets"),
        "body": [
            {
                "op": "if",
                "cond": B("eq", E("locals.t.kind"), "clone_place"),
                "then": [
                    {
                        "op": "call",
                        "tool": "clone_node",
                        "args": {"node_id": E("locals.t.proto"), "new_id": E("locals.t.symbol")},
                    },
                    {
                        "op": "call",
                        "tool": "move_node",
                        "args": {
                            "node_id": E("locals.t.symbol"),
                            "x": E("locals.t.x"),
                            "y": E("locals.t.y"),
                        },
                    },
                ],
                "else": [
                    {
                        "op": "call",
                        "tool": "move_node",
                        "args": {
                            "node_id": E("locals.t.id"),
                            "x": E("locals.t.x"),
                            "y": E("locals.t.y"),
                        },
                    }
                ],
            }
        ],
    }
]

PROBING = [
    {
        "op": "for_each",
        "var": "t",
        "over": E("inputs.targets"),
        "body": [
            {
                "op": "if",
                "cond": B("eq", E("locals.t.kind"), "clone_place"),
                "then": [
                    {
                        "op": "call",
                        "tool": "clone_node",
                        "args": {"node_id": E("locals.t.proto"), "new_id": E("locals.t.symbol")},
                    },
                    {"op": "let", "name": "nid", "value": E("locals.t.symbol")},
                ],
                "else": [{"op": "let", "name": "nid", "value": E("locals.t.id")}],
            },
            {
                "op": "call",
                "tool": "move_node",
                "args": {"node_id": E("locals.nid"), "x": E("locals.t.x"), "y": E("locals.t.y")},
            },
            {
                "op": "call",
                "tool": "observe_geometry",
                "args": {"node_ids": B("list", E("locals.nid"))},
                "bind": "obs",
            },
            {"op": "let", "name": "b", "value": B("index", B("get", E("locals.obs"), "bounds"), 0)},
            {
                "op": "let",
                "name": "dx",
                "value": B("sub", E("locals.t.x"), B("get", E("locals.b"), "left")),
            },
            {
                "op": "let",
                "name": "dy",
                "value": B("sub", E("locals.t.y"), B("get", E("locals.b"), "top")),
            },
            {
                "op": "if",
                "cond": B(
                    "or",
                    B("gt", E("locals.dx"), 0.25),
                    B("lt", E("locals.dx"), -0.25),
                    B("gt", E("locals.dy"), 0.25),
                    B("lt", E("locals.dy"), -0.25),
                ),
                "then": [
                    {
                        "op": "call",
                        "tool": "move_node",
                        "args": {
                            "node_id": E("locals.nid"),
                            "x": B("add", E("locals.t.x"), E("locals.dx")),
                            "y": B("add", E("locals.t.y"), E("locals.dy")),
                        },
                    }
                ],
            },
        ],
    }
]

HARDCODED_OFFSET = [
    {
        "op": "for_each",
        "var": "t",
        "over": E("inputs.targets"),
        "body": [
            {
                "op": "call",
                "tool": "clone_node",
                "args": {"node_id": E("locals.t.proto"), "new_id": E("locals.t.symbol")},
            },
            {
                "op": "call",
                "tool": "move_node",
                "args": {
                    "node_id": E("locals.t.symbol"),
                    "x": B("add", E("locals.t.x"), 10),
                    "y": B("add", E("locals.t.y"), 10),
                },
            },
        ],
    }
]


def cands(*programs: list) -> dict:
    return {
        "candidates": [
            {"diagnosis": f"scripted fixture {i}", "program": p} for i, p in enumerate(programs)
        ]
    }
