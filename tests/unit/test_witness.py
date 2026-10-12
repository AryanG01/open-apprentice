from fractions import Fraction as F

import pytest

from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.witness import (
    SolverBudget,
    SolverPool,
    find_disagreement,
    find_public_constraint_violation,
)
from tests.fixtures_rules import (
    CLAMPED_MARGIN,
    CONST_MARGIN,
    PROP_MARGIN,
    R,
    badge_rule,
    center_spacing_rule,
    gap_rule,
    get,
    op,
)

DOM = DomainManifest()


@pytest.fixture(scope="module")
def pool():
    with SolverPool() as p:
        yield p


def test_const_vs_proportional_margin_has_concrete_witness_not_at_w150(pool):
    res = find_disagreement([CONST_MARGIN, PROP_MARGIN()], [2], DOM, pool=pool)
    assert res.status == "witness_found" and res.witness.kind == "disagreement"
    w = res.witness
    assert DOM.contains(w.objects, w.canvas)
    a, b = w.predictions  # re-executed concretely, not solver output
    assert any(abs(a["badge"][k] - b["badge"][k]) > 1 for k in ("x", "y"))
    assert w.objects[0]["w"] != 150  # 12px coincidence point cannot be the witness
    assert res.domain_hash == DOM.hash and len(res.candidate_hashes) == 2


def test_witness_is_readable_when_rounding_preserves_it(pool):
    res = find_disagreement([CONST_MARGIN, CLAMPED_MARGIN()], [2], DOM, pool=pool)
    assert res.status == "witness_found"
    assert res.witness.simplified in ("rounded_to_integers", "rounded_to_halves", "exact")
    if res.witness.simplified == "rounded_to_integers":
        assert all(F(o[f]).denominator == 1 for o in res.witness.objects for f in "xywh")


def test_equivalent_rules_written_differently_are_unsat_with_exported_query(pool):
    m = lambda: op("mul", get(R("objects.0"), "w"), {"rat": "2/25"})
    via_if = badge_rule(op("min", 24, op("max", 8, m())))
    nested = [
        {"op": "let", "name": "raw", "value": m()},
        {
            "op": "if",
            "cond": op("lt", R("locals.raw"), 8),
            "then": [{"op": "let", "name": "mm", "value": 8}],
            "else": [
                {
                    "op": "if",
                    "cond": op("gt", R("locals.raw"), 24),
                    "then": [{"op": "let", "name": "mm", "value": 24}],
                    "else": [{"op": "let", "name": "mm", "value": R("locals.raw")}],
                }
            ],
        },
    ]
    nested_rule = nested + badge_rule(R("locals.mm"))
    res = find_disagreement([via_if, nested_rule], [2], DOM, pool=pool)
    assert res.status == "no_witness_in_model"
    c = res.cases[0]
    assert c.status == "unsat" and "(check-sat)" in c.smtlib and res.solver_version.startswith("4.")
    assert "domain" in res.encoded_property or "in-domain" in res.encoded_property


def test_edge_gap_and_center_spacing_agree_only_where_pitch_equals_width_plus_gap(pool):
    """pitch 124 = width 100 + gap 24: the rules coincide ONLY when every width is exactly 100."""
    res = find_disagreement(
        [gap_rule(gap=24), center_spacing_rule(pitch=124)], [2, 3, 4], DOM, pool=pool
    )
    assert res.status == "witness_found"
    assert not all(o["w"] == 100 for o in res.witness.objects)
    a, b = res.witness.predictions
    assert a != b
    # and the coincidence case is real: all widths 100 => identical outputs (concrete check)
    eq = [{"id": f"obj{i}", "x": 0, "y": 0, "w": 100, "h": 50} for i in range(3)]
    from open_apprentice.concepts.rules import evaluate_rule

    assert evaluate_rule(gap_rule(gap=24), eq, {"w": 800, "h": 600}) == evaluate_rule(
        center_spacing_rule(pitch=124), eq, {"w": 800, "h": 600}
    )


def test_variable_by_variable_is_unsupported_and_spends_no_solver_call(pool):
    bad = [
        {
            "op": "emit_target",
            "kind": "move_existing",
            "target": R("objects.0"),
            "x": op("mul", get(R("objects.0"), "w"), get(R("objects.1"), "w")),
            "y": 0,
        }
    ]
    b = SolverBudget()
    res = find_disagreement([bad, gap_rule()], [2], DOM, budget=b, pool=pool)
    assert res.status == "unsupported" and b.calls == 0


def test_partial_coverage_is_incomplete_not_no_witness(pool):
    same = [gap_rule(), gap_rule(), gap_rule()]
    res = find_disagreement(same, [2], DOM, budget=SolverBudget(max_calls=1), pool=pool)
    assert res.status == "incomplete"
    assert [c.status for c in res.cases] == ["unsat", "unchecked", "unchecked"]


def test_solver_timeout_status_is_distinct_and_never_a_pass(monkeypatch):
    class Slow(SolverPool):
        def solve(self, payload, wall_s):
            return None

    res = find_disagreement([gap_rule(), center_spacing_rule()], [2], DOM, pool=Slow())
    assert res.status == "timeout" and res.status != "no_witness_in_model"


def test_killed_solver_recovers_on_next_call():
    with SolverPool() as p:
        payload = {
            "mode": "disagree",
            "rules": [gap_rule(), center_spacing_rule()],
            "n": 2,
            "domain": DOM.canonical(),
            "threshold": "1",
            "timeout_ms": 500,
            "memory_mb": 512,
        }
        assert p.solve(payload, wall_s=0.0) is None  # overran the wall clock -> process killed
        assert p.solve(payload, wall_s=30.0)["status"] == "sat"  # respawned


def test_unknown_rejected_public_constraint_name():
    with pytest.raises(ValueError):
        find_public_constraint_violation(gap_rule(), ["be_pretty"], [2], DOM)


def test_gap_row_can_leave_the_canvas_for_some_in_domain_input(pool):
    res = find_public_constraint_violation(
        gap_rule(gap=24, left=80, top=120), ["stay_on_canvas"], [8], DOM, pool=pool
    )
    assert res.status == "witness_found" and res.witness.kind == "constraint_violation"


def test_noop_rule_violates_nothing_in_this_model(pool):
    res = find_public_constraint_violation(
        [{"op": "let", "name": "a", "value": 1}],
        ["preserve_sizes", "stay_on_canvas"],
        [2, 3],
        DOM,
        pool=pool,
    )
    assert res.status == "no_witness_in_model"


def test_resize_rule_violates_preserve_sizes(pool):
    rule = [
        {
            "op": "emit_target",
            "kind": "resize_existing",
            "target": R("objects.0"),
            "w": op("add", get(R("objects.0"), "w"), 1),
            "h": get(R("objects.0"), "h"),
        }
    ]
    res = find_public_constraint_violation(rule, ["preserve_sizes"], [2], DOM, pool=pool)
    assert res.status == "witness_found"


def test_the_work_limit_gives_the_same_verdict_every_time_and_reports_its_usage(pool):
    """Verdicts must not depend on CPU speed: a run limited by z3's resource counter is reproducible, unlike a wall clock."""
    runs = [
        find_disagreement(
            [gap_rule(), center_spacing_rule()],
            [2],
            DOM,
            budget=SolverBudget(rlimit=1),
            pool=pool,  # far below what any check needs
        ).status
        for _ in range(3)
    ]
    assert runs == ["timeout"] * 3, runs
    ok = find_disagreement([gap_rule(), center_spacing_rule()], [2], DOM, pool=pool)
    assert ok.status == "witness_found"
