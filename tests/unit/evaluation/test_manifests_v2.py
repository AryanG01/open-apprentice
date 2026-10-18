import json
from functools import lru_cache

import pytest

from open_apprentice.evaluation.battery_v2 import build_battery
from open_apprentice.evaluation.manifests_v2 import (
    GateRefused,
    calibration_manifest,
    check_live_gate,
    manifest_id,
    measured_call_usd,
    run_live,
)

TOKENS = {"per_system": {"A": {"tokens_per_episode": 11328, "attempts_mean": 2},
                         "B": {"tokens_per_episode": 18486, "attempts_mean": 3},
                         "D": {"tokens_per_episode": 11328, "attempts_mean": 2}}}  # fmt: skip


@lru_cache(maxsize=None)
def _dev():
    return tuple(build_battery("dev"))


def _budget(tmp_path, spent):
    root = tmp_path / "budget"
    root.mkdir(exist_ok=True)
    (root / "budget.json").write_text(json.dumps(
        {"authorized_total_usd": 50.0, "reserve_usd": 10.0, "funded_usd": 50.0}))  # fmt: skip
    (root / "spend.jsonl").write_text(json.dumps({"usd": spent}) + "\n")
    return root


def _approve(tmp_path, m, **extra):
    d = tmp_path / "approved"
    d.mkdir(exist_ok=True)
    approved = dict(m, approved=True, approved_by="owner (chat)", approved_at="2026-10-17") | extra
    (d / f"{m['manifest_id']}.json").write_text(json.dumps(approved))
    return d


def _run(m, **kw):
    return {
        "split": m["split"],
        "systems": m["systems"],
        "episodes": m["task_ids"],
        "repeats": m["repeats"],
    } | kw


def _man():
    return calibration_manifest(list(_dev()), TOKENS, spent_usd=0.0, spendable_usd=40.0, reserve_usd=5.0,
                                call_usd=0.05)  # fmt: skip


def _never_called():
    raise AssertionError("a provider was built before the gate passed")


def test_calibration_manifest_states_what_the_spec_asks():
    m = calibration_manifest(list(_dev()), TOKENS, spent_usd=38.6, spendable_usd=40.0, reserve_usd=5.0,
                             call_usd=0.05)  # fmt: skip
    assert len(m["task_ids"]) == 5 and m["systems"] == ["A", "B"] and m["runs"] == 10
    assert m["attempt_ceilings"] == {"A": 12, "B": 12}
    assert m["worst_case_per_attempt_usd"] == round((16_000 + 32_000) * 4.0 / 1e6, 4)
    assert m["worst_case_total_usd"] > m["estimate_usd"] > 0
    assert m["estimate_usd"] == round(
        5 * 2 * 0.05 + 5 * 3 * 0.05, 4
    )  # episodes x mean attempts x measured $/call
    assert m["protected_reserve_usd"] == 5.0
    assert "not an A-versus-B result" in m["establishes"]
    assert {"run_cap", "global_ceiling", "boundary_violation"} <= set(m["stop_conditions"])
    assert m["manifest_id"] == manifest_id(m)


def test_an_explicit_ceiling_is_kept_and_partial_coverage_is_stated():
    m = calibration_manifest(list(_dev()), TOKENS, spent_usd=0.0, spendable_usd=40.0, reserve_usd=5.0,
                             call_usd=0.05, ceiling_usd=0.5)  # fmt: skip
    assert m["ceiling_usd"] == 0.5 and m["expected_coverage"] < 1


