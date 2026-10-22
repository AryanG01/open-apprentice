"""Evaluate campaign layout rules (spec 7.3): the rules.py campaign dialect, run by a `_Run` subclass so the existing rule
callers and their {id: {x,y,w,h}} state are untouched."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from open_apprentice.campaign.limits import STORY_H, STORY_W
from open_apprentice.concepts.rules import (
    ASK_OPTIONS,
    MAX_OBJECTS,
    Obj,
    RuleError,
    _num,
    _Run,
    to_obj,
    validate_rule,
)


@dataclass
class Target:
    node_id: str
    x: Fraction | None = None
    y: Fraction | None = None
    w: Fraction | None = None
    h: Fraction | None = None
    parent: str | None = None
    z: int | None = None
    font_size: Fraction | None = None
    corner_radius: Fraction | None = None
    contain: bool = False


@dataclass
class LayoutOutcome:
    targets: dict[str, Target] = field(default_factory=dict)
    ask: tuple[str, ...] | None = None


class _Asked(Exception):
    pass


def _frac(v: Any) -> Fraction:
    return Fraction(
        str(v)
    )  # decimal reading of authored floats such as 51.2, not their binary expansion


def objects_for_rule(scene: dict, artboard_id: str) -> list[dict]:
    """Role nodes directly in the artboard, plus the CTA's children as pseudo-roles `cta/<type>`; parent-local geometry."""
    nodes = scene["nodes"]
    out = []
    for n in nodes:
        if n.get("parent") == artboard_id and n.get("role"):
            w, h = n.get("width"), n.get("height")
            if n["type"] == "group":  # a group's size is its children's extent
                kids = [k for k in nodes if k.get("parent") == n["id"]]
                w = max((k["x"] + k["width"] for k in kids), default=0)
                h = max((k["y"] + k["height"] for k in kids), default=0)
            out.append(_obj(n, n["role"], w, h))
            if n["role"] == "cta":
                out += [
                    _obj(k, f"cta/{k['type']}", k["width"], k["height"])
                    for k in nodes
                    if k.get("parent") == n["id"]
                ]
    return out


def _obj(n: dict, role: str, w: Any, h: Any) -> dict:
    return {
        "id": n["id"],
        "x": _frac(n["x"]),
        "y": _frac(n["y"]),
        "w": _frac(w),
        "h": _frac(h),
        "role": role,
        "kind": n["type"],
    }


class _LayoutRun(_Run):
    def __init__(self, objects: list[Obj], facts: dict) -> None:
        super().__init__(objects, {"w": STORY_W, "h": STORY_H})
        self.facts = facts
        self.targets: dict[str, Target] = {}

    def ev(self, e: Any) -> Any:
        if isinstance(e, dict) and "ref" in e and e["ref"].startswith("facts."):
            return self.facts[e["ref"].split(".", 1)[1]]
        return super().ev(e)

    def block(self, stmts: list) -> None:
        for s in stmts:
            if s["op"] == "ask":
                raise _Asked()
            super().block([s])

    def emit(self, s: dict) -> None:
        t = self.ev(s["target"])
        if not isinstance(t, Obj):
            raise RuleError("emit target must be an object")
        cur = self.targets.setdefault(t.id, Target(t.id))
        kind = s["kind"]
        if kind in ("place", "fit_image"):
            cur.x, cur.y, cur.w, cur.h = (_num(self.ev(s[k])) for k in ("x", "y", "w", "h"))
            cur.contain = kind == "fit_image"
            cur.parent = s.get("parent", cur.parent)
            cur.z = s.get("z", cur.z)
        else:  # style
            if "fontSize" in s:
                cur.font_size = _num(self.ev(s["fontSize"]))
            if "cornerRadius" in s:
                cur.corner_radius = _num(self.ev(s["cornerRadius"]))


def evaluate_layout(body: list, objects: list[dict], facts: dict) -> LayoutOutcome:
    """Run a campaign rule. Reaching `ask` stops it: the outcome carries the built-in options and no targets."""
    validate_rule(body, campaign=True)
    if not 1 <= len(objects) <= MAX_OBJECTS:
        raise RuleError("object count out of range")
    if not isinstance(facts.get("output_format"), str) or not isinstance(
        facts.get("overflows"), bool
    ):
        raise RuleError("facts need output_format (str) and overflows (bool)")
    run = _LayoutRun([to_obj(o) for o in objects], facts)
    try:
        run.block(body)
    except _Asked:
        return LayoutOutcome(ask=ASK_OPTIONS)
    return LayoutOutcome(targets=run.targets)


def wrap_learned(body: list) -> list:
    """The fixed, built-in wrapper around a learned layout: story format only, and overflow asks (never learned)."""
    return [
        {
            "op": "if",
            "cond": {"op": "eq", "args": [{"ref": "facts.output_format"}, "9:16"]},
            "then": [
                {
                    "op": "if",
                    "cond": {"ref": "facts.overflows"},
                    "then": [{"op": "ask", "options": list(ASK_OPTIONS)}],
                    "else": body,
                }
            ],
        }
    ]
