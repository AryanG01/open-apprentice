"""When exactly one candidate fits and nothing was asked, round 2 asks for DIFFERENT rules that also fit, so a real
question can exist. The ledger/question/Neither machinery is unchanged."""

import json

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.schemas import IntentState
from open_apprentice.concepts.teaching import State, TeachingSession
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.providers.mock import MockProvider
from tests.fixtures_rules import CLAMPED_MARGIN
from tests.unit.test_teaching_session import demo_for

DOM = DomainManifest()
CONST12 = "let m = 12\nclone proto as badge at (card0.x + card0.w - m - proto.w, card0.y + m)"
PROP = (
    "let m = 0.08 * card0.w\nclone proto as badge at (card0.x + card0.w - m - proto.w, card0.y + m)"
)


def reply(*t):
    return {"candidates": [{"summary": f"c{i}", "rule_text": x} for i, x in enumerate(t)]}


def demo():
    d = demo_for(CLAMPED_MARGIN())
    for o in d["scene"]["objects"]:
        pass
    d["scene"]["objects"][0]["id"], d["scene"]["objects"][1]["id"] = "card0", "proto"
    d["after"] = {
        ("card0" if k == "obj0" else "proto" if k == "obj1" else k): v
        for k, v in d["after"].items()
    }
    return d


@pytest.fixture(scope="module")
def pool():
    with SolverPool() as p:
        yield p


def sess(script, pool, **kw):
    return TeachingSession(
        MockProvider({"hypotheses": script}),
        Ledger(Limits(tokens=500_000, calls=40)),
        DOM,
        [2],
        pool=pool,
        correction_turn=False,
        **kw,
    )


async def test_single_fit_triggers_an_alternatives_round_and_then_a_real_question(pool):
    s = sess([reply(CONST12), reply(PROP)], pool)
    await s.start(demo())
    assert s.rounds == 2 and len(s.candidates) == 2 and s.state == State.AWAITING_USER
    msg = json.loads(s.provider.calls[1][1][1].content)
    assert (
        "already_fitting_rules" in msg
        and "let m = 12" in msg["already_fitting_rules"][0]["rule_text"]
    )  # shown the rule to differ from


async def test_disabled_flag_or_no_alternatives_leaves_the_single_candidate_honestly_unquestioned(
    pool,
):
    s = sess([reply(CONST12)], pool, seek_disagreement=False)
    await s.start(demo())
    assert (
        s.rounds == 1
        and s.state == State.INTENT_READY
        and s.intent_state == IntentState.CONSISTENT_WITH_EXAMPLES
    )
    s2 = sess([reply(CONST12), reply(CONST12)], pool)  # the model offers nothing new
    await s2.start(demo())
    assert (
        s2.rounds == 2
        and len(s2.candidates) == 1
        and s2.intent_state == IntentState.CONSISTENT_WITH_EXAMPLES
    )


async def test_alternatives_that_contradict_the_evidence_are_rejected_and_the_original_is_kept(
    pool,
):
    wrong = "let m = 30\nclone proto as badge at (card0.x + card0.w - m - proto.w, card0.y + m)"
    s = sess([reply(CONST12), reply(wrong)], pool)
    await s.start(demo())
    assert len(s.candidates) == 1 and any(
        "contradicts" in r["reason"] for r in s.reports[-1].rejected
    )


async def test_alternatives_round_is_used_at_most_once_and_only_when_nothing_was_asked(pool):
    s = sess([reply(CONST12), reply(PROP)], pool)
    await s.start(demo())
    assert (
        s._alt_done and s.rounds == 2
    )  # a Neither afterwards ends honestly: no third round exists
