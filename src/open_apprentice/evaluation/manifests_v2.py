"""Priced run manifests and the paid-run gate (spec 7 "Paid-run gating"; evaluator side).

A live run needs a manifest the owner approved in chat, copied to docs/evaluation/approved/<id>.json with
approved/approved_by/approved_at added; its id is the hash of its terms, so an edited copy no longer matches, and the
run's split, systems, episodes and repeats must be exactly the manifest's. (The approval file is a record, not an
access control: whoever writes it must be acting on the owner's word in chat.) The gate runs before any provider is built: no manifest,
an unapproved or edited one, a cap above its ceiling, or a cap that would reach into the protected reserve refuses.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Optional

from open_apprentice.evaluation.battery_v2 import REPO, Episode
from open_apprentice.evaluation.spend import load_budget, spendable, spent_so_far
from open_apprentice.teaching import codec

APPROVED = REPO / "docs/evaluation/approved"
BUDGET_ROOT = REPO / "results/redesign"
WORST_USD_PER_M = 4.0  # SpendGuard's conservative rate
PROMPT_CAP_TOKENS = 16_000  # assumed largest prompt per attempt (dry run: B's largest turn ~ 9k)
MAX_COMPLETION_TOKENS = (
    32_000  # NEBIUS_COMPLETION_CAP: the provider raises every call's max_tokens to this floor
)
MODEL_ROLES = ("hypotheses", "agent", "agent_b", "correction_scope")
ATTEMPTS = {
    "A": 8 + 4,
    "A2": 8 + 4,
    "B": 8 + 4,
    "C": 8 + 4,
    "D": 8 + 4,
    "D2": 8 + 4,
}  # learning + one correction cycle (spec 3.7)
STRATA_ORDER = ("catalogue", "beyond", "inconsistent", "unsupported", "sequential")


class GateRefused(Exception):
    pass


APPROVAL_FIELDS = ("manifest_id", "approved", "approved_by", "approved_at")


def manifest_id(m: dict) -> str:
    """Hash of the manifest's terms; the approval fields the owner's copy adds are not part of them."""
    return codec.digest({k: v for k, v in m.items() if k not in APPROVAL_FIELDS})[:16]


def _per_attempt_worst() -> float:
    return round((PROMPT_CAP_TOKENS + MAX_COMPLETION_TOKENS) * WORST_USD_PER_M / 1e6, 4)


def measured_call_usd(budget_root: Path = BUDGET_ROOT) -> float:
    """Mean real cost of one model call in earlier live teaching runs (spend.jsonl)."""
    f = Path(budget_root) / "spend.jsonl"
    rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []
    usd = [r["usd"] for r in rows if r.get("role") in MODEL_ROLES]
    return round(sum(usd) / len(usd), 4) if usd else 0.0


V2_CALL_FACTOR = 1.6  # policy v2 (A2, D2) makes more proposal calls than A and D: estimated, replaced by measurement


def _attempts(tokens: dict, system: str) -> float:
    """Mean attempts per episode of a system; A2 and D2 are priced from A and D with V2_CALL_FACTOR more calls."""
    per = tokens["per_system"]
    if system in per:
        return per[system]["attempts_mean"]
    return per[system.rstrip("2")]["attempts_mean"] * V2_CALL_FACTOR


def _estimate(counts: dict[str, int], tokens: dict, call_usd: float) -> tuple[float, float]:
    """(expected calls, dollars): runs x the dry run's mean attempts per episode x the measured cost per call."""
    calls = sum(n * _attempts(tokens, s) for s, n in counts.items())
    return round(calls, 2), round(calls * call_usd, 4)


def _finish(m: dict) -> dict:
    m["manifest_id"] = manifest_id(m)
    return m


