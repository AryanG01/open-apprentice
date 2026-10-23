"""Clarification query selection (spec 8.6). A limited disagreement heuristic, NOT Socrates and not
optimal experiment design: it measures disagreement inside a sampled hypothesis set only.

  partition_weight = candidates_in_partition / total_candidates
  disagreement     = -sum(partition_weight * log2(partition_weight))
  query_score      = disagreement / max(1, estimated_query_cost_units)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.rules import FIELDS, RuleError, evaluate_rule
from open_apprentice.concepts.schemas import sha
from open_apprentice.concepts.witness import SolverBudget, SolverPool, find_disagreement

MAX_OPTIONS = 4  # query envelope: up to four predicted outputs + Neither
MAX_SCENES = 8


def differs(a: dict, b: dict, thr: Fraction) -> bool:
    for key in set(a) | set(b):
        if (key in a) != (key in b):
            return True
        if any(abs(a[key][f] - b[key][f]) > thr for f in FIELDS):
            return True
    return False


def partition(preds: list[Optional[dict]], thr: Fraction) -> list[list[int]]:
    """Group candidate indices whose predictions are visibly equivalent (frozen tolerance).
    Candidates that fail to evaluate on this scene are excluded from the question."""
    groups: list[tuple[dict, list[int]]] = []
    for i, p in enumerate(preds):
        if p is None:
            continue
        for rep, members in groups:
            if not differs(rep, p, thr):
                members.append(i)
                break
        else:
            groups.append((p, [i]))
    return [m for _, m in groups]


def disagreement_entropy(groups: list[list[int]]) -> float:
    total = sum(len(g) for g in groups)
    return -sum((len(g) / total) * math.log2(len(g) / total) for g in groups) if total else 0.0


@dataclass
class ScoredScene:
    scene: dict  # {"objects": [...], "canvas": {...}}
    source: str  # "solver_witness" | "sampled"
    groups: list[list[int]]
    predictions: list[Optional[dict]]
    entropy: float
    cost_units: int
    score: float


def predict(rules: list[list], scene: dict) -> list[Optional[dict]]:
    out = []
    for r in rules:
        try:
            out.append(evaluate_rule(r, scene["objects"], scene["canvas"]))
        except RuleError:
            out.append(None)
    return out


def score_scene(rules: list[list], scene: dict, source: str, thr: Fraction) -> ScoredScene:
    preds = predict(rules, scene)
    groups = partition(preds, thr)
    cost = max(1, len(scene["objects"]))  # user inspects each object
    h = disagreement_entropy(groups)
    return ScoredScene(scene, source, groups, preds, h, cost, h / cost)


def sample_scenes(dom: DomainManifest, object_counts: list[int], k: int, seed: int) -> list[dict]:
    """Deterministic, in-domain, readable (multiples of 10) fallback scenes. Labelled 'sampled'."""
    rng = random.Random(seed)
    scenes = []
    for _ in range(k):
        n = rng.choice(object_counts)
        cw, ch = rng.randrange(400, 1000, 100), rng.randrange(300, 700, 100)
        objs, x = [], 10
        for i in range(n):
            w, h = rng.randrange(30, 200, 10), rng.randrange(30, 120, 10)
            objs.append(
                {
                    "id": f"obj{i}",
                    "x": Fraction(x),
                    "y": Fraction(rng.randrange(10, 100, 10)),
                    "w": Fraction(w),
                    "h": Fraction(h),
                }
            )
            x += w + 10
        canvas = {"w": Fraction(max(cw, x + 10)), "h": Fraction(ch)}
        if dom.contains(objs, canvas):
            scenes.append({"objects": objs, "canvas": canvas})
    return scenes


def propose_scenes(
    rules: list[list],
    dom: DomainManifest,
    object_counts: list[int],
    budget: SolverBudget,
    pool: Optional[SolverPool] = None,
    seed: int = 0,
    trace: Optional[dict] = None,
) -> list[tuple[dict, str]]:
    """Up to 8 candidate scenes: one solver witness per disagreeing candidate pair, then sampled fill.
    Every returned scene is validated concretely when scored; solver output is never trusted alone.
    """
    scenes: list[tuple[dict, str]] = []
    if len(rules) >= 2:
        from itertools import combinations

        for i, j in combinations(range(len(rules)), 2):
            if len(scenes) >= MAX_SCENES - 2 or not budget.can_run():
                break
            res = find_disagreement(
                [rules[i], rules[j]], object_counts, dom, budget=budget, pool=pool
            )
            if (
                trace is not None
            ):  # what the solver did, for the "show your work" view (no rules, no indices)
                trace.setdefault("witness_searches", []).append(
                    {
                        "status": res.status,
                        "elapsed_ms": res.elapsed_ms,
                        "cases": len(res.cases),
                        "solver_version": res.solver_version,
                    }
                )
            if res.witness is not None:
                scenes.append(
                    (
                        {"objects": res.witness.objects, "canvas": res.witness.canvas},
                        "solver_witness",
                    )
                )
    for s in sample_scenes(dom, object_counts, MAX_SCENES - len(scenes), seed):
        scenes.append((s, "sampled"))
    return scenes[:MAX_SCENES]


def select_query(
    rules: list[list],
    dom: DomainManifest,
    object_counts: list[int],
    budget: SolverBudget,
    pool: Optional[SolverPool] = None,
    seed: int = 0,
    prefer_readable: bool = False,
    trace: Optional[dict] = None,
) -> Optional[ScoredScene]:
    """Pick the highest-scoring scene on which at least two candidates visibly disagree, else None.

    Ties go to the solver witness (exact, but its simplest form can be degenerate: tiny objects stacked at the origin).
    `prefer_readable` flips that tie-break to the sampled scene, for questions a person has to look at; scores still decide first.
    """
    thr = dom.query_visible_difference_px
    scored = [
        score_scene(rules, s, src, thr)
        for s, src in propose_scenes(rules, dom, object_counts, budget, pool, seed, trace)
    ]
    if trace is not None:
        trace["scenes_considered"] = len(scored)
    scored = [s for s in scored if len(s.groups) >= 2]
    return max(
        scored,
        key=lambda s: (
            s.score,
            (s.source == "sampled") if prefer_readable else (s.source == "solver_witness"),
        ),
        default=None,
    )


# ----------------------------------------------------------------------------- query envelope
@dataclass
class Query:
    query_id: str
    candidate_set_hash: str
    input_scene: dict
    options: dict[str, dict]  # option id -> predicted output (what the user is shown)
    option_members: dict[
        str, list[int]
    ]  # PRIVATE to the learner: which candidates each option came from
    source: str


def candidate_set_hash(rules: list[list]) -> str:
    return sha([sha(r) for r in rules])


def build_query(rules: list[list], sc: ScoredScene) -> Query:
    groups = sc.groups[:MAX_OPTIONS]
    letters = "ABCD"
    options = {letters[i]: sc.predictions[g[0]] for i, g in enumerate(groups)}
    members = {letters[i]: g for i, g in enumerate(groups)}
    csh = candidate_set_hash(rules)
    qid = sha({"csh": csh, "scene": sc.scene})[:16]
    return Query(qid, csh, sc.scene, options, members, sc.source)


def public_view(q: Query) -> dict:
    """What the teacher/user sees: scene + neutral options + Neither. No candidate indices, no rules."""
    return {
        "query_id": q.query_id,
        "candidate_set_hash": q.candidate_set_hash,
        "input_scene": q.input_scene,
        "options": q.options,
        "extra_options": ["neither"],
    }


def apply_answer(rules: list[list], q: Query, answer: str, candidate_set: str) -> list[int]:
    """Indices of candidates consistent with the answer. 'neither' => none: the set must be expanded
    or teaching ends unresolved. A stale answer (different candidate set) is rejected, never applied.
    """
    if candidate_set != candidate_set_hash(rules) or candidate_set != q.candidate_set_hash:
        raise ValueError(
            "stale or mismatched answer: candidate set changed since the question was asked"
        )
    if answer == "neither":
        return []
    if answer not in q.option_members:
        raise ValueError(f"unknown option {answer!r}")
    return list(q.option_members[answer])
