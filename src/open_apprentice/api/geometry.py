"""Plain-JSON geometry helpers shared by the HTTP API and the UI data builder (no engine, no model)."""

from __future__ import annotations

from fractions import Fraction as F
from typing import Any, Optional

from open_apprentice.concepts.bindings import keys_of

CANVAS = {"w": 800, "h": 600}
_ROLES = {"card": "card", "proto": "prototype"}


def fl(v: Any) -> float:
    return float(v)


def card_scene(w: int, h: int = 80, x: int = 100, y: int = 100) -> dict:
    """One card plus the badge prototype: the only scene family the live demo supports."""
    return {
        "objects": [
            {"id": "card", "x": F(x), "y": F(y), "w": F(w), "h": F(h)},
            {"id": "proto", "x": F(0), "y": F(0), "w": F(20), "h": F(20)},
        ],
        "canvas": {"w": F(CANVAS["w"]), "h": F(CANVAS["h"])},
    }


def _role(i: int, obj_id: str) -> str:
    """Rules address objects by position (objects[0] is the card, objects[1] the badge prototype), so roles follow position."""
    if obj_id in _ROLES:
        return _ROLES[obj_id]
    return ("card", "prototype")[i] if i < 2 else "object"


def boxes_of_scene(sc: dict) -> list[dict]:
    return [
        {
            "id": o["id"],
            "x": fl(o["x"]),
            "y": fl(o["y"]),
            "w": fl(o["w"]),
            "h": fl(o["h"]),
            "role": _role(i, o["id"]),
        }
        for i, o in enumerate(sc["objects"])
    ]


def boxes_of_outputs(sc: dict, out: dict[str, dict]) -> list[dict]:
    """The scene's untouched objects plus every geometry a rule emitted (new objects are badges)."""
    base = {b["id"]: b for b in boxes_of_scene(sc)}
    for key, g in out.items():
        prev = base.get(key)
        base[key] = {
            "id": key,
            "x": fl(g["x"]),
            "y": fl(g["y"]),
            "w": fl(g.get("w", prev["w"] if prev else 20)),
            "h": fl(g.get("h", prev["h"] if prev else 20)),
            "role": prev["role"] if prev else "badge",
        }
    return list(base.values())


def boxes_of_targets(targets: list[dict], sc: dict) -> list[dict]:
    return boxes_of_outputs(sc, {(t.get("symbol") or t.get("id")): t for t in targets})


def observed_boxes(session: Any, targets: list[dict]) -> list[dict]:
    ids = sorted({"card", "proto", *keys_of(targets)})
    bounds = session.call("observe_geometry", node_ids=ids)["bounds"]
    return [
        {
            "id": b["id"],
            "x": b["left"],
            "y": b["top"],
            "w": b["width"],
            "h": b["height"],
            "role": _ROLES.get(b["id"], "badge"),
        }
        for b in bounds
    ]


def view(label: str, boxes: list[dict], note: str = "", canvas: Optional[dict] = None) -> dict:
    return {"label": label, "canvas": canvas or CANVAS, "boxes": boxes, "note": note}