def calibration_manifest(
    dev_battery: list[Episode],
    tokens: dict,
    spent_usd: float,
    spendable_usd: float,
    reserve_usd: float,
    call_usd: float,
    ceiling_usd: Optional[float] = None,
    systems: tuple[str, ...] = ("A", "B"),
    episodes: int = 5,
    repeats: int = 1,
    task_ids: Optional[list[str]] = None,
) -> dict:
    """Calibration: a few development episodes x A, B. It measures prompt/parse viability and cost per episode."""
    picked: list[Episode] = []
    if task_ids:
        by_id = {e.id: e for e in dev_battery}
        picked = [by_id[i] for i in task_ids]
    for stratum in () if task_ids else STRATA_ORDER * episodes:
        nxt = next((e for e in dev_battery if e.stratum == stratum and e not in picked), None)
        if nxt is not None and len(picked) < episodes:
            picked.append(nxt)
    runs = len(picked) * len(systems) * repeats
    per_attempt = _per_attempt_worst()
    worst_total = round(sum(len(picked) * repeats * ATTEMPTS[s] * per_attempt for s in systems), 4)
    est_calls, est_usd = _estimate({s: len(picked) * repeats for s in systems}, tokens, call_usd)
    if ceiling_usd is None:
        ceiling_usd = min(
            worst_total, math.ceil(est_usd * 2 * 20) / 20
        )  # 2x headroom, rounded up to $0.05
    ceiling = ceiling_usd
    remaining = round(spendable_usd - spent_usd, 4)
    return _finish(
        {
            "kind": "calibration",
            "split": "dev",
            "task_ids": [e.id for e in picked],
            "task_strata": [e.stratum for e in picked],
            "systems": list(systems),
            "repeats": repeats,
            "runs": runs,
            "attempt_ceilings": {s: ATTEMPTS[s] for s in systems},
            "worst_case_per_attempt_usd": per_attempt,
            "worst_case_total_usd": worst_total,
            "estimate_calls": est_calls,
            "estimate_usd": est_usd,
            "estimate_basis": (
                f"dry-run mean attempts per episode x ${call_usd} per call (mean of earlier live teaching calls in "
                "spend.jsonl); the fixture B stops early, so B's share is a lower bound"
            ),
            "ceiling_usd": ceiling,
            "expected_coverage": round(min(1.0, ceiling / est_usd), 2) if est_usd else 1.0,
            "stop_conditions": {
                "run_cap": "SpendGuard stops the run when the next call's worst case would pass --cap-usd",
                "global_ceiling": "SpendGuard stops when the shared spend would pass min(authorized, funded) - reserve",
                "boundary_violation": "any information-boundary violation stops the run and is reported",
            },
            "protected_reserve_usd": reserve_usd,
            "budget_at_writing": {
                "spent_usd": spent_usd,
                "spendable_usd": spendable_usd,
                "remaining_usd": remaining,
                "ceiling_fits": ceiling <= remaining,
            },
            "establishes": (
                "prompt and parse viability for A and B and the cost per episode on development episodes; "
                "not an A-versus-B result"
            ),
            "approved": False,
        }
    )


def calibration_note(m: dict, note: str) -> dict:
    """The same terms plus a stated purpose (part of the hashed terms)."""
    return _finish({k: v for k, v in m.items() if k != "manifest_id"} | {"note": note})


def measured_episode_usd(results_root: Path = REPO / "results/eval_v2") -> dict[str, float]:
    """Mean real cost of one episode per system, over the live calibration rows (dollar-cap stops left out)."""
    per: dict[str, list[float]] = {}
    for f in sorted(Path(results_root).glob("cal-*/rows.jsonl")):
        for line in f.read_text().splitlines():
            r = json.loads(line) if line.strip() else None
            if (
                r
                and r.get("origin") == "live"
                and r.get("failure") != "budget_stop"
                and r.get("usd")
            ):
                per.setdefault(r["method"], []).append(float(r["usd"]))
    return {k: round(sum(v) / len(v), 4) for k, v in sorted(per.items())}


def d_episode_ids(episodes: list[dict]) -> list[str]:
    """The D ablation set (spec 7: 8 clarification-required episodes): the clarification-required catalogue episodes,
    then the first sequential ones by id, up to 8. A fixed rule, chosen before any final result."""
    cat = sorted(
        e["id"] for e in episodes if e["stratum"] == "catalogue" and e["clarification_required"]
    )
    seq = sorted(
        e["id"] for e in episodes if e["stratum"] == "sequential" and e["clarification_required"]
    )
    return (cat + seq)[:8]


