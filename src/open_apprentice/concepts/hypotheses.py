"""Candidate-rule generation and ledger-wide validation (spec 8.6).

The model proposes rules; the host validates each, replays it on EVERY accumulated teaching constraint
(demonstration, chosen answers, corrected examples, and 'neither' exclusions), and keeps only fits.
A candidate that fits the newest example but contradicts earlier teaching evidence is rejected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Optional

from open_apprentice.budget import Ledger
from open_apprentice.concepts.query_selection import differs
from open_apprentice.concepts.rules import FIELDS, RuleError, evaluate_rule, validate_rule
from open_apprentice.concepts.schemas import sha
from open_apprentice.concepts.symbolic import Unsupported, compile_rule, make_inputs
from pydantic import BaseModel

from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.providers.base import CallContext, Message, Provider, StrictModel

import pathlib

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "hypotheses.md"
FIT_TOL = Fraction(1, 2)  # demonstration-fit tolerance (verifier tolerance, 12.3)
MAX_CANDIDATES = 4


class CandidateOut(BaseModel):
    """One proposed rule. DELIBERATELY lenient: a malformed candidate becomes a REJECTED candidate (with a reason fed back),
    never a failed model call that discards its well-formed siblings."""

    model_config = {"extra": "ignore"}

    summary: str = ""
    rule: Optional[Any] = None  # raw AST (list) or, if the model put text here, the rule text
    rule_text: Optional[str] = (
        None  # preferred: compiled by the closed-grammar parser to the same AST
    )

    def source(self) -> tuple[Optional[list], Optional[str]]:
        """-> (ast, text); exactly one is returned non-None, else (None, None)."""
        text = (
            self.rule_text if isinstance(self.rule_text, str) and self.rule_text.strip() else None
        )
        if text is None and isinstance(self.rule, str) and self.rule.strip():
            text = self.rule
        ast = (
            self.rule
            if isinstance(self.rule, list)
            and self.rule
            and all(isinstance(x, dict) for x in self.rule)
            else None
        )
        return (ast, None) if (ast is not None and text is None) else (None, text)


class HypothesisSet(StrictModel):
    candidates: list[CandidateOut]


@dataclass(frozen=True)
class Constraint:
    """One piece of teaching evidence a candidate must respect."""

    kind: str  # "positive" | "excludes"
    scene: dict  # {"objects": [...], "canvas": {...}}
    expected: Optional[dict] = None  # positive: required output state
    excluded: tuple = ()  # excludes: outputs the user said were ALL wrong ("neither")
    source: str = ""  # demonstration | answer | corrected_example | neither


def _g(d: Optional[dict]) -> str:
    return "missing" if d is None else "(" + ", ".join(f"{f}={_n(d[f])}" for f in FIELDS) + ")"


def _n(v: Fraction) -> str:
    return str(int(v)) if v.denominator == 1 else f"{float(v):.4g}"


def fits(rule: list, c: Constraint, tol: Fraction = FIT_TOL) -> tuple[bool, str]:
    """Does `rule` respect this piece of teaching evidence? On failure the message carries the concrete numbers so it can be
    fed back to the model (what your rule produced vs. what the evidence shows)."""
    try:
        out = evaluate_rule(rule, c.scene["objects"], c.scene["canvas"])
    except RuleError as e:
        return False, f"{c.source}: your rule failed to run ({str(e)[:100]})"
    if c.kind == "positive":
        exp = c.expected
        ids = {o["id"] for o in c.scene["objects"]}
        created_out = sorted(
            (k for k in out if k not in ids), key=lambda k: tuple(out[k][f] for f in FIELDS)
        )
        created_exp = sorted(
            (k for k in exp if k not in ids), key=lambda k: tuple(exp[k][f] for f in FIELDS)
        )
        if len(created_out) != len(created_exp):
            return (
                False,
                f"{c.source}: the evidence shows {len(created_exp)} new object(s) but your rule creates {len(created_out)}",
            )
        for ko, ke in zip(created_out, created_exp):
            if any(abs(out[ko][f] - exp[ke][f]) > tol for f in FIELDS):
                return (
                    False,
                    f"{c.source}: your rule creates a new object at {_g(out[ko])} but the evidence shows {_g(exp[ke])}",
                )
        for o in c.scene["objects"]:
            if k_diff(out.get(o["id"]), exp.get(o["id"]), tol):
                return False, (
                    f"{c.source}: for objects[{[x['id'] for x in c.scene['objects']].index(o['id'])}] your rule gives "
                    f"{_g(out.get(o['id']))} but the evidence shows {_g(exp.get(o['id']))}"
                )
        return True, ""
    for bad in c.excluded:
        if not differs_state(out, bad, tol):
            return False, f"{c.source}: your rule reproduces a result the user already rejected"
    return True, ""


def k_diff(a: Optional[dict], b: Optional[dict], tol: Fraction) -> bool:
    if a is None or b is None:
        return a is not b
    return any(abs(a[f] - b[f]) > tol for f in FIELDS)


def differs_state(a: dict, b: dict, tol: Fraction) -> bool:
    return differs(a, b, tol)


@dataclass
class Candidate:
    summary: str
    rule: list
    hash: str
    symbolic: str  # "supported" | "unsupported: <why>"
    text: str = (
        ""  # the rule as the model wrote it (shown back to the model when asking for alternatives)
    )


@dataclass
class GenerationReport:
    round: int
    accepted: list[Candidate] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    model_calls: int = 0
    usage: dict = field(default_factory=dict)


def neutral(v: Any) -> Any:
    if isinstance(v, Fraction):
        return int(v) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"
    if isinstance(v, dict):
        return {k: neutral(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [neutral(x) for x in v]
    return v


def derived_relations(c: Constraint) -> dict:
    """Geometry the model would otherwise have to subtract by hand, computed ONLY from the public before/after rectangles.
    Symmetric in all four sides and in every pair, so it points at no particular rule family. Positions use objects[K].
    """
    ids = [o["id"] for o in c.scene["objects"]]
    pos = {k: f"objects[{i}]" for i, k in enumerate(ids)}
    exp, out = c.expected, {}
    box = lambda d: (d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"])
    created = [k for k in exp if k not in pos]
    rel = []
    for k in created:
        L, T, R, B = box(exp[k])
        for ref in ids:
            if ref not in exp:
                continue
            l, t, r, b = box(exp[ref])
            rel.append(
                {
                    "new_object": k,
                    "relative_to": pos[ref],
                    "left_edge_minus_ref_left": L - l,
                    "ref_right_minus_right_edge": r - R,
                    "top_edge_minus_ref_top": T - t,
                    "ref_bottom_minus_bottom_edge": b - B,
                    "width_ratio_new_to_ref": (
                        exp[k]["w"] / exp[ref]["w"] if exp[ref]["w"] else None
                    ),
                    "height_ratio_new_to_ref": (
                        exp[k]["h"] / exp[ref]["h"] if exp[ref]["h"] else None
                    ),
                }
            )
    if rel:
        out["created_objects_vs_each_existing_object"] = rel
    moved = {}
    for o in c.scene["objects"]:
        e = exp.get(o["id"])
        if e and any(e[f] != Fraction(o[f]) for f in FIELDS):
            moved[pos[o["id"]]] = {
                "dx": e["x"] - Fraction(o["x"]),
                "dy": e["y"] - Fraction(o["y"]),
                "dw": e["w"] - Fraction(o["w"]),
                "dh": e["h"] - Fraction(o["h"]),
            }
    if moved:
        out["changes_to_existing_objects"] = moved
        row = [k for k in ids if k in exp]
        if len(row) >= 2:
            out["after_state_between_consecutive_objects"] = [
                {
                    "from": pos[a],
                    "to": pos[b],
                    "edge_gap": exp[b]["x"] - (exp[a]["x"] + exp[a]["w"]),
                    "center_distance_x": (exp[b]["x"] + exp[b]["w"] / 2)
                    - (exp[a]["x"] + exp[a]["w"] / 2),
                    "top_difference": exp[b]["y"] - exp[a]["y"],
                }
                for a, b in zip(row, row[1:])
            ]
            out["after_state_first_object"] = {"left": exp[row[0]]["x"], "top": exp[row[0]]["y"]}
    return out


INCLUDE_RELATIONS = (
    False  # decisions #29: tested live (24 dev trials) and did NOT help; kept for reproducibility
)


def describe(constraints: list[Constraint]) -> list[dict]:
    """Learner-facing evidence. Contains geometry only: no rule, family name, formula, or parameters."""
    out = []
    for c in constraints:
        d = {"evidence": c.source, "scene": neutral(c.scene)}
        if c.kind == "positive":
            d["resulting_geometry"] = neutral(c.expected)
            rel = derived_relations(c) if INCLUDE_RELATIONS else {}
            if rel:
                d["derived_relations"] = neutral(rel)
        else:
            d["all_of_these_were_rejected"] = neutral(list(c.excluded))
        out.append(d)
    return out


async def generate_candidates(
    provider: Provider,
    ledger: Ledger,
    constraints: list[Constraint],
    *,
    rnd: int,
    rejected_summaries: list[str],
    object_counts: list[int],
    max_tokens: int = 6000,
    correction_turn: bool = True,
    alternatives_to: Optional[list[Candidate]] = None,
) -> GenerationReport:  # reasoning model: hidden tokens share this budget
    rep = GenerationReport(rnd)
    user: dict[str, Any] = {
        "teaching_evidence": describe(constraints),
        "previously_rejected": rejected_summaries[-8:],
    }
    if alternatives_to:
        user["already_fitting_rules"] = [
            {"summary": c.summary[:100], "rule_text": c.text[:400]} for c in alternatives_to
        ]
        user["instruction"] = (
            "The rules above already reproduce ALL the evidence exactly. Propose up to 3 DIFFERENT rules that also reproduce "
            "all the evidence exactly but would place things differently on OTHER inputs (for example by depending on sizes "
            "differently, or by measuring differently). Do not repeat the rules above."
        )
    msgs = [Message("system", PROMPT.read_text()), Message("user", json.dumps(user))]
    seen: set[str] = {c.hash for c in (alternatives_to or [])}
    aliases = (
        {o["id"]: i for i, o in enumerate(constraints[0].scene["objects"])} if constraints else {}
    )

    def process(cands: list[CandidateOut], tag: str) -> list[dict]:
        problems: list[dict] = []
        for cand in cands[:MAX_CANDIDATES]:
            try:
                ast, text = cand.source()
                if ast is None and text is None:
                    raise RuleError("give the rule as rule_text (a string in the rule language)")
                rule = ast if ast is not None else parse_rule_text(text, aliases)
                validate_rule(rule)
            except RuleError as e:
                excerpt = (
                    cand.rule_text or (json.dumps(cand.rule) if cand.rule is not None else "")
                )[:400]
                rep.rejected.append(
                    {
                        "summary": cand.summary,
                        "reason": f"invalid rule: {str(e)[:160]}",
                        "rule_excerpt": excerpt,
                        "stage": tag,
                    }
                )
                problems.append(
                    {
                        "summary": cand.summary[:80],
                        "problem": f"syntax: {str(e)[:160]}",
                        "rule_text": (cand.rule_text or "")[:300],
                    }
                )
                continue
            h = sha(rule)
            if h in seen:
                rep.rejected.append({"summary": cand.summary, "reason": "duplicate", "stage": tag})
                continue
            seen.add(h)
            bad = next((why for c in constraints for ok, why in [fits(rule, c)] if not ok), None)
            if bad:
                rep.rejected.append(
                    {
                        "summary": cand.summary,
                        "reason": f"contradicts teaching evidence - {bad}",
                        "rule_excerpt": json.dumps(rule)[:400],
                        "stage": tag,
                    }
                )
                problems.append(
                    {
                        "summary": cand.summary[:80],
                        "problem": bad,
                        "rule_text": (cand.rule_text or "")[:300],
                    }
                )
                continue
            sym = "supported"
            try:
                for n in object_counts:
                    o, cv, _ = make_inputs(n)
                    compile_rule(rule, o, cv)
            except (Unsupported, RuleError) as e:
                sym = f"unsupported: {str(e)[:80]}"
            rep.accepted.append(
                Candidate(
                    cand.summary or "candidate",
                    rule,
                    h,
                    sym,
                    cand.rule_text or (cand.rule if isinstance(cand.rule, str) else ""),
                )
            )
        return problems

    comp = await provider.complete_json(
        messages=msgs,
        output_schema=HypothesisSet,
        ctx=CallContext(role="hypotheses", category="teaching"),
        ledger=ledger,
        max_tokens=max_tokens,
    )
    calls = 1 + comp.schema_corrections
    ptok, ctok = comp.prompt_tokens or 0, comp.completion_tokens or 0
    problems = process(comp.parsed.candidates, "initial")

    if correction_turn and not rep.accepted and problems:
        # ONE counted correction turn: show the model exactly how each rule failed (numbers, parse errors).
        msgs = msgs + [
            Message("assistant", comp.parsed.model_dump_json()),
            Message(
                "user",
                json.dumps(
                    {
                        "your_candidates_were_checked": problems[:MAX_CANDIDATES],
                        "instruction": "None of your rules reproduced the teaching evidence exactly. Fix the arithmetic or syntax "
                        "and reply in the same JSON format with up to 4 corrected, different candidates.",
                    }
                ),
            ),
        ]
        comp2 = await provider.complete_json(
            messages=msgs,
            output_schema=HypothesisSet,
            ctx=CallContext(role="hypotheses", category="teaching"),
            ledger=ledger,
            max_tokens=max_tokens,
        )
        calls += 1 + comp2.schema_corrections
        ptok, ctok = ptok + (comp2.prompt_tokens or 0), ctok + (comp2.completion_tokens or 0)
        process(comp2.parsed.candidates, "after_correction")
        rep.usage["correction_turn"] = True

    rep.model_calls = calls
    rep.usage.update(
        {
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
            "label": comp.provider_label,
            "model": comp.model_id,
        }
    )
    return rep
