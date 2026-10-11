"""Grounding ablation on REAL engines (dev drift episode) and target-omission recovery. Disposable-scene batteries:
the numbers printed are harness checks on DEVELOPMENT data, not results."""

import asyncio
from fractions import Fraction as F


from open_apprentice.agent.policies import ReferencePolicy, ReferenceUngrounded
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.enumerative import EnumerativeSource
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.batteries import FirstRoundFixtureSource, run_omission_case
from open_apprentice.evaluation.episodes import make_manifest
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.evaluation.metrics import method_summary
from open_apprentice.evaluation.runner import run_episode
from tests.fixtures_rules import CONST_MARGIN, PROP_MARGIN, R, badge_rule, get, op

TOKEN = "e2e-token"
DOM = DomainManifest()
CANVAS = {"w": F(800), "h": F(600)}


def test_grounding_ablation_exposes_silent_failures_that_native_confirmation_catches(
    engine_url, capsys
):
    m = make_manifest("development", 0, 12)
    drift_ep = m.episodes[2]
    assert drift_ep.drift is not None  # an episode that really contains the tool change
    rows = []

    async def go():
        with SolverPool() as pool:
            for cls in (ReferencePolicy, ReferenceUngrounded):
                rows.extend(
                    await run_episode(
                        drift_ep,
                        cls(),
                        EvaluatorHarness(engine_url, TOKEN),
                        DOM,
                        pool,
                        origin="reference",
                    )
                )

    asyncio.run(go())
    rec = {"recovery"}
    g, u = (
        method_summary(rows, n, rec)
        for n in ("enumerative_reference", "enumerative_reference_ungrounded")
    )
    with capsys.disabled():
        print(
            "\nGROUNDING ABLATION (non-LLM reference, 1 DEVELOPMENT drift episode, recovery tasks; harness check):"
        )
        for n, s in (("grounded", g), ("ungrounded", u)):
            print(
                f"  {n:10s} success={s['success']} false_success={s['false_success']} failures={s['failures']}"
            )
    # What must hold by construction of the ablation:
    assert (
        u["false_success"]["false_successes"] >= 1
    )  # without native confirmation wrong outputs are claimed as success
    assert (
        g["false_success"]["false_successes"] == 0
    )  # with it, a mismatch is repaired or the task abstains
    assert (g["success"]["rate"] or 0) > (u["success"]["rate"] or 0)


async def _omission(template, latent, fixture, pool, method):
    obj = [
        {"id": "obj0", "x": F(100), "y": F(100), "w": F(150), "h": F(80)},
        {"id": "obj1", "x": F(0), "y": F(0), "w": F(20), "h": F(20)},
    ]
    sc = {"objects": obj, "canvas": CANVAS}
    demo = {"scene": sc, "after": evaluate_rule(latent, obj, CANVAS)}
    src = FirstRoundFixtureSource(EnumerativeSource(DOM, [2]), fixture)
    return await run_omission_case(method, template, latent, demo, DOM, [2], pool, source=src)


async def test_omitted_rule_is_recovered_only_through_neither_plus_a_counted_corrected_example():
    # latent = 0.1*w - 3 (affine, outside the fixture set {12px, 8% of w}); both fixtures also fit the demo at w=150
    latent = badge_rule(op("add", op("mul", get(R("objects.0"), "w"), {"rat": "1/10"}), -3))
    with SolverPool() as pool:
        r = await _omission(
            "affine",
            latent,
            [("fixed 12px", CONST_MARGIN), ("8% of width", PROP_MARGIN())],
            pool,
            "enumerative_reference",
        )
    assert (
        r.rounds == 2 and r.teacher_corrections == 1 and r.teacher_answers >= 1
    )  # Neither -> counted correction
    assert r.state == "INTENT_READY" and r.intent_state == "user_corrected" and r.recovered
    assert "FIXTURE" in r.note


async def test_when_the_fixture_contains_the_true_rule_no_correction_is_needed():
    with SolverPool() as pool:
        r = await _omission(
            "prop",
            PROP_MARGIN(),
            [("fixed 12px", CONST_MARGIN), ("8% of width", PROP_MARGIN())],
            pool,
            "enumerative_reference",
        )
    assert r.teacher_corrections == 0 and r.recovered
