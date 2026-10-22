"""The reference apply procedure (origin "reference"): one restricted JSON-AST program that carries out any LayoutPlan
through the engine's allowlisted tools (spec 7.4). Inputs are flat per-operation lists so the program stays well inside the
interpreter's caps (16 items per loop, 500 expressions, 100 actions)."""

from __future__ import annotations

from typing import Any

from open_apprentice.campaign.plan import LayoutPlan
from open_apprentice.environments.client import EngineSession
from open_apprentice.skills.interpreter import run_program

ORIGIN = "reference"


def _each(over: str, tool: str, args: list[str]) -> dict:
    return {
        "op": "for_each",
        "over": {"ref": f"inputs.{over}"},
        "var": "it",
        "body": [
            {
                "op": "call",
                "tool": tool,
                "args": {a: {"op": "get", "args": [{"ref": "locals.it"}, a]} for a in args},
            }
        ],
    }


APPLY_PLAN: list = [
    _each(
        "artboards",
        "create_artboard",
        ["artboard_id", "x", "y", "width", "height", "format", "safe", "sequence"],
    ),
    _each("clones", "clone_node", ["node_id", "new_id"]),
    _each("reparents", "reparent_nodes", ["node_ids", "parent_id"]),
    _each("moves", "move_node", ["node_id", "x", "y"]),
    _each("resizes", "resize_node", ["node_id", "width", "height"]),
    _each("contains", "fit_image_contain", ["node_id", "x", "y", "width", "height"]),
    _each("styles", "set_style", ["node_id", "style"]),
    _each("orders", "set_order", ["node_id", "z"]),
    {
        "op": "call",
        "tool": "remove_artboard",
        "args": {"artboard_id": {"ref": "inputs.source_artboard"}},
    },
]
APPLY_TOOLS = frozenset(
    {
        "create_artboard",
        "clone_node",
        "reparent_nodes",
        "move_node",
        "resize_node",
        "fit_image_contain",
        "set_style",
        "set_order",
        "remove_artboard",
    }
)


def _f(v: Any) -> float:
    return float(v)


def plan_inputs(plan: LayoutPlan) -> dict:
    by_parent: dict[str, list[str]] = {}
    for t in plan.targets:
        if t.parent:
            by_parent.setdefault(t.parent, []).append(t.node_id)
    styles = []
    for t in plan.targets:
        style = {}
        if t.font_size is not None:
            style["fontSize"] = _f(t.font_size)
        if t.corner_radius is not None:
            style["cornerRadius"] = _f(t.corner_radius)
        if style:
            styles.append({"node_id": t.node_id, "style": style})
    placed = [t for t in plan.targets if t.x is not None]
    return {
        "source_artboard": plan.source_artboard,
        "artboards": [
            {
                "artboard_id": a["id"],
                "x": a["x"],
                "y": 0,
                "width": a["width"],
                "height": a["height"],
                "format": a["format"],
                "safe": a["safe"],
                "sequence": a["sequence"],
            }
            for a in plan.artboards
        ],
        "clones": [{"node_id": s, "new_id": n} for s, n in plan.clones],
        "reparents": [{"parent_id": p, "node_ids": ids} for p, ids in by_parent.items()],
        "moves": [
            {"node_id": t.node_id, "x": _f(t.x), "y": _f(t.y)} for t in placed if not t.contain
        ],
        "resizes": [
            {"node_id": t.node_id, "width": _f(t.w), "height": _f(t.h)}
            for t in placed
            if not t.contain and t.w is not None and plan.kinds[t.node_id] != "group"
        ],
        "contains": [
            {"node_id": t.node_id, "x": _f(t.x), "y": _f(t.y), "width": _f(t.w), "height": _f(t.h)}
            for t in placed
            if t.contain
        ],
        "styles": styles,
        # ascending z: each set_order lands its node at its final index because every lower one is already placed
        "orders": [
            {"node_id": t.node_id, "z": t.z}
            for t in sorted(plan.targets, key=lambda t: (t.parent or "", t.z or 0))
            if t.z is not None
        ],
    }


def apply_plan(
    session: EngineSession, plan: LayoutPlan, program: list | None = None, origin: str = ORIGIN
) -> dict:
    """Run a procedure (the reference one by default) on `session`. Engine tool errors propagate (the caller discards the
    session)."""
    _, used = run_program(
        APPLY_PLAN if program is None else program,
        plan_inputs(plan),
        session.tools(sorted(APPLY_TOOLS)),
    )
    return {"origin": origin, "actions": used["actions"]}
