"""The audit round: after a lone rule is settled, one extra generation round looks for OTHER rules that fit all the evidence.
If one concretely disagrees, the session asks (if it still can) or ends UNRESOLVED instead of committing confidently. MOCK replies."""

from tests.fixtures_rules import CLAMPED_MARGIN, CONST_MARGIN, PROP_MARGIN
from tests.unit.test_teaching_session import cand, demo_for, mk, pool  # noqa: F401
from open_apprentice.concepts.teaching import MAX_QUERIES, State


async def test_without_audit_a_lone_fitting_rule_is_committed_unchallenged(pool):
    s = mk([{"candidates": [cand("fixed 12px", CONST_MARGIN)]}], pool)
    await s.start(demo_for(CLAMPED_MARGIN()))
    assert s.state == State.INTENT_READY and s.queries_asked == 0 and s.rounds == 1


async def test_audit_surfaces_a_disagreeing_alternative_and_the_session_asks(pool):
    s = mk(
        [
            {"candidates": [cand("fixed 12px", CONST_MARGIN)]},
            {"candidates": [cand("8% of width", PROP_MARGIN())]},
        ],
        pool,
        audit=True,
    )
    await s.start(demo_for(CLAMPED_MARGIN()))
    assert s.rounds == 2 and len(s.candidates) == 2
    assert s.state == State.AWAITING_USER and s.pending_kind == "question"


async def test_audit_with_no_questions_left_abstains_instead_of_committing(pool):
    s = mk(
        [
            {"candidates": [cand("fixed 12px", CONST_MARGIN)]},
            {"candidates": [cand("8% of width", PROP_MARGIN())]},
        ],
        pool,
        audit=True,
    )
    s.queries_asked = MAX_QUERIES  # the user's patience is spent: a real disagreement can no longer be resolved by asking
    await s.start(demo_for(CLAMPED_MARGIN()))
    assert s.state == State.UNRESOLVED and "ambiguity_remains" in s.unresolved_reason


async def test_audit_that_finds_nothing_keeps_the_rule(pool):
    s = mk(
        [{"candidates": [cand("fixed 12px", CONST_MARGIN)]}, {"candidates": []}], pool, audit=True
    )
    await s.start(demo_for(CLAMPED_MARGIN()))
    assert s.state == State.INTENT_READY and s.rounds == 2 and len(s.candidates) == 1


async def test_audit_costs_at_most_one_extra_round(pool):
    s = mk(
        [
            {"candidates": [cand("fixed 12px", CONST_MARGIN)]},
            {"candidates": [cand("8% of width", PROP_MARGIN())]},
            {"candidates": [cand("clamped", CLAMPED_MARGIN())]},
        ],
        pool,
        audit=True,
    )
    await s.start(demo_for(CLAMPED_MARGIN()))
    assert s.rounds <= 3 and len(s.provider.calls) == 2
