"""Offline label-rule enumerator: the no-model learner behind PROVIDER_MODE=mock and the journey tests.

It proposes rules from a small template grammar (side x gap x scope) and keeps only those that reproduce every evidence item
exactly. Gaps are read off the evidence (the gap each side would need) plus a few common values. It never sees held-out data and
is reported as provenance "Fixture" (a deterministic offline candidate source, not a model). It implements the learning
executor's Proposer protocol and the correction executor's ScopeProposer protocol."""

from __future__ import annotations

from fractions import Fraction
from itertools import product
from typing import Any, Optional

from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.concepts.rules import RuleError, evaluate_rule, validate_rule

SIDES = ("right", "below", "left", "above")
COMMON_GAPS = (Fraction(8), Fraction(12), Fraction(16))
MAX_GAP = Fraction(200)
PER_ROUND = 4
POSE = {
    "right": ("a.x + a.w + {g}", "a.y + (a.h - o.h) / 2"),
    "left": ("a.x - o.w - {g}", "a.y + (a.h - o.h) / 2"),
    "below": ("a.x + (a.w - o.w) / 2", "a.y + a.h + {g}"),
    "above": ("a.x + (a.w - o.w) / 2", "a.y - o.h - {g}"),
    "stay": ("o.x", "o.y"),
}


def _f(v: Any) -> Fraction:
    return Fraction(str(v))


def _scene(objects: list[dict], canvas: dict) -> tuple[list[dict], dict]:
    objs = [{**o, **{k: _f(o[k]) for k in ("x", "y", "w", "h")}} for o in objects]
    return objs, {k: _f(v) for k, v in canvas.items()}


def _num(g: Fraction) -> str:
    return str(g.numerator) if g.denominator == 1 else format(float(g), "g")


def _text(side: str, gap: Fraction, scope: Optional[str]) -> str:
    x, y = (p.format(g=_num(gap)) for p in POSE[side])
    move = ["let a = object(o.attached)", f"move o to ({x}, {y})"]
    body = move if scope is None else [f"if {scope} {{", *("  " + m for m in move), "}"]
    lines = [
        "for o in objects {",
        '  if o.kind == "label" {',
        *("    " + b for b in body),
        "  }",
        "}",
    ]
    return "\n".join(lines)


def _gaps(objs: list[dict], moves: dict[str, tuple[Fraction, Fraction]]) -> list[Fraction]:
    by_id = {o["id"]: o for o in objs}
    found = set(COMMON_GAPS)
    for lid, (x, y) in moves.items():
        o = by_id.get(lid)
        a = by_id.get(o["attached"]) if o else None
        if o is None or a is None:
            continue
        for g in (
            x - (a["x"] + a["w"]),
            a["x"] - (x + o["w"]),
            y - (a["y"] + a["h"]),
            a["y"] - (y + o["h"]),
        ):
            if 0 <= g <= MAX_GAP and (g * 64).denominator == 1:
                found.add(g)
    return sorted(found)


def _out(
    rule: list, objs: list[dict], canvas: dict
) -> Optional[dict[str, tuple[Fraction, Fraction]]]:
    try:
        res = evaluate_rule(rule, objs, canvas)
    except RuleError:
        return None
    return {k: (v["x"], v["y"]) for k, v in res.items()}


def _fits(out: Optional[dict], objs: list[dict], moves: dict, all_others_fixed: bool) -> bool:
    if out is None:
        return False
    if any(out.get(k) != v for k, v in moves.items()):
        return False
    if all_others_fixed:
        for o in objs:
            if o["id"] not in moves and o["id"] in out and out[o["id"]] != (o["x"], o["y"]):
                return False
    return True


def _parse(text: str) -> Optional[list]:
    try:
        rule = parse_rule_text(text)
        validate_rule(rule)
    except RuleError:
        return None
    return rule


class LabelEnumerator:
    def propose(
        self, evidence_json: dict, round_kind: str, feedback: tuple[str, ...]
    ) -> tuple[list[dict], dict, Fraction]:
        items = []
        for it in evidence_json.get("teaching_evidence", []):
            objs, canvas = _scene(it["scene"]["objects"], it["scene"]["canvas"])
            moves = {k: (_f(v[0]), _f(v[1])) for k, v in it.get("labels_moved_to", {}).items()}
            items.append((objs, canvas, moves))
        roles = sorted(
            {o["role"] for objs, _, mv in items for o in objs if o["id"] in mv and o["role"]}
        )
        gaps = sorted({g for objs, _, mv in items for g in _gaps(objs, mv)})
        scopes: list[Optional[str]] = [None] + [f'o.role == "{r}"' for r in roles]
        fitting, seen, evaluated = [], set(), 0
        for scope, side, gap in product(scopes, SIDES, gaps):
            text = _text(side, gap, scope)
            rule = _parse(text)
            evaluated += 1
            if rule is None:
                continue
            outs = [_out(rule, objs, canvas) for objs, canvas, _ in items]
            if not items or not all(
                _fits(o, objs, mv, True) for o, (objs, _, mv) in zip(outs, items)
            ):
                continue
            key = repr([sorted(o.items()) for o in outs if o is not None])
            if key in seen:
                continue
            seen.add(key)
            summary = f"labels{'' if scope is None else ' with ' + scope} go {side} of their node, gap {_num(gap)}"
            fitting.append({"rule": rule, "summary": summary, "text": text})
        fitting.sort(key=lambda c: (len(c["text"]), c["text"]))
        start = 0 if round_kind == "initial" else PER_ROUND
        usage = {"source": "label_enumerative", "evaluated": evaluated}
        return fitting[start : start + PER_ROUND], usage, Fraction(0)

    def propose_scope(
        self, evidence_json: dict, round_kind: str
    ) -> tuple[list[dict], dict, Fraction]:
        objs, canvas = _scene(evidence_json["corrected_scene_objects"], evidence_json["canvas"])
        moves = {k: (_f(v[0]), _f(v[1])) for k, v in evidence_json["corrected_output"].items()}
        base = list(evidence_json.get("base_program", {}).get("rule") or [])
        by_id = {o["id"]: o for o in objs}
        roles = {by_id[k]["role"] for k in moves if k in by_id}
        selectors = [f'o.role == "{roles.pop()}"'] if len(roles) == 1 and "" not in roles else []
        selectors.append('o.kind == "label"')
        out, evaluated = [], 0
        for selector, side in product(selectors, (*SIDES, "stay")):
            for gap in [Fraction(0)] if side == "stay" else _gaps(objs, moves):
                text = _text(side, gap, selector)
                rule = _parse(text)
                evaluated += 1
                if rule is None:
                    continue
                combined = (
                    base + rule
                )  # the later move wins, so labels outside the selector keep the base behaviour
                if not _fits(_out(combined, objs, canvas), objs, moves, False):
                    continue
                summary = f"labels with {selector} go {side} of their node" + (
                    "" if side == "stay" else f", gap {_num(gap)}"
                )
                out.append({"rule": combined, "selector": selector, "summary": summary})
        usage = {"source": "label_enumerative", "evaluated": evaluated}
        return out[: 2 * PER_ROUND], usage, Fraction(0)
