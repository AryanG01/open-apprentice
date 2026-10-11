import json
import math
from fractions import Fraction as F

import pytest

from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.query_selection import (
    apply_answer,
    build_query,
    candidate_set_hash,
    disagreement_entropy,
    partition,
    public_view,
    score_scene,
    select_query,
)
from open_apprentice.concepts.schemas import (
    Concept,
    HeldOutStatus,
    IntentState,
    LedgerError,
    NativeStatus,
    SymbolicStatus,
    TeachingLedger,
    assert_no_aggregate_confidence,
)
from open_apprentice.concepts.witness import SolverBudget, SolverPool
from tests.fixtures_rules import CLAMPED_MARGIN, CONST_MARGIN, PROP_MARGIN

DOM = DomainManifest()
THR = DOM.query_visible_difference_px


# ---------------------------------------------------------------- ledger & sealed concept
def ledger():
    l = TeachingLedger()
    l.append("demonstration", {"after": "x"}, "user")
    return l


def test_ledger_is_hash_chained_and_tamper_evident():
    l = ledger()
    l.append("query", {"q": 1}, "system")
    l.append("answer", {"a": "A"}, "benchmark_teacher")
    assert l.verify_chain() and [e.seq for e in l.entries] == [0, 1, 2]
    object.__setattr__(l.entries[1], "payload", {"q": 999})  # tamper
    assert not l.verify_chain()


def test_ledger_rejects_unknown_kinds_and_records_teacher_provenance():
    l = ledger()
    with pytest.raises(LedgerError):
        l.append("silently_delete_answer", {}, "system")
    l.append("answer", {"a": "A"}, "benchmark_teacher")
    assert l.of_kind("answer")[0].source == "benchmark_teacher"  # never presented as a user study


def concept(rule, l, summary="s", version=1, domain=DOM.hash):
    return Concept.create(
        "c1", version, summary, rule, domain, l, IntentState.CONSISTENT_WITH_EXAMPLES
    )


def test_sealed_hash_covers_rule_domain_and_ledger_but_not_summary_or_version():
    l = ledger()
    base = concept(CONST_MARGIN, l).sealed_hash()
    assert concept(CONST_MARGIN, l, summary="reworded", version=2).sealed_hash() == base
    assert concept(PROP_MARGIN(), l).sealed_hash() != base  # rule change
    assert (
        concept(CONST_MARGIN, l, domain="narrower").sealed_hash() != base
    )  # domain narrowing to hide a failure
    l2 = ledger()
    l2.append("answer", {"a": "B"}, "user")
    assert concept(CONST_MARGIN, l2).sealed_hash() != base  # teaching evidence changed


def test_concept_is_immutable():
    c = concept(CONST_MARGIN, ledger())
    with pytest.raises(Exception):
        c.rule_json = "[]"


def test_no_aggregate_confidence_field_anywhere():
    assert_no_aggregate_confidence(
        {
            "intent": IntentState.UNRESOLVED.value,
            "symbolic": SymbolicStatus.TIMEOUT.value,
            "native": NativeStatus.UNTESTED.value,
            "held_out": HeldOutStatus.HIDDEN_DURING_EXECUTION.value,
        }
    )
    for bad in ({"verified": True}, {"a": {"Confidence": 0.9}}, [{"score": 1}]):
        with pytest.raises(AssertionError):
            assert_no_aggregate_confidence(bad)
    c = concept(CONST_MARGIN, ledger())
    assert_no_aggregate_confidence(json.loads(json.dumps(c.__dict__, default=str)))


def test_evidence_axes_are_distinct_types():
    assert len({IntentState, SymbolicStatus, NativeStatus, HeldOutStatus}) == 4
    assert not set(m.value for m in SymbolicStatus) & set(m.value for m in NativeStatus)


# ---------------------------------------------------------------- entropy / partition
def test_entropy_values():
    assert disagreement_entropy([[0, 1, 2]]) == 0
    assert disagreement_entropy([[0], [1], [2]]) == pytest.approx(math.log2(3))
    assert disagreement_entropy([[0, 1], [2]]) == pytest.approx(0.9183, abs=1e-3)


def test_partition_uses_the_frozen_visible_threshold():
    a = {"k": {"x": F(0), "y": F(0), "w": F(1), "h": F(1)}}
    near = {
        "k": {"x": F(1), "y": F(0), "w": F(1), "h": F(1)}
    }  # exactly 1px: NOT visibly different (needs > 1)
    far = {"k": {"x": F(2), "y": F(0), "w": F(1), "h": F(1)}}
    assert partition([a, near, far], THR) == [[0, 1], [2]]
    assert partition([a, None, far], THR) == [
        [0],
        [2],
    ]  # a failing candidate is excluded from the question


# ---------------------------------------------------------------- query selection
RULES = [CONST_MARGIN, PROP_MARGIN(), CLAMPED_MARGIN()]


def scene(w):
    return {
        "objects": [
            {"id": "obj0", "x": F(100), "y": F(100), "w": F(w), "h": F(80)},
            {"id": "obj1", "x": F(0), "y": F(0), "w": F(20), "h": F(20)},
        ],
        "canvas": {"w": F(800), "h": F(600)},
    }


def test_ambiguous_demo_scene_gives_no_question():
    sc = score_scene(RULES, scene(150), "sampled", THR)
    assert len(sc.groups) == 1 and sc.entropy == 0  # all three coincide at w=150 (12px)


def test_revealing_scene_separates_all_three_candidates():
    sc = score_scene(RULES, scene(60), "sampled", THR)
    assert len(sc.groups) == 3 and sc.entropy == pytest.approx(math.log2(3))
    assert sc.score == pytest.approx(sc.entropy / 2)  # cost = 2 objects


def test_select_query_returns_a_valid_discriminating_question():
    with SolverPool() as pool:
        sc = select_query(RULES, DOM, [2], SolverBudget(), pool, seed=1)
    assert (
        sc is not None
        and len(sc.groups) >= 2
        and DOM.contains(sc.scene["objects"], sc.scene["canvas"])
    )
    q = build_query(RULES, sc)
    assert 2 <= len(q.options) <= 4
    outs = list(q.options.values())
    assert all(
        partition([a, b], THR) == [[0], [1]] for i, a in enumerate(outs) for b in outs[i + 1 :]
    )  # options pairwise visibly distinct


def test_public_view_hides_candidates_and_rules():
    sc = score_scene(RULES, scene(60), "sampled", THR)
    q = build_query(RULES, sc)
    v = json.dumps(public_view(q), default=str)
    assert "option_members" not in v and "rule" not in v and "margin" not in v and "neither" in v


def test_answers_filter_neither_empties_and_stale_answers_are_rejected():
    sc = score_scene(RULES, scene(60), "sampled", THR)
    q = build_query(RULES, sc)
    h = candidate_set_hash(RULES)
    kept = apply_answer(RULES, q, "A", h)
    assert kept and set(kept) < {0, 1, 2}
    assert apply_answer(RULES, q, "neither", h) == []  # never forces a pick
    with pytest.raises(ValueError, match="stale"):
        apply_answer(
            RULES[:2], q, "A", candidate_set_hash(RULES[:2])
        )  # candidate set changed since asked
    with pytest.raises(ValueError):
        apply_answer(RULES, q, "Z", h)
