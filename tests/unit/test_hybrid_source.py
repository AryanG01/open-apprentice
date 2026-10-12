"""Hybrid candidate source with a SCRIPTED model: the union covers a rule the model omitted, dedupes behaviourally identical rules, tags origins,
and degrades to search-only when the model call fails. No network."""

from fractions import Fraction as F

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.hybrid import HybridSource
from open_apprentice.concepts.hypotheses import Constraint
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.concepts.teaching import State, TeachingSession
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.teacher import BenchmarkTeacher
from open_apprentice.providers.base import TruncatedOutput
from open_apprentice.providers.mock import MockProvider
from tests.fixtures_rules import CONST_MARGIN, PROP_MARGIN
from tests.unit.test_teaching_session import demo_for, drive

DOM = DomainManifest()


def ledger():
    return Ledger(Limits(tokens=500_000, calls=64))


def constraint(latent):
    d = demo_for(latent)
    return [Constraint("positive", d["scene"], d["after"], source="demonstration")]


async def test_union_contains_the_rule_the_model_omitted_and_tags_origins():
    model = MockProvider(
        {"hypotheses": [{"candidates": [{"summary": "fixed 12px", "rule": CONST_MARGIN}]}]}
    )
    src = HybridSource(model, ledger(), DOM, [2])
    rep = await src(constraint(PROP_MARGIN()), 1, [])
    tags = [c.summary.split("]")[0] + "]" for c in rep.accepted]
    assert "[model]" in tags and "[search]" in tags
    truth = evaluate_rule(
        PROP_MARGIN(),
        demo_for(PROP_MARGIN(), 400)["scene"]["objects"],
        {"w": F(800), "h": F(600)},
    )
    assert any(
        evaluate_rule(
            c.rule, demo_for(PROP_MARGIN(), 400)["scene"]["objects"], {"w": F(800), "h": F(600)}
        )
        == truth
        for c in rep.accepted
    ), "the omitted true rule must be reachable through the symbolic search"
    assert len({c.hash for c in rep.accepted}) == len(rep.accepted)


async def test_behaviourally_identical_candidates_are_counted_once_and_the_first_origin_wins():
    model = MockProvider(
        {"hypotheses": [{"candidates": [{"summary": "fixed 12px", "rule": CONST_MARGIN}]}]}
    )
    rep = await HybridSource(model, ledger(), DOM, [2])(constraint(PROP_MARGIN()), 1, [])
    twelve = [
        c
        for c in rep.accepted
        if "12" in c.summary and "inset" in c.summary or c.summary.startswith("[model]")
    ]
    assert sum(1 for c in rep.accepted if c.summary.startswith("[model]")) == 1
    assert not any(
        c.summary.startswith("[search]") and "inset 12" in c.summary for c in rep.accepted
    ), twelve


async def test_a_failing_model_degrades_to_search_only_and_records_why():
    class Broken(MockProvider):
        async def _call(self, messages, *, max_tokens, ctx):
            raise TruncatedOutput("completion limit")

    src = HybridSource(Broken({}), ledger(), DOM, [2])
    rep = await src(constraint(PROP_MARGIN()), 1, [])
    assert rep.accepted and all(c.summary.startswith("[search]") for c in rep.accepted)
    assert src.model_errors == ["MODEL_TRUNCATED"] and rep.usage["model_error"] == "MODEL_TRUNCATED"


@pytest.fixture(scope="module")
def pool():
    with SolverPool() as p:
        yield p


async def test_hybrid_session_reaches_the_intended_rule_even_when_the_model_is_useless(pool):
    latent = (
        PROP_MARGIN()
    )  # inside the search grammar's simple end; harder rules are a documented limit (decisions #45)

    class Useless(MockProvider):
        async def _call(self, messages, *, max_tokens, ctx):
            raise TruncatedOutput("nothing usable")

    sess = TeachingSession(None, ledger(), DOM, [2], pool=pool, teacher_source="benchmark_teacher")
    sess.candidate_source = HybridSource(Useless({}), ledger(), DOM, [2])
    await sess.start(demo_for(latent))
    await drive(sess, BenchmarkTeacher(latent))
    assert sess.state == State.INTENT_READY
    for w in (40, 150, 400, 480):
        sc = demo_for(latent, w)["scene"]
        assert evaluate_rule(sess.finalize().rule, sc["objects"], sc["canvas"]) == evaluate_rule(
            latent, sc["objects"], sc["canvas"]
        )


async def test_the_cap_never_drops_every_search_candidate_when_the_model_proposes_many():
    from tests.fixtures_rules import CLAMPED_MARGIN

    model = MockProvider(
        {
            "hypotheses": [
                {
                    "candidates": [
                        {"summary": "fixed 12px", "rule": CONST_MARGIN},
                        {"summary": "clamped inset", "rule": CLAMPED_MARGIN()},
                    ]
                }
            ]
        }
    )
    src = HybridSource(model, ledger(), DOM, [2])
    src.max_union = 2  # as many slots as the model filled on its own
    rep = await src(constraint(PROP_MARGIN()), 1, [])
    origins = [c.summary.split("]")[0] + "]" for c in rep.accepted]
    assert (
        "[search]" in origins
    ), origins  # the search exists to cover what the model omitted; the cap must not undo that
    assert "[model]" in origins, origins
