"""M3 on REAL Konva and Fabric: transfer, reproduced native mismatch under private drift, binding-only
repair with the sealed concept unchanged. MOCK provider replies are scripted fixtures (origin=fixture)."""

from fractions import Fraction as F

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.bindings import (
    BindingRegistry,
    NativeBudget,
    PromotionError,
    expected_state,
    native_run,
    targets_from_rule,
    backend_scene,
)
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.schemas import Concept, IntentState, NativeStatus, TeachingLedger
from open_apprentice.concepts.transfer import repair_binding, transfer_concept
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.providers.mock import MockProvider
from tests.fixtures_rules import CLAMPED_MARGIN, PROP_MARGIN

TOKEN = "e2e-token"
DOM = DomainManifest()


def scene(w, h=80, x=100, y=100):
    return {
        "objects": [
            {"id": "card", "x": F(x), "y": F(y), "w": F(w), "h": F(h)},
            {"id": "proto", "x": F(0), "y": F(0), "w": F(20), "h": F(20)},
        ],
        "canvas": {"w": F(800), "h": F(600)},
    }


def concept_for(rule):
    l = TeachingLedger()
    l.append("demonstration", {"d": 1}, "benchmark_teacher")
    return (
        Concept.create(
            "badge", 1, "badge inset", rule, DOM.hash, l, IntentState.RESOLVED_WITHIN_CANDIDATE_SET
        ),
        l,
    )


# ---- fixture binding programs ------------------------------------------------------------------
def E(p):
    return {"ref": p}


def B(o, *a):
    return {"op": o, "args": list(a)}


NAIVE = [
    {
        "op": "for_each",
        "var": "t",
        "over": E("inputs.targets"),
        "body": [
            {
                "op": "if",
                "cond": B("eq", E("locals.t.kind"), "clone_place"),
                "then": [
                    {
                        "op": "call",
                        "tool": "clone_node",
                        "args": {"node_id": E("locals.t.proto"), "new_id": E("locals.t.symbol")},
                    },
                    {
                        "op": "call",
                        "tool": "move_node",
                        "args": {
                            "node_id": E("locals.t.symbol"),
                            "x": E("locals.t.x"),
                            "y": E("locals.t.y"),
                        },
                    },
                ],
                "else": [
                    {
                        "op": "call",
                        "tool": "move_node",
                        "args": {
                            "node_id": E("locals.t.id"),
                            "x": E("locals.t.x"),
                            "y": E("locals.t.y"),
                        },
                    }
                ],
            }
        ],
    }
]

PROBING = [
    {
        "op": "for_each",
        "var": "t",
        "over": E("inputs.targets"),
        "body": [
            {
                "op": "if",
                "cond": B("eq", E("locals.t.kind"), "clone_place"),
                "then": [
                    {
                        "op": "call",
                        "tool": "clone_node",
                        "args": {"node_id": E("locals.t.proto"), "new_id": E("locals.t.symbol")},
                    },
                    {"op": "let", "name": "nid", "value": E("locals.t.symbol")},
                ],
                "else": [{"op": "let", "name": "nid", "value": E("locals.t.id")}],
            },
            {
                "op": "call",
                "tool": "move_node",
                "args": {"node_id": E("locals.nid"), "x": E("locals.t.x"), "y": E("locals.t.y")},
            },
            {
                "op": "call",
                "tool": "observe_geometry",
                "args": {"node_ids": B("list", E("locals.nid"))},
                "bind": "obs",
            },
            {"op": "let", "name": "b", "value": B("index", B("get", E("locals.obs"), "bounds"), 0)},
            {
                "op": "let",
                "name": "dx",
                "value": B("sub", E("locals.t.x"), B("get", E("locals.b"), "left")),
            },
            {
                "op": "let",
                "name": "dy",
                "value": B("sub", E("locals.t.y"), B("get", E("locals.b"), "top")),
            },
            {
                "op": "if",
                "cond": B(
                    "or",
                    B("gt", E("locals.dx"), 0.25),
                    B("lt", E("locals.dx"), -0.25),
                    B("gt", E("locals.dy"), 0.25),
                    B("lt", E("locals.dy"), -0.25),
                ),
                "then": [
                    {
                        "op": "call",
                        "tool": "move_node",
                        "args": {
                            "node_id": E("locals.nid"),
                            "x": B("add", E("locals.t.x"), E("locals.dx")),
                            "y": B("add", E("locals.t.y"), E("locals.dy")),
                        },
                    }
                ],
            },
        ],
    }
]

HARDCODED_OFFSET = [
    {
        "op": "for_each",
        "var": "t",
        "over": E("inputs.targets"),
        "body": [
            {
                "op": "call",
                "tool": "clone_node",
                "args": {"node_id": E("locals.t.proto"), "new_id": E("locals.t.symbol")},
            },
            # "fixes" the witness by hard-coding a half-size offset (wrong for any other situation)
            {
                "op": "call",
                "tool": "move_node",
                "args": {
                    "node_id": E("locals.t.symbol"),
                    "x": B("add", E("locals.t.x"), 10),
                    "y": B("add", E("locals.t.y"), 10),
                },
            },
        ],
    }
]


