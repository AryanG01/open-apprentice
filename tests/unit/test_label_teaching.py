"""The label-placement teaching loop with a SCRIPTED proposer (MOCK, never model evidence). It exercises the loop's logic:
filtering on all evidence, batch-first questions, commit/abstain, and the scoring - not any language model."""

import json

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.evaluation.label_episodes import build_manifest, consistent_classes
from open_apprentice.evaluation.label_runner import run_episode
from open_apprentice.evaluation.labels import rule_for_spec
from open_apprentice.providers.mock import MockProvider

pytestmark = pytest.mark.asyncio


def _proposer(ep):
    """Returns up to 4 catalogue behaviours consistent with the demonstrations (an oracle-assisted proposer: it knows the
    catalogue). For unsupported/noisy episodes nothing is consistent, so it proposes nothing."""
    specs = [v[0] for v in consistent_classes(ep.demos).values()][:4]
    reply = {"candidates": [{"summary": f"{s}", "rule": rule_for_spec(s)} for s in specs]}
    return MockProvider({}, functions={"hypotheses": lambda m: reply})


@pytest.fixture(scope="module")
def dev():
    return build_manifest("development")


async def test_the_loop_commits_correctly_asks_only_when_needed_and_abstains_otherwise(dev):
    rows = []
    for ep in dev:
        rows.append(await run_episode(_proposer(ep), Ledger(Limits(tokens=10**7, calls=1000)), ep))
    by_kind = {
        k: [r for r in rows if r["kind"] == k]
        for k in ("unambiguous", "ambiguous", "unsupported", "noisy")
    }
    assert all(
        r["outcome"] == "correct_commit" and r["questions"] == 0 for r in by_kind["unambiguous"]
    ), by_kind["unambiguous"]
    assert all(
        r["outcome"] == "correct_commit" and r["questions"] >= 1 for r in by_kind["ambiguous"]
    ), [(r["id"], r["outcome"], r["questions"], r.get("reason")) for r in by_kind["ambiguous"]]
    assert all(
        r["outcome"] == "appropriate_abstain" for r in by_kind["unsupported"] + by_kind["noisy"]
    )


async def test_a_proposer_that_returns_only_wrong_but_fitting_rules_is_caught_by_the_questions(dev):
    ep = next(e for e in dev if e.kind == "ambiguous")
    truth_cls = None
    from open_apprentice.evaluation.label_episodes import behaviour_class

    truth_cls = behaviour_class(ep.truth)
    wrong = [v[0] for k, v in consistent_classes(ep.demos).items() if k != truth_cls][:2]
    reply = {"candidates": [{"summary": "w", "rule": rule_for_spec(s)} for s in wrong]}
    row = await run_episode(
        MockProvider({}, functions={"hypotheses": lambda m: reply}),
        Ledger(Limits(tokens=10**7, calls=1000)),
        ep,
    )
    # the truth was never proposed: the loop must not commit a rule that the teacher's answer contradicts
    assert row["outcome"] != "correct_commit"
    assert row["status"] == "abstained" or row["outcome"] == "wrong_commit"


async def test_a_model_that_never_answers_is_an_error_not_an_abstention():
    from open_apprentice.providers.base import ProviderError

    class Down(MockProvider):
        async def _call(self, messages, *, max_tokens, ctx):
            raise ProviderError("transport failure: ProxyError")

    ep = build_manifest("development")[0]
    row = await run_episode(Down({}), Ledger(Limits(tokens=10**7, calls=1000)), ep)
    assert row["outcome"] == "error" and "ProxyError" in row["error"]


async def test_survivors_that_agree_on_the_batch_trigger_a_contrastive_round_and_a_dead_end_feeds_back_the_contradiction():
    ep = next(e for e in build_manifest("development") if e.kind == "ambiguous")
    from open_apprentice.evaluation.label_episodes import behaviour_class

    classes = consistent_classes(ep.demos)
    truth_cls = behaviour_class(ep.truth)
    wrong = [v[0] for k, v in classes.items() if k != truth_cls][:1]
    calls = []

    def reply(messages):
        user = json.loads(messages[-1].content)
        calls.append(user)
        specs = wrong if len(calls) == 1 else [ep.truth]
        return {
            "candidates": [{"summary": f"c{len(calls)}", "rule": rule_for_spec(s)} for s in specs]
        }

    row = await run_episode(
        MockProvider({}, functions={"hypotheses": reply}),
        Ledger(Limits(tokens=10**7, calls=1000)),
        ep,
    )
    assert (
        len(calls) >= 2 and "already_fitting_rules" in calls[1]
    )  # lone/agreeing survivors -> contrastive round
    assert (
        row["outcome"] == "correct_commit"
    )  # the contrastive round supplied the truth, the batch question then chose it
