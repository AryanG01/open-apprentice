"""Metrics from stored per-task rows (spec 21.6-21.7). Pure functions; nothing here is typed by hand.

Conventions that matter for honesty:
  * success denominators are ALL scheduled tasks: abstentions, budget exhaustion and failures count as failures;
    conditional correctness (among committed answers) is reported separately.
  * false success = committed output the learner CLAIMED was fine that the private evaluator rejected.
  * uncertainty uses an EPISODE-CLUSTERED bootstrap: repetitions and tasks inside an episode are not independent.
  * costs stay separate dimensions; no merged cost score.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from statistics import mean
from typing import Iterable, Optional

COST_FIELDS = ("tokens", "calls", "actions", "solver_s", "teacher_interactions", "wall_s")


@dataclass(frozen=True)
class Row:
    episode: str
    rep: int
    method: str
    task_id: str
    stage: str
    committed: bool
    claimed_success: bool
    correct: Optional[bool]  # None until the private evaluator scores a COMMITTED output
    abstained: bool = False
    failure: Optional[str] = (
        None  # budget_exhausted | provider_error | model_format | unsupported | ...
    )
    tokens: int = 0
    calls: int = 0
    actions: int = 0
    solver_s: float = 0.0
    teacher_interactions: int = 0
    wall_s: float = 0.0
    usd: Optional[float] = None  # None = unknown, never zero
    origin: str = "live"  # live | mock | replay
    verdict: Optional[list] = (
        None  # EVALUATOR-PRIVATE: failed verifier checks (name, detail) for a committed-wrong output; never shown to a policy
    )


def select(
    rows: Iterable[Row],
    method: Optional[str] = None,
    stages: Optional[set[str]] = None,
    scored_only: bool = True,
) -> list[Row]:
    """`stage == 'learning'` rows carry teaching/learning COSTS; they are not scored tasks and never enter success denominators."""
    return [
        r
        for r in rows
        if (method is None or r.method == method)
        and (stages is None or r.stage in stages)
        and not (scored_only and r.stage == "learning")
    ]


def success_rate(rows: list[Row]) -> dict:
    n = len(rows)
    ok = sum(1 for r in rows if r.committed and r.correct is True)
    return {"correct": ok, "scheduled": n, "rate": ok / n if n else None}


def conditional_correctness(rows: list[Row]) -> dict:
    c = [r for r in rows if r.committed and not r.abstained and r.correct is not None]
    ok = sum(1 for r in c if r.correct)
    return {"correct": ok, "committed": len(c), "rate": ok / len(c) if c else None}


def false_success(rows: list[Row]) -> dict:
    claimed = [r for r in rows if r.committed and r.claimed_success and r.correct is not None]
    bad = sum(1 for r in claimed if not r.correct)
    return {
        "false_successes": bad,
        "claimed_successes": len(claimed),
        "rate": bad / len(claimed) if claimed else None,
    }


def failure_breakdown(rows: list[Row]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        key = (
            "abstained"
            if r.abstained
            else (r.failure or ("wrong_output" if r.committed and r.correct is False else None))
        )
        if key:
            out[key] = out.get(key, 0) + 1
    return out


def cost_totals(rows: list[Row]) -> dict:
    t = {f: sum(getattr(r, f) for r in rows) for f in COST_FIELDS}
    unknown = sum(1 for r in rows if r.usd is None)
    t["usd_known_total"] = sum(r.usd for r in rows if r.usd is not None)
    t["rows_with_unknown_usd"] = unknown
    return t


def episode_means(rows: list[Row], method: str, stages: Optional[set[str]]) -> dict[str, float]:
    """Per-episode success rate (averaged over repetitions and tasks), failures counted as 0."""
    by: dict[str, list[int]] = {}
    for r in select(rows, method, stages):
        by.setdefault(r.episode, []).append(1 if (r.committed and r.correct is True) else 0)
    return {e: mean(v) for e, v in by.items()}


def paired_cluster_bootstrap(
    rows: list[Row],
    a: str,
    b: str,
    stages: Optional[set[str]] = None,
    draws: int = 5000,
    seed: int = 0,
) -> dict:
    """Mean paired difference (a - b) with a 95% percentile interval, resampling EPISODES with replacement."""
    ma, mb = episode_means(rows, a, stages), episode_means(rows, b, stages)
    eps = sorted(set(ma) & set(mb))
    if len(eps) < 2:
        return {
            "a": a,
            "b": b,
            "n_episodes": len(eps),
            "diff": None,
            "ci95": None,
            "note": "fewer than 2 paired episodes: no uncertainty can be estimated",
        }
    d = [ma[e] - mb[e] for e in eps]
    rng = random.Random(seed)
    boots = sorted(mean(rng.choices(d, k=len(d))) for _ in range(draws))
    lo, hi = boots[int(0.025 * draws)], boots[int(0.975 * draws) - 1]
    return {
        "a": a,
        "b": b,
        "n_episodes": len(eps),
        "diff": mean(d),
        "ci95": [lo, hi],
        "draws": draws,
        "per_episode_diff": dict(zip(eps, d)),
        "note": "episode-clustered percentile bootstrap; with few episodes uncertainty is substantial",
    }


def method_summary(rows: list[Row], method: str, stages: Optional[set[str]] = None) -> dict:
    sel = select(rows, method, stages)
    costs = cost_totals(
        select(rows, method, None, scored_only=False)
    )  # learning + teaching costs INCLUDED
    return {
        "method": method,
        "success": success_rate(sel),
        "conditional": conditional_correctness(sel),
        "false_success": false_success(sel),
        "failures": failure_breakdown(sel),
        "costs": costs,
    }


def row_dicts(rows: list[Row]) -> list[dict]:
    return [asdict(r) for r in rows]