def cands(*progs):
    return {
        "candidates": [{"diagnosis": f"fixture {i}", "program": p} for i, p in enumerate(progs)]
    }


_ENVS: list = []


@pytest.fixture(autouse=True)
def _close_sessions():
    yield
    while _ENVS:
        env = _ENVS.pop()
        for sess, _ in env.sessions:
            try:
                sess.close()
            except Exception:
                pass


class Env:
    """Evaluator-side: builds sessions on a backend with a private config; the learner sees only a factory."""

    def __init__(self, url, backend, private=None):
        self.h, self.backend, self.private, self.sessions = (
            EvaluatorHarness(url, TOKEN),
            backend,
            private,
            [],
        )
        _ENVS.append(self)

    def factory(self, sc):
        s, initial = self.h.open_session(
            backend_scene(sc), "m3", self.private, backend=self.backend
        )
        self.sessions.append((s, initial))
        return s

    def judge(self, s, initial, latent, sc):
        return self.h.judge_expected(s, initial, expected_state(latent, sc), ["card"])


def ledger():
    return Ledger(Limits(tokens=500_000, calls=64, actions=800))


@pytest.mark.parametrize("backend", ["konva", "fabric"])
async def test_transfer_validates_binding_on_listed_cases_for_both_real_backends(
    engine_url, backend
):
    concept, _ = concept_for(CLAMPED_MARGIN())
    env, reg, nb = Env(engine_url, backend), BindingRegistry(), NativeBudget()
    r = await transfer_concept(
        concept,
        backend,
        MockProvider({"binding": [cands(NAIVE)]}),
        ledger(),
        nb,
        env.factory,
        [scene(150), scene(60)],
        reg,
        "schema-hash",
    )
    assert r.status == "validated" and r.native_status == NativeStatus.CHECKED_ON_LISTED_CASES
    assert reg.current("badge", backend).version == 1 and nb.used <= 24
    assert r.binding.validation["scope"].startswith("listed cases only")


async def test_correct_native_execution_of_a_wrong_inferred_rule_fails_the_independent_intent_check(
    engine_url,
):
    latent, wrong = CLAMPED_MARGIN(), PROP_MARGIN()  # at w=400: latent margin 24, wrong margin 32
    concept, _ = concept_for(wrong)
    env, nb = Env(engine_url, "konva"), NativeBudget(60)
    sc = scene(400)
    s = env.factory(sc)
    initial = env.sessions[-1][1]
    res = native_run(NAIVE, targets_from_rule(concept.rule, sc), s, {"w": 800, "h": 600}, nb)
    assert res["passed"]  # binding perfectly realises the learner's rule...
    rep = env.judge(s, initial, latent, sc)
    assert (
        not rep.passed and "geometry_matches_expected" in rep.failed()
    )  # ...which is the wrong intent


async def test_drift_reproduces_mismatch_while_abstract_model_passes_then_binding_only_repair(
    engine_url,
):
    latent = CLAMPED_MARGIN()
    concept, ledger_ = concept_for(latent)
    sealed, ledger_len = concept.sealed_hash(), len(ledger_.entries)
    reg = BindingRegistry()
    orig = Env(engine_url, "fabric")  # documented behaviour
    drifted = Env(engine_url, "fabric", {"move_origin": "center"})  # private, undocumented

    # 1) transfer to Fabric before any drift
    r1 = await transfer_concept(
        concept,
        "fabric",
        MockProvider({"binding": [cands(NAIVE)]}),
        ledger(),
        NativeBudget(),
        orig.factory,
        [scene(150), scene(60)],
        reg,
        "fabric-hash",
    )
    assert r1.status == "validated"
    v1 = reg.current("badge", "fabric")

    # 2) the same candidate on the drifted tool: abstract check passes, native fails => reproduced mismatch
    r2 = await transfer_concept(
        concept,
        "fabric",
        MockProvider({"binding": [cands(NAIVE), cands(NAIVE)]}),
        ledger(),
        NativeBudget(),
        drifted.factory,
        [scene(300), scene(80)],
        BindingRegistry(),
        "fabric-hash",
    )
    assert r2.status == "failed" and r2.native_status == NativeStatus.REPRODUCED_MISMATCH
    assert r2.semantic_model_trusted is False and r2.mismatch["abstract_check_passed"] is True
    d = r2.mismatch["native_diffs"][0]
    assert abs(d["observed"][0] - d["expected"][0]) == pytest.approx(
        10.0, abs=0.01
    )  # proto is 20 wide => center offset 10

    # 3) repair: a hard-coded offset is rejected by retained-case replay; the probing patch is promoted
    witness_scene = scene(300)
    witness = {
        "scene": witness_scene,
        "targets": r2.mismatch["expected_targets"],
        "observed": [
            {"key": x["key"], "observed": x["observed"]} for x in r2.mismatch["native_diffs"]
        ],
    }
    nb = NativeBudget()
    r3 = await repair_binding(
        concept,
        "fabric",
        v1,
        witness,
        MockProvider({"binding_repair": [cands(HARDCODED_OFFSET, PROBING)]}),
        ledger(),
        nb,
        drifted.factory,
        orig.factory,
        [scene(150)],
        scene(80),
        reg,
        "fabric-hash",
    )
    assert r3.status == "validated", r3.attempts
    a0 = r3.attempts[0]
    assert a0["cases"][0] == {
        **a0["cases"][0],
        "stage": "witness_in_current_env",
        "passed": True,
    }  # it "fixes" the witness...
    assert a0["failed_stage"] == "retained_in_original_env"  # ...but breaks earlier behaviour
    assert reg.current("badge", "fabric").version == 2 and [
        b.version for b in reg.versions[("badge", "fabric")]
    ] == [1, 2]
    assert nb.used <= 24

    # intent untouched by a binding repair
    assert (
        concept.sealed_hash() == sealed
        and len(ledger_.entries) == ledger_len
        and ledger_.verify_chain()
    )
    assert r3.binding.concept_sealed_hash == sealed

    # the repaired binding is intent-correct on an unseen scene in BOTH environments (independent verifier)
    for env in (drifted, orig):
        sc = scene(220, y=150)
        s = env.factory(sc)
        initial = env.sessions[-1][1]
        native_run(
            r3.binding.prog,
            targets_from_rule(concept.rule, sc),
            s,
            {"w": 800, "h": 600},
            NativeBudget(60),
        )
        rep = env.judge(s, initial, latent, sc)
        assert rep.passed, [(c.name, c.detail) for c in rep.checks if not c.passed]

    # old version retained and still valid in the original environment; rollback is a pointer move
    reg.rollback("badge", "fabric", 1, "demo rollback")
    assert (
        reg.current("badge", "fabric").version == 1 and len(reg.versions[("badge", "fabric")]) == 2
    )


