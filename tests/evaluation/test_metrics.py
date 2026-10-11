"""Arithmetic and statistical-honesty checks on SYNTHETIC rows (origin=mock). They test the metric code only."""

import random

import pytest

from open_apprentice.evaluation.metrics import (
    Row,
    conditional_correctness,
    cost_totals,
    false_success,
    paired_cluster_bootstrap,
    success_rate,
)
from open_apprentice.evaluation.report import EmptyResults, build_report, render_markdown


def R(ep, method, ok, rep=0, i=0, stage="transfer", **kw):
    base = dict(
        episode=ep,
        rep=rep,
        method=method,
        task_id=f"{ep}-{i}",
        stage=stage,
        committed=True,
        claimed_success=True,
        correct=ok,
        origin="mock",
    )
    base.update(kw)
    return Row(**base)


def test_abstentions_and_failures_count_in_the_denominator_but_not_in_conditional_correctness():
    rows = [
        R("e", "m", True),
        R("e", "m", False, i=1),
        R("e", "m", None, i=2, committed=False, abstained=True, claimed_success=False),
        R("e", "m", None, i=3, committed=False, failure="budget_exhausted", claimed_success=False),
    ]
    assert success_rate(rows) == {"correct": 1, "scheduled": 4, "rate": 0.25}
    assert conditional_correctness(rows) == {"correct": 1, "committed": 2, "rate": 0.5}


def test_false_success_counts_claimed_but_rejected_outputs():
    rows = [
        R("e", "m", False),
        R("e", "m", True, i=1),
        R("e", "m", False, i=2, claimed_success=False),
    ]
    assert false_success(rows) == {"false_successes": 1, "claimed_successes": 2, "rate": 0.5}


def test_costs_are_separate_dimensions_and_unknown_usd_is_never_zero():
    rows = [
        R("e", "m", True, tokens=10, calls=1, usd=0.5),
        R("e", "m", True, i=1, tokens=5, actions=7, usd=None),
    ]
    c = cost_totals(rows)
    assert (
        (c["tokens"], c["calls"], c["actions"]) == (15, 1, 7)
        and c["rows_with_unknown_usd"] == 1
        and c["usd_known_total"] == 0.5
    )


def rows_for(effect, n_ep=12, reps=3, tasks=4, between_sd=0.0, seed=1):
    rng = random.Random(seed)
    out = []
    for e in range(n_ep):
        shift = rng.gauss(0, between_sd)
        for rep in range(reps):
            for i in range(tasks):
                pa = min(1, max(0, 0.5 + effect / 2 + shift))
                pb = min(1, max(0, 0.5 - effect / 2 + shift))
                out += [
                    R(f"ep{e}", "A", rng.random() < pa, rep, i),
                    R(f"ep{e}", "B", rng.random() < pb, rep, i),
                ]
    return out


def test_no_effect_interval_covers_zero_and_clear_effect_excludes_it():
    none = paired_cluster_bootstrap(rows_for(0.0), "A", "B")
    assert none["ci95"][0] <= 0 <= none["ci95"][1]
    clear = paired_cluster_bootstrap(rows_for(0.6), "A", "B")
    assert clear["ci95"][0] > 0 and clear["diff"] > 0.3


def test_clustering_widens_intervals_when_episodes_differ():
    """If episodes differ a lot, treating all rows as independent would be overconfident; clustering must not be."""
    homog = paired_cluster_bootstrap(rows_for(0.3, between_sd=0.0), "A", "B")
    hetero = paired_cluster_bootstrap(rows_for(0.3, between_sd=0.25), "A", "B")
    w = lambda r: r["ci95"][1] - r["ci95"][0]
    assert w(hetero) > w(homog)
    assert hetero["n_episodes"] == 12  # 288 rows per method are NOT 288 samples


def test_too_few_episodes_gives_no_interval_not_a_made_up_one():
    r = paired_cluster_bootstrap([R("e1", "A", True), R("e1", "B", False)], "A", "B")
    assert r["ci95"] is None and "fewer than 2" in r["note"]


def test_bootstrap_is_deterministic_for_a_seed():
    rows = rows_for(0.3)
    assert paired_cluster_bootstrap(rows, "A", "B", seed=5) == paired_cluster_bootstrap(
        rows, "A", "B", seed=5
    )


def test_report_refuses_empty_and_non_live_rows_unless_labelled_and_never_evaluates_gates_on_mock():
    with pytest.raises(EmptyResults):
        build_report([], ["A", "B"], ("A", "B"), "cfg")
    rows = rows_for(0.6)
    with pytest.raises(EmptyResults, match="non-live"):
        build_report(rows, ["A", "B"], ("A", "B"), "cfg")
    rep = build_report(rows, ["A", "B"], ("A", "B"), "cfg", allow_mock=True)
    assert (
        rep["label"].startswith("MOCK")
        and rep["gates_27_5"]["status"] == "not_evaluated_on_non_live_rows"
    )
    assert "improvement_over_strongest_baseline_pp" not in rep["gates_27_5"]
    md = render_markdown(rep)
    assert "MOCK" in md and "independent episodes" in md and "prospective" in md


def live(rows):
    return [Row(**{**r.__dict__, "origin": "live"}) for r in rows]


def test_live_rows_gate_requires_both_the_10pp_goal_and_a_positive_interval():
    big = build_report(live(rows_for(0.6, tasks=6)), ["A", "B"], ("A", "B"), "cfg")["gates_27_5"][
        "improvement_over_strongest_baseline_pp"
    ]
    assert (
        big["baseline"] == "B"
        and big["observed_pp"] > 40
        and big["ci95_pp"][0] > 0
        and big["met"] is True
    )
    small = build_report(live(rows_for(0.05, tasks=6)), ["A", "B"], ("A", "B"), "cfg")[
        "gates_27_5"
    ]["improvement_over_strongest_baseline_pp"]
    assert small["met"] is False  # <10pp and/or interval includes 0
