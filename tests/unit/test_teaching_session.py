"""Teaching sessions end-to-end with MOCK provider replies (fixture origin) and the deterministic
benchmark teacher. These show orchestration + honesty properties, NOT Nemotron's candidate quality."""

import json
from fractions import Fraction as F

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.concepts.schemas import IntentState
from open_apprentice.concepts.teaching import MAX_QUERIES, State, TeachingSession
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.teacher import BenchmarkTeacher
from open_apprentice.providers.mock import MockProvider
from tests.fixtures_rules import CLAMPED_MARGIN, CONST_MARGIN, PROP_MARGIN, R, badge_rule, get, op

DOM = DomainManifest()
CANVAS = {"w": F(800), "h": F(600)}


def scene(w):
    return {
        "objects": [
            {"id": "obj0", "x": F(100), "y": F(100), "w": F(w), "h": F(80)},
            {"id": "obj1", "x": F(0), "y": F(0), "w": F(20), "h": F(20)},
        ],
        "canvas": CANVAS,
    }


def demo_for(latent, w=150):
    s = scene(w)
    return {"scene": s, "after": evaluate_rule(latent, s["objects"], s["canvas"])}


def cand(summary, rule):
    return {"summary": summary, "rule": rule}


def budget():
    return Ledger(Limits(tokens=500_000, calls=64))


@pytest.fixture(scope="module")
def pool():
    with SolverPool() as p:
        yield p


async def drive(sess, teacher):
    """Run a session to a terminal state using the teacher, like the UI would."""
    guard = 0
    while sess.state == State.AWAITING_USER and guard < 10:
        guard += 1
        if sess.pending_kind == "question":
            v = sess.public_question()
            await sess.answer(v["query_id"], teacher.answer(v), v["candidate_set_hash"])
        else:
            from open_apprentice.concepts.hypotheses import neutral  # noqa

            await sess.submit_correction(teacher.corrected_example(sess.pending_scene))
    return sess


def mk(script, pool, **kw):
    kw.setdefault("seek_disagreement", False)
    kw.setdefault(
        "correction_turn", False
    )  # these tests count scripted replies; the turn has its own tests
    return TeachingSession(
        MockProvider({"hypotheses": script}), budget(), DOM, [2], pool=pool, **kw
    )


async def test_ambiguous_demo_is_resolved_by_one_question_and_concept_is_sealed(pool):
    latent = CLAMPED_MARGIN()
    s = mk(
        [
            {
                "candidates": [
                    cand("fixed 12px inset", CONST_MARGIN),
                    cand("8% of width", PROP_MARGIN()),
                    cand("8% of width, clamped to 8..24", CLAMPED_MARGIN()),
                ]
            }
        ],
        pool,
        teacher_source="benchmark_teacher",
    )
    await s.start(demo_for(latent))  # w=150: all three coincide => 3 survivors
    assert (
        len(s.candidates) == 3 and s.state == State.AWAITING_USER and s.pending_kind == "question"
    )
    t = BenchmarkTeacher(latent)
    await drive(s, t)
    assert (
        s.state == State.INTENT_READY
        and s.intent_state == IntentState.RESOLVED_WITHIN_CANDIDATE_SET
    )
    assert s.queries_asked <= MAX_QUERIES and len(s.candidates) >= 1
    c = s.finalize()
    # the surviving rule behaves like the latent rule on fresh in-domain inputs (held-out style check)
    for w in (40, 99, 100, 101, 230, 299, 300, 301, 480):
        sc = scene(w)
        assert (
            evaluate_rule(c.rule, sc["objects"], CANVAS)["badge"]
            == evaluate_rule(latent, sc["objects"], CANVAS)["badge"]
        )
    assert s.ledger.verify_chain() and [e.kind for e in s.ledger.entries][:2] == [
        "demonstration",
        "query",
    ]
    assert all(e.source in ("benchmark_teacher", "system") for e in s.ledger.entries)
    assert t.interactions == ["answer"] * len(t.interactions) and 1 <= len(t.interactions) <= 2


async def test_learner_never_receives_the_latent_rule_or_family_labels(pool):
    latent = CLAMPED_MARGIN()
    s = mk(
        [
            {
                "candidates": [
                    cand("a", CONST_MARGIN),
                    cand("b", PROP_MARGIN()),
                    cand("c", CLAMPED_MARGIN()),
                ]
            }
        ],
        pool,
    )
    await s.start(demo_for(latent))
    await drive(s, BenchmarkTeacher(latent))
    sent = json.dumps([[m.content for m in msgs] for _, msgs in s.provider.calls]).lower()
    for leak in (
        "clamp",
        "margin",
        "family",
        "badge_attach",
        "gap_row",
        "equal_edge",
        "2/25",
        "latent",
        "teacher",
    ):
        assert leak not in sent, leak


async def test_no_question_when_all_candidates_are_equivalent(pool):
    s = mk([{"candidates": [cand("a", gap_like(24)), cand("b", gap_like(24, extra=True))]}], pool)
    await s.start(demo_for(gap_like(24)))
    assert s.state == State.INTENT_READY and s.queries_asked == 0
    assert (
        s.intent_state == IntentState.RESOLVED_WITHIN_CANDIDATE_SET
    )  # solver: no_witness_in_model