def funded_manifests(
    final_ids: list[str],
    clarify_ids: list[str],
    episode_usd: dict[str, float],
    reserve_usd: float,
    repeats: int = 3,
    ab_ceiling_usd: Optional[float] = None,
    d_ceiling_usd: Optional[float] = None,
) -> tuple[dict, dict]:
    """Tier T3 (spec 7) as two gated runs (a gate binds one run shape): A and B x 3 on every final episode, and D x 3
    on the clarification-required ones. Estimates come from the live calibrations; the ceiling adds 25% headroom.
    Generated, not approved."""

    def one(
        kind: str, systems: list[str], ids: list[str], what: str, ceiling: Optional[float]
    ) -> dict:
        runs = len(ids) * len(systems) * repeats
        est = round(sum(len(ids) * repeats * episode_usd[s] for s in systems), 2)
        return _finish(
            {
                "kind": kind,
                "split": "final",
                "systems": systems,
                "task_ids": list(ids),
                "repeats": repeats,
                "runs": runs,
                "attempt_ceilings": {s: ATTEMPTS[s] for s in systems},
                "worst_case_per_attempt_usd": _per_attempt_worst(),
                "episode_usd_measured": {s: episode_usd[s] for s in systems},
                "estimate_usd": est,
                "ceiling_usd": ceiling if ceiling is not None else math.ceil(est * 1.25 * 20) / 20,
                "expected_coverage": round(min(1.0, ceiling / est), 2) if ceiling and est else 1.0,
                "stop_conditions": {
                    "run_cap": "no new run starts unless every run in flight can still make one call",
                    "global_ceiling": "SpendGuard stops when the shared spend would pass min(authorized, funded) - reserve",
                    "boundary_violation": "any information-boundary violation stops the run and is reported",
                },
                "protected_reserve_usd": reserve_usd,
                "establishes": what,
                "approved": False,
            }
        )

    ab = one(
        "funded_T3_AB",
        ["A", "B"],
        final_ids,
        "the paired A-versus-B comparison on the frozen battery (both primary endpoints)",
        ab_ceiling_usd,
    )
    d = one(
        "funded_T3_D",
        ["D"],
        clarify_ids,
        "the question-selection ablation (A's policy with uniform questions) on the clarification-required episodes",
        d_ceiling_usd,
    )
    return ab, d


def check_live_gate(
    mid: Optional[str],
    cap_usd: float,
    run: dict,
    approved_dir: Path = APPROVED,
    budget_root: Path = BUDGET_ROOT,
) -> dict:
    if not mid:
        raise GateRefused("a live run needs --manifest naming an owner-approved manifest")
    f = Path(approved_dir) / f"{mid}.json"
    if not f.exists():
        raise GateRefused(f"manifest {mid} has not been approved ({f} is missing)")
    m = json.loads(f.read_text())
    if manifest_id(m) != mid or m.get("manifest_id") != mid:
        raise GateRefused(
            f"approved file {f.name} does not match its manifest id (edited after approval?)"
        )
    if m.get("approved") is not True or not m.get("approved_by") or not m.get("approved_at"):
        raise GateRefused(
            f"{f.name} lacks the owner's approval fields (approved, approved_by, approved_at)"
        )
    want = {
        "split": m["split"],
        "systems": m["systems"],
        "episodes": m["task_ids"],
        "repeats": m["repeats"],
    }
    got = {k: run.get(k) for k in want}
    if got != want:
        raise GateRefused(f"this run {got} is not the approved manifest's run {want}")
    if not cap_usd > 0:
        raise GateRefused("--cap-usd must be positive")
    if cap_usd > m["ceiling_usd"]:
        raise GateRefused(f"--cap-usd {cap_usd} is above the manifest ceiling {m['ceiling_usd']}")
    budget = load_budget(Path(budget_root))
    spent, allowed = spent_so_far(Path(budget_root)), spendable(budget)
    if spent + cap_usd > allowed:
        raise GateRefused(
            f"the cap would reach into the protected ${budget['reserve_usd']:.0f} reserve: spent ${spent:.2f} + cap "
            f"${cap_usd:.2f} > spendable ${allowed:.2f}"
        )
    return m


def _not_wired(manifest: dict, cap: float, provider_factory: Callable[[], Any]) -> None:
    raise NotImplementedError(
        "the gate passed, but live learner execution is wired only after the owner approves a calibration manifest"
    )


def run_live(
    mid: Optional[str],
    cap_usd: float,
    provider_factory: Callable[[], Any],
    run: dict,
    approved_dir: Path = APPROVED,
    budget_root: Path = BUDGET_ROOT,
    runner: Callable[[dict, float, Callable[[], Any]], Any] = _not_wired,
) -> Any:
    """Gate first; the provider factory is handed on only after every check passed."""
    manifest = check_live_gate(mid, cap_usd, run, approved_dir, budget_root)
    return runner(manifest, cap_usd, provider_factory)
