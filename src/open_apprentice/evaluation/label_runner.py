"""Run one label-placement episode through the learner and score it. Evaluator side: it holds the truth, the learner does not.

Outcome codes keep the failure modes apart (handoff 17.5): a wrong commitment is not an abstention is not an environment error.
  correct_commit        committed; every fresh document passes intent + preservation + layout
  wrong_commit          committed; some fresh document fails an axis
  abstained             no commitment (reason kept)
  appropriate_abstain   abstained on an episode whose expected outcome is to abstain
  error                 the model/provider failed in a way that stopped the run
"""

from __future__ import annotations

from typing import Any

from open_apprentice.budget import Ledger
from open_apprentice.concepts.label_teaching import teach
from open_apprentice.evaluation.label_episodes import LabelEpisode, agent_visible, score_commit
from open_apprentice.providers.base import Provider


def score_and_row(ep: LabelEpisode, res: Any) -> dict[str, Any]:
    """Turn a TeachingResult into one outcome row, scoring a commitment on the fresh documents."""
    row: dict[str, Any] = {
        "id": ep.id,
        "kind": ep.kind,
        "expected": ep.expected,
        "status": res.status,
        "reason": res.reason,
        "questions": len(res.questions),
        "rounds": res.rounds,
        "model_calls": res.model_calls,
        "asked_when_expected": (len(res.questions) > 0) == (ep.kind == "ambiguous"),
    }
    if res.status == "committed" and res.rule is not None:
        score = score_commit(ep, res.rule)
        row["axes"] = score["per_scene"]
        row["outcome"] = "correct_commit" if score["complete"] else "wrong_commit"
        row["rule_hash"] = res.rule_hash
        row["scope"] = res.scope
    else:
        row["outcome"] = "appropriate_abstain" if ep.expected == "abstain" else "abstained"
    return row


async def run_episode(provider: Provider, ledger: Ledger, ep: LabelEpisode) -> dict[str, Any]:
    view = agent_visible(ep)
    demos = [(d["before"], d["after"]) for d in view["demonstrations"]]
    spent_before = (ledger.consumed_usd, ledger.consumed_tokens, ledger.consumed_calls)
    try:
        res = await teach(provider, ledger, demos, view["batch"], ep.teacher_answer)
    except Exception as e:  # recorded as an environment/provider error, never as a success
        return {
            "id": ep.id,
            "kind": ep.kind,
            "expected": ep.expected,
            "outcome": "error",
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }
    row = score_and_row(ep, res)
    row.update(
        usd=round(ledger.consumed_usd - spent_before[0], 6),
        tokens=ledger.consumed_tokens - spent_before[1],
    )
    return row
