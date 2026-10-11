"""Fixed two-concept composition (spacing then badge) on a REAL Konva scene, judged by the independent verifier.
Bindings are registered fixtures (origin=fixture); this tests orchestration + honesty properties."""

from fractions import Fraction as F

import pytest

from open_apprentice.concepts.bindings import Binding, BindingRegistry, NativeBudget, backend_scene
from open_apprentice.concepts.composition import (
    CompositionPlan,
    PlanError,
    PlanNode,
    run_composition,
    validate_plan,
)
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.concepts.schemas import Concept, IntentState, TeachingLedger
from open_apprentice.evaluation.harness import EvaluatorHarness
from tests.fixtures_rules import CLAMPED_MARGIN, gap_rule
from tests.integration.test_binding_transfer import NAIVE

TOKEN = "e2e-token"
DOM = DomainManifest()
CANVAS = {"w": F(900), "h": F(600)}
CARDS = ["c0", "c1", "c2"]
LATENT_SPACING, LATENT_BADGE = gap_rule(gap=24, left=80, top=120), CLAMPED_MARGIN()


def concept(cid, rule):
    l = TeachingLedger()
    l.append("demonstration", {"c": cid}, "benchmark_teacher")
    return Concept.create(cid, 1, cid, rule, DOM.hash, l, IntentState.RESOLVED_WITHIN_CANDIDATE_SET)


SPACING, BADGE = concept("spacing", LATENT_SPACING), concept("badge", LATENT_BADGE)
CONCEPTS = {"spacing": SPACING, "badge": BADGE}


def scene():
    objs = [
        {"id": c, "x": F(10 + 150 * i), "y": F(400), "w": F(w), "h": F(70)}
        for i, (c, w) in enumerate(zip(CARDS, (100, 60, 140)))
    ]
    objs += [
        {"id": "proto", "x": F(800), "y": F(20), "w": F(20), "h": F(20)},
        {"id": "bystander", "x": F(700), "y": F(500), "w": F(50), "h": F(40)},
    ]
    return {"objects": objs, "canvas": CANVAS}


def registry(spacing_prog=NAIVE, badge_prog=NAIVE):
    reg = BindingRegistry()
    for c, prog in ((SPACING, spacing_prog), (BADGE, badge_prog)):
        reg.promote(
            Binding.create(
                c,
                "konva",
                1,
                None,
                prog,
                "h",
                {"passed": True, "regression_passed": True},
                "fixture",
            ),
            c,
            "fixture",
        )
    return reg


def expected():
    cards = [o for o in scene()["objects"] if o["id"] in CARDS]
    arranged = evaluate_rule(LATENT_SPACING, cards, CANVAS)
    exp = {k: {f: float(v[f]) for f in "xywh"} for k, v in arranged.items()}
    proto = scene()["objects"][3]
    for c in CARDS:
        out = evaluate_rule(LATENT_BADGE, [{"id": c, **arranged[c]}, proto], CANVAS)["badge"]
        exp[f"badge_{c}"] = {f: float(out[f]) for f in "xywh"}
    return exp


PLAN = CompositionPlan(
    nodes=[
        PlanNode(id="arrange", concept="spacing"),
        PlanNode(id="badges", concept="badge", mode="each", depends_on=["arrange"]),
    ]
)
REVERSED = CompositionPlan(
    nodes=[
        PlanNode(id="badges", concept="badge", mode="each"),
        PlanNode(id="arrange", concept="spacing", depends_on=["badges"]),
    ]
)


def execute(url, plan, reg, budget=None):
    h = EvaluatorHarness(url, TOKEN)
    sess, initial = h.open_session(backend_scene(scene()), "comp", None, backend="konva")
    try:
        run = run_composition(
            plan,
            CONCEPTS,
            reg,
            "konva",
            sess,
            CARDS,
            "proto",
            {"w": 900.0, "h": 600.0},
            budget or NativeBudget(500),
        )
        rep = h.judge_expected(sess, initial, expected(), CARDS)
        return run, rep
    finally:
        sess.close()


def test_spacing_then_badges_is_correct_per_the_independent_verifier(engine_url):
    run, rep = execute(engine_url, PLAN, registry())
    assert run.status == "completed" and run.order == ["arrange", "badges"]
    assert all(n["local_native_check_passed"] for n in run.nodes)
    assert rep.passed, [(c.name, c.detail) for c in rep.checks if not c.passed]
    assert set(run.nodes[1]["affected"]) == {
        f"badge_{c}" for c in CARDS
    }  # badge node touched ONLY its badges


def test_wrong_order_passes_every_node_local_check_but_fails_the_global_requirement(engine_url):
    run, rep = execute(engine_url, REVERSED, registry())
    assert run.status == "completed" and all(
        n["local_native_check_passed"] for n in run.nodes
    )  # parts look fine...
    assert not rep.passed and "geometry_matches_expected" in rep.failed()  # ...interference is real


def test_node_that_touches_objects_outside_its_scope_is_rejected_not_accepted(engine_url):
    sneaky = NAIVE + [
        {"op": "call", "tool": "move_node", "args": {"node_id": "bystander", "x": 1, "y": 1}}
    ]
    run, _ = execute(engine_url, PLAN, registry(spacing_prog=sneaky))
    assert run.status == "rejected_scope" and "bystander" in run.detail


def test_budget_is_shared_across_nodes_and_never_reset(engine_url):
    b = NativeBudget(12)
    run, _ = execute(engine_url, PLAN, registry(), b)
    assert run.status == "budget_exhausted" and b.used <= 12


def test_missing_binding_is_an_explicit_error_not_a_silent_drop(engine_url):
    reg = BindingRegistry()
    reg.promote(
        Binding.create(SPACING, "konva", 1, None, NAIVE, "h", {"passed": True}, "fixture"),
        SPACING,
        "fixture",
    )
    run, _ = execute(engine_url, PLAN, reg)
    assert run.status == "error" and "badge" in run.detail and "not dropped silently" in run.detail


# ---- plan validation (pure) ----------------------------------------------------------------------
def test_plan_validation_rejects_cycles_recursion_unresolved_refs_and_large_plans():
    n = lambda i, c="spacing", d=(): PlanNode(id=i, concept=c, depends_on=list(d))
    assert validate_plan(PLAN, CONCEPTS) == ["arrange", "badges"]
    for bad in (
        CompositionPlan(nodes=[n("a", d=["b"]), n("b", d=["a"])]),  # cycle
        CompositionPlan(nodes=[n("a", d=["a"])]),  # recursion
        CompositionPlan(nodes=[n("a", d=["zzz"])]),  # unresolved dep
        CompositionPlan(nodes=[n("a", c="ghost")]),  # unresolved concept
        CompositionPlan(nodes=[n("a"), n("a")]),  # duplicate ids
        CompositionPlan(nodes=[n(f"n{i}") for i in range(5)]),  # > 4 nodes
        CompositionPlan(nodes=[]),
    ):
        with pytest.raises(PlanError):
            validate_plan(bad, CONCEPTS)
