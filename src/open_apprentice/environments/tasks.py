"""Canonical task generation (spec 6.2) and the AGENT-VISIBLE view of a task.

The agent view omits evaluator-only fields. The task id is opaque so it can't leak a family or drift.
"""

from __future__ import annotations

import hashlib
import random

PUBLIC_CONSTRAINTS = [
    "preserve_order",
    "preserve_sizes",
    "stay_on_canvas",
    "leave_unselected_unchanged",
]
PUBLIC_TOOLS = [
    "inspect_scene",
    "inspect_node",
    "observe_geometry",
    "measure_node",
    "move_node",
    "resize_node",
    "set_style",
    "clone_node",
    "group_nodes",
    "ungroup_node",
    "export_scene",
    "finish",
]


def make_gap_row_task(seed: int, *, n: int = 3, nested: bool = False) -> tuple[dict, dict]:
    """Returns (canonical_task, scene). Deterministic in `seed`."""
    rng = random.Random(seed)
    gap, left, top = rng.choice([12, 16, 24, 32]), rng.choice([40, 80]), rng.choice([60, 120])
    ids = [f"card_{chr(97 + i)}" for i in range(n)]
    nodes: list[dict] = []
    parent = None
    if nested:
        nodes.append(
            {"id": "frame", "type": "group", "x": 20, "y": 10, "scaleX": 1.0, "scaleY": 1.0}
        )
        parent = "frame"
    x = 30
    for i in ids:
        w, h = rng.randrange(40, 120, 10), rng.randrange(30, 90, 10)
        nodes.append(
            {
                "id": i,
                "type": "rect",
                "parent": parent,
                "x": x,
                "y": 250 + rng.randrange(0, 40, 10),
                "width": w,
                "height": h,
                "fill": rng.choice(["#d33", "#36c", "#3a6"]),
            }
        )
        x += w + rng.randrange(20, 60, 10)
    nodes.append(
        {
            "id": "bystander",
            "type": "rect",
            "x": 700,
            "y": 400,
            "width": 60,
            "height": 40,
            "fill": "#999",
        }
    )
    scene = {"canvas": {"width": 800, "height": 500}, "nodes": nodes}
    task = {
        "task_id": "t-" + hashlib.sha256(f"{seed}{n}{nested}".encode()).hexdigest()[:10],
        "family": "gap_row",
        "goal_source": "explicit_task",
        "canvas": scene["canvas"],
        "instruction": f"Arrange the {n} selected cards left to right with a {gap} px edge gap, top-aligned at "
        f"y={top}, first card's left edge at x={left}, preserving order and sizes.",
        "selected_ids": ids,
        "parameters": {"gap_px": gap, "left_px": left, "top_px": top},
        "public_constraints": PUBLIC_CONSTRAINTS,
        "schema_version": 1,
    }
    return task, scene


def agent_view(task: dict) -> dict:
    keys = (
        "task_id",
        "goal_source",
        "canvas",
        "instruction",
        "selected_ids",
        "parameters",
        "public_constraints",
    )
    return {k: task[k] for k in keys}
