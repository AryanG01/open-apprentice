"""All methods through the SAME runner on a DEVELOPMENT episode with MOCK model replies (fixture origin).
Checks fairness/accounting/leakage plumbing. It says NOTHING about model quality."""

import asyncio
import json

import pytest

from open_apprentice.agent.policies import BADGE, SPACING, FullV12Policy, ReferencePolicy
from open_apprentice.agent.binding_templates import CALIBRATING, DIRECT
from open_apprentice.agent.synth import (
    FreshFullContextPolicy,
    StructuredProcedurePolicy,
    TextMemoryPolicy,
)
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.episodes import make_manifest
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.evaluation.metrics import method_summary
from open_apprentice.providers.mock import MockProvider

TOKEN = "e2e-token"
DOM = DomainManifest()
E = lambda p: {"ref": p}
B = lambda o, *a: {"op": o, "args": list(a)}


def synth_reply(msgs):
    """Intent-agnostic fixture: arranges with a fixed pitch / clones badges at the prototype. Passes the PUBLIC check, not intent."""
    kind = json.loads(msgs[1].content)["task"]["kind"]
    spacing = [
        {"op": "let", "name": "cursor", "value": 80},
        {
            "op": "for_each",
            "var": "id",
            "over": E("inputs.selected_ids"),
            "body": [
                {
                    "op": "call",
                    "tool": "measure_node",
                    "args": {"node_id": E("locals.id")},
                    "bind": "m",
                },
                {
                    "op": "call",
                    "tool": "move_node",
                    "args": {"node_id": E("locals.id"), "x": E("locals.cursor"), "y": 100},
                },
                {
                    "op": "let",
                    "name": "cursor",
                    "value": B(
                        "add", E("locals.cursor"), B("add", B("get", E("locals.m"), "width"), 20)
                    ),
                },
            ],
        },
    ]
    badge = [
        {
            "op": "for_each",
            "var": "id",
            "over": E("inputs.selected_ids"),
            "body": [
                {
                    "op": "call",
                    "tool": "clone_node",
                    "args": {
                        "node_id": E("inputs.prototype_id"),
                        "new_id": B("name", "badge_", E("locals.id")),
                    },
                }
            ],
        }
    ]
    prog = spacing if kind == SPACING else badge if kind == BADGE else spacing + badge
    return {"diagnosis": "fixture", "program": prog}


def make_provider(ep):
    cs = lambda rule, extra=None: {
        "candidates": [{"summary": "rule", "rule": rule}]
        + ([{"summary": "other", "rule": extra}] if extra else [])
    }
    fresh = [cs(ep.spacing), cs(ep.badge)]

    def hypotheses(msgs):
        # an "alternatives" round (the sole fitting rule is shown back) gets no new rule; every other request gets the next concept's rule
        if "already_fitting_rules" in msgs[1].content:
            return {"candidates": []}
        return fresh.pop(0)

    return MockProvider(
        {},
        functions={
            "hypotheses": hypotheses,
            "binding": lambda m: {
                "candidates": [
                    {"diagnosis": "d", "program": DIRECT},
                    {"diagnosis": "c", "program": CALIBRATING},
                ]
            },
            "binding_repair": lambda m: {
                "candidates": [{"diagnosis": "c", "program": CALIBRATING}]
            },
            "synth": synth_reply,
        },
    )


POLICIES = [
    ReferencePolicy,
    FullV12Policy,
    FreshFullContextPolicy,
    TextMemoryPolicy,
    StructuredProcedurePolicy,
]


