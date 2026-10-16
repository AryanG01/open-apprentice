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
ESTIMATE_USD_PER_M = 3.5  # output-heavy teaching runs (live-run cost note)
WORST_USD_PER_M = 4.0  # SpendGuard's conservative rate
PROMPT_CAP_TOKENS = 16_000  # assumed largest prompt per attempt (dry run: B's largest turn ~ 9k)
MAX_COMPLETION_TOKENS = 6_000  # the proposers' max_tokens
ATTEMPTS = {
    "A": 8 + 4,
    "B": 8 + 4,
    "C": 8 + 4,
    "D": 8 + 4,
}  # learning + one correction cycle (spec 3.7)
RESERVE_USD = 10.0
STRATA_ORDER = ("catalogue", "beyond", "inconsistent", "unsupported", "sequential")


class GateRefused(Exception):
    pass


APPROVAL_FIELDS = ("manifest_id", "approved", "approved_by", "approved_at")


def manifest_id(m: dict) -> str:
    """Hash of the manifest's terms; the approval fields the owner's copy adds are not part of them."""
    return codec.digest({k: v for k, v in m.items() if k not in APPROVAL_FIELDS})[:16]


def _per_attempt_worst() -> float:
    return round((PROMPT_CAP_TOKENS + MAX_COMPLETION_TOKENS) * WORST_USD_PER_M / 1e6, 4)


def _estimate(counts: dict[str, int], tokens: dict) -> tuple[int, float]:
    t = sum(n * tokens["per_system"][s]["tokens_per_episode"] for s, n in counts.items())
    return t, round(t * ESTIMATE_USD_PER_M / 1e6, 4)


def _finish(m: dict) -> dict:
    m["manifest_id"] = manifest_id(m)
    return m


def calibration_manifest(
    dev_battery: list[Episode],
    tokens: dict,
    spent_usd: float,
    spendable_usd: float,
    systems: tuple[str, ...] = ("A", "B"),
    episodes: int = 5,
    repeats: int = 1,
) -> dict:
    """Calibration: a few development episodes x A, B. It measures prompt/parse viability and cost per episode."""
    picked: list[Episode] = []
    for stratum in STRATA_ORDER * episodes:
        nxt = next((e for e in dev_battery if e.stratum == stratum and e not in picked), None)
        if nxt is not None and len(picked) < episodes:
            picked.append(nxt)
    runs = len(picked) * len(systems) * repeats
    per_attempt = _per_attempt_worst()
    worst_total = round(sum(len(picked) * repeats * ATTEMPTS[s] * per_attempt for s in systems), 4)
    est_tokens, est_usd = _estimate({s: len(picked) * repeats for s in systems}, tokens)
    ceiling = min(worst_total, math.ceil(est_usd * 2 * 20) / 20)  # 2x headroom, rounded up to $0.05
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
            "estimate_tokens": est_tokens,
            "estimate_usd": est_usd,
            "estimate_basis": (
                f"dry-run token estimate per episode x ${ESTIMATE_USD_PER_M}/M; completion tokens assumed "
                f"{tokens.get('completion_assumed_per_attempt', 'n/a')} per attempt"
            ),
            "ceiling_usd": ceiling,
            "stop_conditions": {
                "run_cap": "SpendGuard stops the run when the next call's worst case would pass --cap-usd",
                "global_ceiling": "SpendGuard stops when the shared spend would pass min(authorized, funded) - reserve",
                "boundary_violation": "any information-boundary violation stops the run and is reported",
            },
            "protected_reserve_usd": RESERVE_USD,
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


def funded_manifest(n_final: int, n_clarify: int, tokens: dict, repeats: int = 3) -> dict:
    """Tier T3 (spec 7): A and B x 3 on all final episodes + D x 3 on the clarification-required ones. Generated, not
    approved; re-estimated after calibration."""
    counts = {"A": n_final * repeats, "B": n_final * repeats, "D": n_clarify * repeats}
    per_attempt = _per_attempt_worst()
    est_tokens, est_usd = _estimate(counts, tokens)
    return _finish(
        {
            "kind": "funded_T3",
            "split": "final",
            "runs": sum(counts.values()),
            "runs_per_system": counts,
            "attempt_ceilings": {s: ATTEMPTS[s] for s in counts},
            "worst_case_per_attempt_usd": per_attempt,
            "worst_case_total_usd": round(
                sum(n * ATTEMPTS[s] * per_attempt for s, n in counts.items()), 2
            ),
            "estimate_tokens": est_tokens,
            "estimate_usd": est_usd,
            "protected_reserve_usd": RESERVE_USD,
            "establishes": "the paired A-versus-B comparison on the frozen battery (both primary endpoints)",
            "approved": False,
            "note": "re-estimate from the calibration run before asking for approval",
        }
    )


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