def test_measured_call_cost_is_the_mean_over_model_calls(tmp_path):
    root = _budget(tmp_path, 0.0)
    rows = [
        {"usd": 0.04, "role": "hypotheses"},
        {"usd": 0.06, "role": "agent"},
        {"usd": 9.0, "role": "binding"},
    ]
    (root / "spend.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert measured_call_usd(root) == 0.05


def test_live_without_a_manifest_refuses(tmp_path):
    with pytest.raises(GateRefused, match="manifest"):
        run_live(None, 1.0, _never_called, {}, tmp_path / "approved", _budget(tmp_path, 0.0))


def test_an_unapproved_or_tampered_manifest_refuses(tmp_path):
    m = _man()
    with pytest.raises(GateRefused, match="approved"):
        run_live(
            m["manifest_id"],
            0.5,
            _never_called,
            _run(m),
            tmp_path / "approved",
            _budget(tmp_path, 0.0),
        )
    d = _approve(tmp_path, m, estimate_usd=0.0)
    with pytest.raises(GateRefused, match="does not match"):
        check_live_gate(m["manifest_id"], 0.5, _run(m), d, tmp_path)


def test_a_copy_without_the_owners_approval_fields_refuses(tmp_path):
    m = _man()
    d = _approve(tmp_path, m, approved=False)
    with pytest.raises(GateRefused, match="approval"):
        check_live_gate(m["manifest_id"], 0.5, _run(m), d, _budget(tmp_path, 0.0))


def test_a_run_that_differs_from_the_manifest_refuses(tmp_path):
    m = _man()
    d = _approve(tmp_path, m)
    for bad in (_run(m, split="final"), _run(m, systems=["A", "B", "C", "D"]), _run(m, repeats=3),
                _run(m, episodes=m["task_ids"][:2])):  # fmt: skip
        with pytest.raises(GateRefused, match="manifest"):
            run_live(m["manifest_id"], 0.5, _never_called, bad, d, _budget(tmp_path, 0.0))


def test_a_cap_above_the_ceiling_or_not_positive_refuses(tmp_path):
    m = _man()
    d = _approve(tmp_path, m)
    for cap, why in ((m["ceiling_usd"] + 0.01, "ceiling"), (0.0, "positive"), (-1.0, "positive")):
        with pytest.raises(GateRefused, match=why):
            run_live(m["manifest_id"], cap, _never_called, _run(m), d, _budget(tmp_path, 0.0))


def test_a_reserve_breach_refuses_before_any_provider_call(tmp_path):
    m = _man()
    d = _approve(tmp_path, m)
    root = _budget(tmp_path, 39.9)  # spendable is 40: the cap would reach into the $10 reserve
    with pytest.raises(GateRefused, match="reserve"):
        run_live(m["manifest_id"], m["ceiling_usd"], _never_called, _run(m), d, root)


def test_a_passing_gate_hands_over_to_the_runner(tmp_path):
    m = _man()
    d = _approve(tmp_path, m)
    seen = []
    run_live(m["manifest_id"], m["ceiling_usd"], _never_called, _run(m), d, _budget(tmp_path, 0.0),
             runner=lambda man, cap, factory: seen.append((man["manifest_id"], cap)))  # fmt: skip
    assert seen == [(m["manifest_id"], m["ceiling_usd"])]


def test_cli_live_without_manifest_exits_refused():
    from typer.testing import CliRunner

    from open_apprentice.cli import app

    r = CliRunner().invoke(app, ["eval", "run", "--split", "dev", "--mode", "live"])
    assert r.exit_code == 2 and "manifest" in r.output


def test_cli_live_run_does_not_fall_through_to_the_offline_runner(monkeypatch):
    from typer.testing import CliRunner

    import open_apprentice.evaluation.manifests_v2 as mv
    from open_apprentice.cli import app

    seen = {}
    monkeypatch.setattr(
        mv, "run_live", lambda mid, cap, factory, run, runner=None: seen.update(run=run)
    )
    r = CliRunner().invoke(app, ["eval", "run", "--split", "dev", "--mode", "live", "--manifest", "x",
                                 "--cap-usd", "0.5", "--resume", "cal-x"])  # fmt: skip
    assert r.exit_code == 0, r.output
    assert seen["run"]["split"] == "dev"


def test_a_calibration_can_name_its_episodes():
    ep = next(e for e in _dev() if e.stratum == "beyond")
    m = calibration_manifest(
        list(_dev()), TOKENS, 0.0, 40.0, 5.0, 0.05, 0.4, systems=("B",), task_ids=[ep.id]
    )
    assert m["task_ids"] == [ep.id] and m["task_strata"] == ["beyond"] and m["runs"] == 1


def test_a_hash_mismatch_is_a_clean_cli_refusal(monkeypatch):
    from typer.testing import CliRunner

    import open_apprentice.evaluation.manifests_v2 as mv
    from open_apprentice.cli import app
    from open_apprentice.evaluation.battery_v2 import FrozenMismatch

    def boom(*a, **k):
        raise FrozenMismatch("episodes/x.private.json does not match its recorded hash")

    monkeypatch.setattr(mv, "run_live", boom)
    r = CliRunner().invoke(
        app,
        ["eval", "run", "--split", "final", "--mode", "live", "--manifest", "x", "--cap-usd", "1"],
    )
    assert r.exit_code == 2 and "refused: hash mismatch" in r.output


def test_the_funded_tier_is_two_manifests_with_the_right_runs():
    from open_apprentice.evaluation.manifests_v2 import funded_manifests

    ids = [f"e{i}" for i in range(36)]
    ab, d = funded_manifests(ids, ids[:8], {"A": 0.11, "B": 0.19, "D": 0.11}, reserve_usd=10.0)
    assert (ab["runs"], ab["systems"], ab["repeats"], ab["task_ids"]) == (216, ["A", "B"], 3, ids)
    assert (d["runs"], d["systems"], d["task_ids"]) == (24, ["D"], ids[:8])
    assert (
        ab["estimate_usd"] == round(108 * 0.11 + 108 * 0.19, 2)
        and ab["ceiling_usd"] >= ab["estimate_usd"]
    )
    assert ab["split"] == d["split"] == "final" and not ab["approved"]


def test_measured_episode_cost_comes_from_live_calibration_rows(tmp_path):
    from open_apprentice.evaluation.manifests_v2 import measured_episode_usd

    d = tmp_path / "cal-x"
    d.mkdir()
    rows = [{"method": "A", "usd": 0.1, "origin": "live", "failure": None},
            {"method": "A", "usd": 0.3, "origin": "live", "failure": None},
            {"method": "B", "usd": 0.0, "origin": "live", "failure": "budget_stop"},
            {"method": "B", "usd": 0.2, "origin": "live", "failure": None}]  # fmt: skip
    (d / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    assert measured_episode_usd(tmp_path) == {"A": 0.2, "B": 0.2}


def test_funded_ceilings_can_be_set_to_fit_the_budget():
    from open_apprentice.evaluation.manifests_v2 import funded_manifests

    ids = [f"e{i}" for i in range(36)]
    ab, d = funded_manifests(
        ids,
        ids[:8],
        {"A": 0.11, "B": 0.19, "D": 0.11},
        10.0,
        ab_ceiling_usd=33.0,
        d_ceiling_usd=3.0,
    )
    assert ab["ceiling_usd"] == 33.0 and d["ceiling_usd"] == 3.0
    assert ab["expected_coverage"] == round(min(1.0, 33.0 / ab["estimate_usd"]), 2)


def test_d_runs_on_the_catalogue_clarification_episodes_plus_the_first_sequential_ones():
    from open_apprentice.evaluation.manifests_v2 import d_episode_ids

    eps = [
        {"id": f"c{i}", "stratum": "catalogue", "clarification_required": i < 4} for i in range(8)
    ]
    eps += [
        {"id": f"s{i:02d}", "stratum": "sequential", "clarification_required": True}
        for i in (9, 3, 7, 1, 5, 2)
    ]
    eps += [{"id": "b0", "stratum": "beyond", "clarification_required": False}]
    assert d_episode_ids(eps) == ["c0", "c1", "c2", "c3", "s01", "s02", "s03", "s05"]


def test_policy_v2_systems_are_priced_from_their_base_system_with_more_calls():
    from open_apprentice.evaluation.manifests_v2 import V2_CALL_FACTOR, _estimate

    tokens = {"per_system": {"A": {"attempts_mean": 2.0}, "D": {"attempts_mean": 2.0}}}
    calls, usd = _estimate({"A": 10, "A2": 10, "D2": 5}, tokens, 0.05)
    assert calls == round(10 * 2.0 + 10 * 2.0 * V2_CALL_FACTOR + 5 * 2.0 * V2_CALL_FACTOR, 2)
    assert usd == round(calls * 0.05, 4) and V2_CALL_FACTOR > 1