@pytest.fixture(scope="module")
def runs(engine_url):
    from open_apprentice.evaluation.runner import run_episode

    ep = make_manifest("development", 0, 12).episodes[2]  # a DRIFT episode
    out, views, providers = {}, {}, {}

    async def go():
        with SolverPool() as pool:
            for cls in POLICIES:
                pol = cls()
                seen = []
                orig = pol.solve

                async def spy(ctx, view, _o=orig, _s=seen):
                    _s.append(json.dumps(view, sort_keys=True))
                    return await _o(ctx, view)

                pol.solve = spy
                prov = make_provider(ep)
                providers[pol.name] = prov
                out[pol.name] = (
                    pol,
                    await run_episode(
                        ep,
                        pol,
                        EvaluatorHarness(engine_url, TOKEN),
                        DOM,
                        pool,
                        provider=prov,
                        origin="mock" if pol.name != "enumerative_reference" else "reference",
                    ),
                )
                views[pol.name] = seen

    asyncio.run(go())
    return ep, out, views, providers


def test_every_method_receives_byte_identical_task_views(runs):
    _, _, views, _ = runs
    ref = views["enumerative_reference"]
    assert len(ref) == 8
    for name, v in views.items():
        assert v == ref, name


def test_no_prompt_contains_evaluator_only_information(runs):
    ep, _, _, providers = runs
    secrets = [
        ep.episode_id.lower(),
        "move_origin",
        "move_anchor",
        "drift",
        "latent",
        "recovery",
        "same_backend",
        "template",
        ep.templates["badge"],
        ep.templates["spacing"],
        "benchmark_teacher",
    ]
    for name, prov in providers.items():
        # user-turn content only: static public system prompts legitimately name grammar operators such as min/max
        sent = json.dumps(
            [[m.content for m in msgs if m.role != "system"] for _, msgs in prov.calls]
        ).lower()
        for s in secrets:
            i = sent.find(s.lower())
            assert i < 0, (name, s, sent[max(0, i - 140) : i + 80])


def test_rows_and_costs_have_the_same_shape_for_every_method(runs):
    _, out, _, _ = runs
    for name, (pol, rows) in out.items():
        assert [r.stage for r in rows].count("learning") == 1 and len(
            [r for r in rows if r.stage != "learning"]
        ) == 8
        assert all(r.method == name for r in rows)
    ref_learn = [r for r in out["enumerative_reference"][1] if r.stage == "learning"][0]
    assert ref_learn.tokens == 0 and ref_learn.calls == 0 and ref_learn.usd == 0.0
    for name in ("full_v1_2", "fresh_full_context", "text_memory", "structured_procedure"):
        learn = [r for r in out[name][1] if r.stage == "learning"][0]
        assert (
            learn.calls >= 2 and learn.tokens > 0 and learn.usd is None
        )  # mock cost is UNKNOWN, never zero
        assert learn.teacher_interactions >= 0


def test_intent_agnostic_baselines_pass_the_public_check_but_the_private_evaluator_rejects_them(
    runs,
):
    """Operational success != intent correctness: the metric must expose false success."""
    _, out, _, _ = runs
    for name in ("fresh_full_context", "text_memory", "structured_procedure"):
        s = method_summary(out[name][1], name)
        assert (
            s["false_success"]["claimed_successes"] > 0
            and s["false_success"]["false_successes"] > 0
        ), name


def test_structured_procedure_reuses_verified_programs_with_fewer_model_calls_than_fresh(runs):
    _, out, _, _ = runs
    calls = lambda n: sum(r.calls for r in out[n][1] if r.stage != "learning")
    assert calls("structured_procedure") < calls("fresh_full_context")
    pol = out["structured_procedure"][0]
    assert any(g["stored"] for g in pol.gate_log) or pol.programs


def test_full_policy_with_correct_candidates_matches_the_reference_machinery(runs):
    _, out, _, _ = runs
    full = method_summary(out["full_v1_2"][1], "full_v1_2")
    assert full["success"]["scheduled"] == 8 and full["false_success"]["false_successes"] == 0


def test_every_policy_only_ever_sees_the_ports(runs):
    import inspect
    from open_apprentice.agent import policies, synth

    src = inspect.getsource(policies) + inspect.getsource(synth)
    for forbidden in (
        "EnvService",
        "EvaluatorHarness",
        "evaluation.verifier",
        "evaluation.episodes",
        "DRIFT",
        "native_state",
        "nativeState",
    ):
        assert forbidden not in src, forbidden
