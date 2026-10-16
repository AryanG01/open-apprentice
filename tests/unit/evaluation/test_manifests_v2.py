import json
from functools import lru_cache

import pytest

from open_apprentice.evaluation.battery_v2 import build_battery
from open_apprentice.evaluation.manifests_v2 import (
    GateRefused,
    calibration_manifest,
    check_live_gate,
    funded_manifest,
    manifest_id,
    run_live,
)

TOKENS = {"per_system": {"A": {"tokens_per_episode": 11328}, "B": {"tokens_per_episode": 18486},
                         "D": {"tokens_per_episode": 11328}}}  # fmt: skip


@lru_cache(maxsize=None)
def _dev():
    return tuple(build_battery("dev"))


def _budget(tmp_path, spent):
    root = tmp_path / "budget"
    root.mkdir()
    (root / "budget.json").write_text(json.dumps(
        {"authorized_total_usd": 50.0, "reserve_usd": 10.0, "funded_usd": 50.0}))  # fmt: skip
    (root / "spend.jsonl").write_text(json.dumps({"usd": spent}) + "\n")
    return root


def _approve(tmp_path, m):
    d = tmp_path / "approved"
    d.mkdir(exist_ok=True)
    (d / f"{m['manifest_id']}.json").write_text(json.dumps(m))
    return d


def _never_called():
    raise AssertionError("a provider was built before the gate passed")


def test_calibration_manifest_states_what_the_spec_asks():
    m = calibration_manifest(list(_dev()), TOKENS, spent_usd=38.6, spendable_usd=40.0)
    assert len(m["task_ids"]) == 5 and m["systems"] == ["A", "B"] and m["runs"] == 10
    assert m["attempt_ceilings"] == {"A": 12, "B": 12}
    assert m["worst_case_per_attempt_usd"] > 0 and m["worst_case_total_usd"] > m["estimate_usd"] > 0
    assert m["estimate_usd"] == round((5 * 11328 + 5 * 18486) * 3.5 / 1e6, 4)
    assert m["protected_reserve_usd"] == 10.0
    assert "not an A-versus-B result" in m["establishes"]
    assert {"run_cap", "global_ceiling", "boundary_violation"} <= set(m["stop_conditions"])
    assert m["manifest_id"] == manifest_id(m)


def test_funded_manifest_counts_240_runs_and_is_not_approved():
    m = funded_manifest(36, 8, TOKENS)
    assert m["runs"] == 240 and m["approved"] is False


def test_live_without_a_manifest_refuses(tmp_path):
    with pytest.raises(GateRefused, match="manifest"):
        run_live(None, 1.0, _never_called, tmp_path / "approved", _budget(tmp_path, 0.0))


def test_an_unapproved_or_tampered_manifest_refuses(tmp_path):
    m = calibration_manifest(list(_dev()), TOKENS, spent_usd=0.0, spendable_usd=40.0)
    with pytest.raises(GateRefused, match="approved"):
        run_live(
            m["manifest_id"], 0.5, _never_called, tmp_path / "approved", _budget(tmp_path, 0.0)
        )
    d = _approve(tmp_path, dict(m, estimate_usd=0.0))
    with pytest.raises(GateRefused, match="does not match"):
        check_live_gate(m["manifest_id"], 0.5, d, tmp_path)


def test_a_cap_above_the_ceiling_refuses(tmp_path):
    m = calibration_manifest(list(_dev()), TOKENS, spent_usd=0.0, spendable_usd=40.0)
    d = _approve(tmp_path, m)
    with pytest.raises(GateRefused, match="ceiling"):
        run_live(
            m["manifest_id"], m["ceiling_usd"] + 0.01, _never_called, d, _budget(tmp_path, 0.0)
        )


def test_a_reserve_breach_refuses_before_any_provider_call(tmp_path):
    m = calibration_manifest(list(_dev()), TOKENS, spent_usd=0.0, spendable_usd=40.0)
    d = _approve(tmp_path, m)
    root = _budget(tmp_path, 39.9)  # spendable is 40: the cap would reach into the $10 reserve
    with pytest.raises(GateRefused, match="reserve"):
        run_live(m["manifest_id"], m["ceiling_usd"], _never_called, d, root)


def test_a_passing_gate_hands_over_to_the_runner(tmp_path):
    m = calibration_manifest(list(_dev()), TOKENS, spent_usd=0.0, spendable_usd=40.0)
    d = _approve(tmp_path, m)
    seen = []
    run_live(m["manifest_id"], m["ceiling_usd"], _never_called, d, _budget(tmp_path, 0.0),
             runner=lambda man, cap, factory: seen.append((man["manifest_id"], cap)))  # fmt: skip
    assert seen == [(m["manifest_id"], m["ceiling_usd"])]


def test_cli_live_without_manifest_exits_refused():
    from typer.testing import CliRunner

    from open_apprentice.cli import app

    r = CliRunner().invoke(app, ["eval", "run", "--split", "dev", "--mode", "live"])
    assert r.exit_code == 2 and "manifest" in r.output