def gap_like(m, extra=False):
    r = badge_rule(m)
    return r + [{"op": "let", "name": "unused", "value": 1}] if extra else r


async def test_neither_then_counted_correction_recovers_a_rule_outside_the_initial_set(pool):
    # latent: margin = 12 + (w-150)/10 -- NOT among the first-round candidates (omission stress test, fixture)
    latent = badge_rule(op("add", 12, op("div", op("sub", get(R("objects.0"), "w"), 150), 10)))
    second_round = {"candidates": [cand("inset grows by 1px per 10px of width", latent)]}
    s = mk(
        [
            {
                "candidates": [
                    cand("a", CONST_MARGIN),
                    cand("b", PROP_MARGIN()),
                    cand("c", CLAMPED_MARGIN()),
                ]
            },
            second_round,
        ],
        pool,
        teacher_source="benchmark_teacher",
    )
    await s.start(demo_for(latent))
    t = BenchmarkTeacher(latent)
    assert s.pending_kind == "question"
    await drive(s, t)
    assert "corrected_example" in t.interactions and t.interactions[0] == "answer"
    assert s.rounds == 2 and s.user_corrected
    assert s.state == State.INTENT_READY and s.intent_state == IntentState.USER_CORRECTED
    for w in (40, 150, 260, 480):
        sc = scene(w)
        assert (
            evaluate_rule(s.finalize().rule, sc["objects"], CANVAS)["badge"]
            == evaluate_rule(latent, sc["objects"], CANVAS)["badge"]
        )
    kinds = [e.kind for e in s.ledger.entries]
    assert kinds.index("answer") < kinds.index("corrected_example")
    sent = json.dumps(
        [[m.content for m in msgs if m.role != "system"] for _, msgs in s.provider.calls]
    ).lower()  # user turns only
    assert (
        "/10" not in sent and '"sub"' not in sent
    )  # the correction reveals geometry, not the formula


async def test_candidate_that_fits_only_the_new_correction_is_rejected(pool):
    latent = badge_rule(op("add", 12, op("div", op("sub", get(R("objects.0"), "w"), 150), 10)))
    fits_correction_only = badge_rule(
        op("div", get(R("objects.0"), "w"), 10)
    )  # 15 at w=150: breaks the demonstration
    s = mk(
        [
            {
                "candidates": [
                    cand("a", CONST_MARGIN),
                    cand("b", PROP_MARGIN()),
                    cand("c", CLAMPED_MARGIN()),
                ]
            },
            {"candidates": [cand("w/10", fits_correction_only)]},
        ],
        pool,
    )
    await s.start(demo_for(latent))
    await drive(s, BenchmarkTeacher(latent))
    assert s.state == State.UNRESOLVED and "candidate_generation_failure" in s.unresolved_reason
    assert any("contradicts teaching evidence" in r["reason"] for r in s.reports[-1].rejected)
    with pytest.raises(ValueError):
        s.finalize()


async def test_all_candidates_failing_demo_is_unresolved_not_forced(pool):
    wrong = badge_rule(99)
    s = mk([{"candidates": [cand("x", wrong)]}, {"candidates": [cand("y", wrong)]}], pool)
    await s.start(demo_for(CONST_MARGIN))
    assert s.state == State.UNRESOLVED and s.rounds == 2


async def test_stale_or_wrong_answers_do_not_advance_the_session(pool):
    latent = CLAMPED_MARGIN()
    s = mk(
        [
            {
                "candidates": [
                    cand("a", CONST_MARGIN),
                    cand("b", PROP_MARGIN()),
                    cand("c", CLAMPED_MARGIN()),
                ]
            }
        ],
        pool,
    )
    await s.start(demo_for(latent))
    v = s.public_question()
    with pytest.raises(ValueError, match="stale"):
        await s.answer("some-other-query", "A", v["candidate_set_hash"])
    with pytest.raises(ValueError, match="stale"):
        await s.answer(v["query_id"], "A", "0" * 64)
    assert s.state == State.AWAITING_USER and s.queries_asked == 0
    await s.answer(v["query_id"], "A", v["candidate_set_hash"])
    with pytest.raises(ValueError):
        await s.answer(
            v["query_id"], "A", v["candidate_set_hash"]
        )  # duplicate answer cannot resume the wrong set


async def test_teaching_costs_are_charged_to_the_shared_ledger(pool):
    latent = CLAMPED_MARGIN()
    s = mk(
        [
            {
                "candidates": [
                    cand("a", CONST_MARGIN),
                    cand("b", PROP_MARGIN()),
                    cand("c", CLAMPED_MARGIN()),
                ]
            }
        ],
        pool,
    )
    await s.start(demo_for(latent))
    snap = s.budget.snapshot()
    assert (
        snap["consumed"]["calls"] == 1
        and "teaching" in snap["by_category"]
        and snap["consumed"]["tokens"] > 0
    )
