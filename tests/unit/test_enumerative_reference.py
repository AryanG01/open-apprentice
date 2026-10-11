"""The non-LLM reference on the same teaching machinery. These are fixtures/coverage facts about a DECLARED
grammar, not performance claims about any LLM."""

from fractions import Fraction as F

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.enumerative import EnumerativeSource
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.concepts.schemas import IntentState
from open_apprentice.concepts.teaching import State, TeachingSession
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.teacher import BenchmarkTeacher
from tests.fixtures_rules import (
    CLAMPED_MARGIN,
    R,
    badge_rule,
    gap_rule,
    get,
    op,
)
from tests.unit.test_teaching_session import demo_for, drive, scene, CANVAS

DOM = DomainManifest()


@pytest.fixture(scope="module")
def pool():
    with SolverPool() as p:
        yield p


def session(pool, counts=(2,)):
    src = EnumerativeSource(DOM, list(counts))
    return (
        TeachingSession(
            None,
            Ledger(Limits()),
            DOM,
            list(counts),
            pool=pool,
            teacher_source="benchmark_teacher",
            candidate_source=src,
        ),
        src,
    )


def behaves_like(
    rule, latent, widths=(24, 40, 60, 99, 100, 101, 150, 230, 299, 300, 301, 400, 512)
):
    for w in widths:
        sc = scene(w)
        a, b = (
            evaluate_rule(rule, sc["objects"], CANVAS)["badge"],
            evaluate_rule(latent, sc["objects"], CANVAS)["badge"],
        )
        if a != b:
            return False
    return True


def session_cap(pool, cap):
    src = EnumerativeSource(DOM, [2], max_candidates=cap)
    return (
        TeachingSession(
            None,
            Ledger(Limits()),
            DOM,
            [2],
            pool=pool,
            teacher_source="benchmark_teacher",
            candidate_source=src,
        ),
        src,
    )


async def test_reference_learns_a_proportional_badge_with_questions_and_no_model(pool):
    from tests.fixtures_rules import PROP_MARGIN

    latent = PROP_MARGIN()
    s, src = session(pool)
    await s.start(demo_for(latent))
    await drive(s, BenchmarkTeacher(latent))
    assert s.state == State.INTENT_READY and behaves_like(s.finalize().rule, latent)
    st = src.stats[0]
    assert (
        st["label"] == "ENUMERATIVE"
        and st["enumerated"] > 0
        and st["cpu_seconds"] >= 0
        and st["limit_hit"] is False
    )


@pytest.mark.parametrize("cap", [4, 64])
async def test_clamped_latent_is_not_resolved_within_the_teaching_budget_and_is_never_forced(
    pool, cap
):
    """Observed (deterministic) behaviour, an identifiability limit of the 2-query allowance, not a pass:
    the first question hits 'neither' (the true rule is outside the kept candidates), a counted corrected example
    triggers the deeper grammar, and a second question still cannot separate the survivors."""
    latent = CLAMPED_MARGIN()
    s, src = session_cap(pool, cap)
    t = BenchmarkTeacher(latent)
    await s.start(demo_for(latent))
    await drive(s, t)
    assert t.interactions == ["answer", "corrected_example", "answer"]
    assert s.state == State.UNRESOLVED and "ambiguity_remains" in s.unresolved_reason
    assert s.queries_asked == 2 and s.rounds == 2 and len(s.candidates) >= 2
    assert [x["grammar_round"] for x in src.stats] == [1, 2]
    with pytest.raises(ValueError):
        s.finalize()  # an unresolved session cannot be turned into a concept


def test_solver_pool_close_is_safe_when_never_started_or_called_twice():
    p = SolverPool()
    p.close()
    p.close()


async def test_reference_recovers_an_omitted_style_rule_only_via_the_deeper_grammar_after_neither(
    pool,
):
    latent = badge_rule(
        op("add", 12, op("div", op("sub", get(R("objects.0"), "w"), 150), 10))
    )  # 0.1*w - 3
    s, src = session(pool)
    await s.start(demo_for(latent))
    t = BenchmarkTeacher(latent)
    await drive(s, t)
    assert "corrected_example" in t.interactions and [x["grammar_round"] for x in src.stats] == [
        1,
        2,
    ]
    assert s.state == State.INTENT_READY and s.intent_state == IntentState.USER_CORRECTED
    assert behaves_like(s.finalize().rule, latent)


async def test_coverage_is_reported_honestly_when_the_target_is_outside_the_grammar(pool):
    outside = badge_rule(
        op("add", op("mul", get(R("objects.0"), "w"), {"rat": "7/100"}), {"rat": "1/3"})
    )  # 0.07w + 1/3
    s, src = session(pool)
    await s.start(demo_for(outside))
    t = BenchmarkTeacher(outside)
    await drive(s, t)
    assert s.state == State.UNRESOLVED and any(
        x["expressible"] is False for x in src.stats
    )  # not faked


async def test_reference_distinguishes_edge_gap_from_center_pitch_on_a_row(pool):
    latent = gap_rule(gap=24, left=80, top=120)
    objs = [
        {"id": f"obj{i}", "x": F(10 * i), "y": F(300), "w": F(w), "h": F(50)}
        for i, w in enumerate((100, 100, 100))
    ]
    sc = {"objects": objs, "canvas": CANVAS}
    demo = {"scene": sc, "after": evaluate_rule(latent, objs, CANVAS)}
    s, src = session(pool, counts=(3,))
    await s.start(demo)
    # equal widths of 100 + gap 24 == pitch 124: both rules fit => a real question is needed
    assert len(s.candidates) == 2 and s.state == State.AWAITING_USER
    await drive(s, BenchmarkTeacher(latent))
    assert s.state == State.INTENT_READY
    uneq = [
        {"id": f"obj{i}", "x": F(0), "y": F(0), "w": F(w), "h": F(50)}
        for i, w in enumerate((60, 140, 90))
    ]
    assert evaluate_rule(s.finalize().rule, uneq, CANVAS) == evaluate_rule(latent, uneq, CANVAS)
