"""Learn the base story layout from one teaching pair (spec 7.4). A deterministic search candidate, plus optional model
candidates; every candidate must reproduce the teaching pair exactly through the exact rule interpreter."""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from open_apprentice.budget import Ledger
from open_apprentice.campaign.layout_rule import evaluate_layout, objects_for_rule, wrap_learned
from open_apprentice.campaign.scene import role_map
from open_apprentice.concepts.rules import RuleError, validate_rule
from open_apprentice.providers.base import CallContext, Message, Provider, StrictModel

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "campaign_layout.md"
FACTS = {"output_format": "9:16", "overflows": False}
MAX_MODEL_CANDIDATES = 3


class CandidateOut(StrictModel):
    rule: list[Any]
    summary: str


class CandidateSet(StrictModel):
    candidates: list[CandidateOut]


@dataclass
class CandidateReport:
    origin: str
    rule: list
    reproduces: bool
    reason: str = ""


@dataclass
class Learned:
    rule: list
    origin: str
    candidates: list[CandidateReport] = field(default_factory=list)


class LearnError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _board(scene: dict, fmt: str | None = None) -> str:
    boards = [
        n
        for n in scene["nodes"]
        if n["type"] == "artboard" and (fmt is None or n.get("format") == fmt)
    ]
    if len(boards) != 1:
        raise LearnError(
            f"expected exactly one {fmt or ''} artboard, found {len(boards)}".replace("  ", " ")
        )
    return boards[0]["id"]


def _lit(v: Any) -> Any:
    f = Fraction(str(v))
    return int(f) if f.denominator == 1 else {"rat": f"{f.numerator}/{f.denominator}"}


def _expected(before: dict, after: dict) -> dict[str, dict]:
    """Role -> what the taught story says: box, z, font size, corner radius (per role, so it compares across ids)."""
    b_nodes = {n["id"]: n for n in before["nodes"]}
    a_nodes = {n["id"]: n for n in after["nodes"]}
    out = {}
    for o in objects_for_rule(after, _board(after, "9:16")):
        n = a_nodes[o["id"]]
        src = b_nodes.get(o["id"], {})
        out[o["role"]] = {
            "box": (o["x"], o["y"], o["w"], o["h"]),
            "z": n.get("z"),
            "image": n["type"] == "image",
            "fontSize": Fraction(str(n["fontSize"])) if "fontSize" in n else None,
            "fontSize_changed": "fontSize" in n and n["fontSize"] != src.get("fontSize"),
            "cornerRadius": Fraction(str(n["cornerRadius"])) if n["type"] == "shape" else None,
            "cornerRadius_changed": n["type"] == "shape"
            and n.get("cornerRadius") != src.get("cornerRadius"),
        }
    return out


def _search_rule(expected: dict[str, dict]) -> list:
    me = {"ref": "locals.o"}
    branches = []
    for role, e in expected.items():
        x, y, w, h = (_lit(v) for v in e["box"])
        emits = [
            {
                "op": "emit_target",
                "kind": "fit_image" if e["image"] else "place",
                "target": me,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
        ]
        if e["z"] is not None and not e["image"]:
            emits[0]["z"] = e["z"]
        if e["fontSize_changed"]:
            emits.append(
                {
                    "op": "emit_target",
                    "kind": "style",
                    "target": me,
                    "fontSize": _lit(e["fontSize"]),
                }
            )
        if e["cornerRadius_changed"]:
            emits.append(
                {
                    "op": "emit_target",
                    "kind": "style",
                    "target": me,
                    "cornerRadius": _lit(e["cornerRadius"]),
                }
            )
        cond = {"op": "eq", "args": [{"op": "get", "args": [me, "role"]}, role]}
        branches.append({"op": "if", "cond": cond, "then": emits})
    return [{"op": "for_each", "over": {"ref": "objects"}, "var": "o", "body": branches}]


def _asks(stmts: list) -> bool:
    return any(
        isinstance(s, dict)
        and (s.get("op") == "ask" or any(_asks(s.get(k) or []) for k in ("then", "else", "body")))
        for s in stmts
    )


def _check(rule: list, before: dict, expected: dict[str, dict]) -> tuple[bool, str]:
    if not isinstance(rule, list) or _asks(rule):
        return (
            False,
            "invalid rule: overflow questions are built in and cannot be part of a learned layout",
        )
    try:
        validate_rule(wrap_learned(rule), campaign=True)
        objs = objects_for_rule(before, _board(before))
        out = evaluate_layout(wrap_learned(rule), objs, FACTS)
    except (RuleError, LearnError) as e:
        return False, f"invalid rule: {e}"
    roles = {o["id"]: o["role"] for o in objs}
    src_font = {
        o["id"]: n.get("fontSize") for o in objs for n in before["nodes"] if n["id"] == o["id"]
    }
    got = {roles[t.node_id]: t for t in out.targets.values() if t.node_id in roles}
    for role, e in expected.items():
        t = got.get(role)
        if t is None or (t.x, t.y, t.w, t.h) != e["box"]:
            return False, f"{role}: box differs from the taught story"
        if not e["image"] and t.z != e["z"]:
            return False, f"{role}: stacking differs from the taught story"
        if e["fontSize"] is not None:
            size = t.font_size if t.font_size is not None else Fraction(str(src_font[t.node_id]))
            if size != e["fontSize"]:
                return False, f"{role}: font size differs from the taught story"
        if e["cornerRadius_changed"] and t.corner_radius != e["cornerRadius"]:
            return False, f"{role}: corner radius differs from the taught story"
    return True, ""


async def _model_candidates(
    provider: Provider, ledger: Ledger, expected: dict[str, dict]
) -> list[CandidateOut]:
    payload = {
        role: {k: (str(v) if isinstance(v, Fraction) else v) for k, v in e.items() if k != "box"}
        | {"box_after": [str(v) for v in e["box"]]}
        for role, e in expected.items()
    }
    comp = await provider.complete_json(
        messages=[Message("system", PROMPT.read_text()), Message("user", json.dumps(payload))],
        output_schema=CandidateSet,
        ctx=CallContext(role="campaign_layout", category="inference"),
        ledger=ledger,
        max_tokens=4000,
    )
    return comp.parsed.candidates[:MAX_MODEL_CANDIDATES]


async def learn_layout(
    before: dict, after: dict, *, provider: Provider | None = None, ledger: Ledger | None = None
) -> Learned:
    role_map(before, _board(before))  # a missing or doubled role stops here, before any model call
    role_map(after, _board(after, "9:16"))
    expected = _expected(before, after)
    search = _search_rule(expected)
    ok, why = _check(search, before, expected)
    reports = [CandidateReport("search", search, ok, why)]
    if provider is not None:
        for c in await _model_candidates(provider, ledger, expected):
            ok_m, why_m = _check(c.rule, before, expected)
            reports.append(CandidateReport("model", c.rule, ok_m, why_m))
    chosen = next((r for r in reports if r.reproduces), None)
    if chosen is None:
        raise LearnError(
            "no candidate reproduces the taught story: " + "; ".join(r.reason for r in reports)
        )
    return Learned(chosen.rule, chosen.origin, reports)
