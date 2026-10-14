"""Teaching loop for label placement: propose, filter on all evidence, ask about the batch, commit or abstain.

Agent-visible code: it receives plain scene dicts and a `teacher` callable; it never sees the hidden behaviour.

  1. Nemotron (or any Provider) proposes rules from the demonstrations; each is parsed, validated and replayed on EVERY
     constraint (hypotheses.fits). Zero candidates after the allowed rounds => abstain (never a guess).
  2. Batch-first questions: run every surviving candidate on every batch document; documents where candidates disagree
     are question candidates. Pick the one that splits the candidates most (tie: fewer objects changed, then position).
     The teacher shows the true result; it becomes one more positive constraint. A (document, outcome-partition) pair is
     never asked twice. At most MAX_QUESTIONS questions.
  3. Commit when the survivors agree on every batch document (scope: batch_agreement, NOT global equivalence), taking the
     smallest rule; abstain when nothing fits or the question budget leaves a disagreement unresolved.

Provenance is logged: every candidate carries its proposal round. Truncated or failed model calls are recorded, not hidden.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable, Optional

from open_apprentice.budget import BudgetExhausted, Ledger
from open_apprentice.concepts.hypotheses import Candidate, Constraint, fits, generate_candidates
from open_apprentice.concepts.rules import FIELDS, RuleError, evaluate_rule
from open_apprentice.concepts.schemas import sha
from open_apprentice.providers.base import Provider

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "hypotheses_labels.md"
MAX_QUESTIONS = 3
MAX_ROUNDS = 2


def to_state(scene: dict) -> dict[str, dict[str, Fraction]]:
    return {o["id"]: {f: Fraction(o[f]) for f in FIELDS} for o in scene["objects"]}


def _run(rule: list, scene: dict) -> Optional[tuple]:
    try:
        st = evaluate_rule(rule, scene["objects"], scene["canvas"])
    except RuleError:
        return None
    return tuple(sorted((k, tuple(v[f] for f in FIELDS)) for k, v in st.items()))


def _changed(rule: list, scene: dict) -> int:
    out = _run(rule, scene)
    base = tuple(sorted((o["id"], tuple(Fraction(o[f]) for f in FIELDS)) for o in scene["objects"]))
    return 0 if out is None else sum(a != b for a, b in zip(out, base))


def _size(c: Candidate) -> int:
    return len(json.dumps(c.rule))


CMP = {"lt", "le", "gt", "ge", "eq", "ne"}


def magic_condition(node: Any) -> bool:
    """True if the rule compares an object's raw geometry or id with a non-zero constant (e.g. `w == 80`, `x < 50`,
    `id == "n3"`). Such rules memorise the demonstrations (noise included) instead of generalising; comparisons with 0
    (off-canvas checks) and between two computed values are fine."""
    if isinstance(node, list):
        return any(magic_condition(n) for n in node)
    if not isinstance(node, dict):
        return False
    if node.get("op") in CMP:
        a = node.get("args", [])
        has_get = any(
            isinstance(x, dict)
            and x.get("op") == "get"
            and x["args"][1] in ("x", "y", "w", "h", "id")
            for x in a
        )
        has_const = any(
            (isinstance(x, (int, dict)) and not isinstance(x, bool) and x not in (0, {"rat": "0"}))
            and not (isinstance(x, dict) and "op" in x or isinstance(x, dict) and "ref" in x)
            for x in a
        ) or any(
            isinstance(x, str) and x not in ("label", "node", "note", "warning", "") for x in a
        )
        if has_get and has_const:
            return True
    return any(magic_condition(v) for v in node.values())


@dataclass
class TeachingResult:
    status: str  # committed | abstained
    reason: str = ""
    rule: Optional[list] = None
    rule_hash: str = ""
    summary: str = ""
    scope: str = ""  # batch_agreement
    questions: list[dict] = field(default_factory=list)
    rounds: list[dict] = field(default_factory=list)
    remaining: int = 0
    model_calls: int = 0
    usage: dict = field(default_factory=dict)


def pick_question(cands: list[Candidate], batch: list[dict], asked: set[str]) -> Optional[int]:
    best: Optional[tuple] = None
    for i, scene in enumerate(batch):
        groups: dict[Any, int] = {}
        for c in cands:
            groups[_run(c.rule, scene)] = groups.get(_run(c.rule, scene), 0) + 1
        if len(groups) < 2:
            continue
        key = sha([sorted(map(repr, groups)), i])
        if key in asked:
            continue
        outside_largest = len(cands) - max(groups.values())
        changed = sum(_changed(c.rule, scene) for c in cands)
        score = (-outside_largest, changed, i)
        if best is None or score < best[0]:
            best = (score, i, key)
    if best is None:
        return None
    asked.add(best[2])
    return best[1]


async def teach(
    provider: Provider,
    ledger: Ledger,
    demos: list[tuple[dict, dict]],
    batch: list[dict],
    teacher: Callable[[dict], dict],
    *,
    max_tokens: int = 6000,
    max_candidates: int = 4,
) -> TeachingResult:
    res = TeachingResult("abstained")
    constraints = [
        Constraint("positive", before, to_state(after), source="demonstration")
        for before, after in demos
    ]
    cands: list[Candidate] = []
    rejected_summaries: list[str] = []
    counts = sorted({len(b["objects"]) for b, _ in demos})

    async def propose(rnd: int, alternatives: Optional[list[Candidate]] = None) -> None:
        rep = None
        for attempt in (
            1,
            2,
        ):  # one retry: truncation / timeout / transport failures are often transient
            try:
                rep = await generate_candidates(
                    provider,
                    ledger,
                    constraints,
                    rnd=rnd,
                    rejected_summaries=rejected_summaries,
                    object_counts=counts,
                    max_tokens=max_tokens,
                    alternatives_to=alternatives,
                    prompt=PROMPT,
                    max_candidates=max_candidates,
                )
                break
            except BudgetExhausted as e:
                res.rounds.append({"round": rnd, "error": f"budget: {e}"})
                raise
            except Exception as e:  # recorded, never silently turned into success
                res.rounds.append(
                    {
                        "round": rnd,
                        "attempt": attempt,
                        "error": f"{type(e).__name__}: {str(e)[:160]}",
                    }
                )
        if rep is None:
            return
        res.model_calls += rep.model_calls
        for k in ("prompt_tokens", "completion_tokens"):
            res.usage[k] = res.usage.get(k, 0) + rep.usage.get(k, 0)
        res.rounds.append(
            {
                "round": rnd,
                "accepted": len(rep.accepted),
                "rejected": [{"why": r["reason"][:200]} for r in rep.rejected],
            }
        )
        rejected_summaries.extend(r["summary"] for r in rep.rejected)
        have = {c.hash for c in cands}
        for c in rep.accepted:
            if magic_condition(c.rule):
                rejected_summaries.append(
                    f"{c.summary[:60]} -- compares a position, size or id with a constant: that memorises the "
                    "demonstrations; use relations between objects instead"
                )
                res.rounds[-1]["magic_rejected"] = res.rounds[-1].get("magic_rejected", 0) + 1
            elif c.hash not in have:
                cands.append(c)

    def splits(cs: list[Candidate]) -> bool:
        return any(len({_run(c.rule, sc) for c in cs}) > 1 for sc in batch)

    try:
        await propose(1)
        if (len(cands) < 2 or not splits(cands)) and not any(r.get("error") for r in res.rounds):
            # contrastive round: survivors that agree on every batch diagram (or a lone survivor) are not proof that the
            # evidence is unambiguous; ask for rules that fit equally well but behave differently elsewhere
            await propose(2, alternatives=list(cands) or None)
        asked: set[str] = set()
        revised = False
        while cands and len(res.questions) < MAX_QUESTIONS:
            i = pick_question(cands, batch, asked)
            if i is None:
                break
            truth = teacher(batch[i])
            constraints.append(Constraint("positive", batch[i], to_state(truth), source="answer"))
            before_n = len(cands)
            dead = [
                (c, next(w for k in constraints for ok, w in [fits(c.rule, k)] if not ok))
                for c in cands
                if not all(fits(c.rule, k)[0] for k in constraints)
            ]
            cands = [c for c in cands if all(fits(c.rule, k)[0] for k in constraints)]
            res.questions.append(
                {"batch_index": i, "candidates_before": before_n, "after": len(cands)}
            )
            if not cands and not revised:
                # "none of these": show the model exactly how each rule contradicted the teacher, ask once more
                revised = True
                rejected_summaries.extend(f"{c.summary[:60]} -- {why[:220]}" for c, why in dead)
                await propose(len(res.rounds) + 1)
                cands = [c for c in cands if all(fits(c.rule, k)[0] for k in constraints)]
                continue
            if not cands:
                break
    except BudgetExhausted:
        res.reason = "model budget exhausted"
        res.remaining = len(cands)
        return res

    res.remaining = len(cands)
    if not cands:
        res.reason = "no rule in the language reproduces all the evidence"
        return res
    if len({tuple(_run(c.rule, s) for s in batch) for c in cands}) > 1:
        res.reason = "question budget exhausted with a disagreement unresolved"
        return res
    best = min(cands, key=_size)
    res.status, res.rule, res.rule_hash = "committed", best.rule, best.hash
    res.summary, res.scope = best.summary, "batch_agreement"
    return res