async def test_failed_repair_quarantines_and_keeps_history(engine_url):
    concept, _ = concept_for(CLAMPED_MARGIN())
    reg, orig = BindingRegistry(), Env(engine_url, "fabric")
    drifted = Env(engine_url, "fabric", {"move_origin": "center"})
    await transfer_concept(
        concept,
        "fabric",
        MockProvider({"binding": [cands(NAIVE)]}),
        ledger(),
        NativeBudget(),
        orig.factory,
        [scene(150), scene(60)],
        reg,
        "h",
    )
    v1 = reg.current("badge", "fabric")
    w = {
        "scene": scene(300),
        "targets": targets_from_rule(concept.rule, scene(300)),
        "observed": [],
    }
    r = await repair_binding(
        concept,
        "fabric",
        v1,
        w,
        MockProvider({"binding_repair": [cands(NAIVE, HARDCODED_OFFSET)]}),
        ledger(),
        NativeBudget(),
        drifted.factory,
        orig.factory,
        [scene(150)],
        scene(80),
        reg,
        "h",
    )
    assert r.status == "failed" and reg.current("badge", "fabric").version == 1
    assert any(e["event"] == "quarantined" for e in reg.events)


# ---- promotion rules (no engine needed) ------------------------------------------------------------
def _binding(concept, parent=None, **val):
    from open_apprentice.concepts.bindings import Binding

    return Binding.create(
        concept,
        "fabric",
        1,
        parent,
        NAIVE,
        "h",
        {"passed": True, "regression_passed": True, **val},
        "fixture",
    )


def test_promotion_rejects_changed_rule_narrowed_domain_changed_ledger_and_failed_validation():
    c, l = concept_for(CLAMPED_MARGIN())
    b = _binding(c)
    for changed in (
        concept_for(PROP_MARGIN())[0],  # rule edited
        Concept.create("badge", 1, "s", CLAMPED_MARGIN(), "narrower-domain", l, c.intent_state),
    ):  # domain narrowed
        with pytest.raises(PromotionError, match="different concept"):
            BindingRegistry().promote(b, changed, "x")
    l2 = TeachingLedger()
    l2.append("demonstration", {"d": 1}, "benchmark_teacher")
    l2.append("answer", {"a": "B"}, "user")
    with pytest.raises(PromotionError):
        BindingRegistry().promote(
            b, Concept.create("badge", 1, "s", CLAMPED_MARGIN(), DOM.hash, l2, c.intent_state), "x"
        )
    with pytest.raises(PromotionError, match="validation"):
        BindingRegistry().promote(_binding(c, passed=False), c, "x")
    with pytest.raises(PromotionError, match="validation"):
        BindingRegistry().promote(_binding(c, regression_passed=False), c, "x")


def test_promotion_race_retains_candidate_unpromoted_and_never_overwrites():
    c, _ = concept_for(CLAMPED_MARGIN())
    reg = BindingRegistry()
    reg.promote(_binding(c), c, "v1")
    stale = _binding(c, parent=None)  # built against the pre-v1 state
    with pytest.raises(PromotionError, match="retained unpromoted"):
        reg.promote(stale, c, "late")
    assert reg.active[("badge", "fabric")] == 1 and len(reg.versions[("badge", "fabric")]) == 2
    assert reg.events[-1]["event"] == "promotion_deferred"
