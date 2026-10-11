"""CLI contract: every spec 24.5 command is registered; unbuilt ones never fake success."""

import pytest
from typer.testing import CliRunner

from open_apprentice.cli import app
from open_apprentice.cli_exit import ExitState

runner = CliRunner()

SPEC_COMMANDS = [
    ["doctor"],
    ["config", "init"],
    ["admin", "create"],
    ["db", "upgrade"],
    ["provider", "probe"],
    ["demo", "seed"],
    ["run"],
    ["learn"],
    ["teach"],
    ["transfer"],
    ["compose"],
    ["compare"],
    ["benchmark", "freeze"],
    ["benchmark", "run"],
    ["replay"],
    ["export-skill"],
    ["challenge"],
    ["export-svg"],
    ["replay-evidence"],
    # v1.3 additions (docs/decisions.md #1)
    ["import-svg"],
    ["svg-apply"],
    ["svg-trial"],
]


@pytest.mark.parametrize("cmd", SPEC_COMMANDS, ids=lambda c: " ".join(c))
def test_command_registered_with_help(cmd):
    result = runner.invoke(app, [*cmd, "--help"])
    assert result.exit_code == 0, result.output


UNBUILT = [
    c
    for c in SPEC_COMMANDS
    if c not in (["doctor"], ["config", "init"], ["provider", "probe"], ["learn"], ["compare"])
]


@pytest.mark.parametrize("cmd", UNBUILT, ids=lambda c: " ".join(c))
def test_unbuilt_command_exits_not_implemented(cmd):
    result = runner.invoke(app, cmd)
    assert result.exit_code == int(ExitState.NOT_IMPLEMENTED)
    assert "NOT_IMPLEMENTED" in result.output


def test_exit_codes_unique():
    codes = [s.value for s in ExitState]
    assert len(codes) == len(set(codes))


def test_probe_without_live_is_a_dry_run_that_sends_nothing():
    r = runner.invoke(app, ["provider", "probe"])
    assert r.exit_code == 0 and "DRY RUN" in r.output and "Nothing sent" in r.output


def test_probe_live_without_credentials_is_blocked_not_passed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no .env here
    for k in ("NEBIUS_API_KEY", "PROVIDER_MODE"):
        monkeypatch.delenv(k, raising=False)
    r = runner.invoke(app, ["provider", "probe", "--live", "--max-usd", "1"])
    assert r.exit_code == int(ExitState.BLOCKED_NO_CREDENTIAL) and "NOT verified" in r.output


def test_probe_live_requires_an_explicit_ceiling_within_the_configured_one(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROVIDER_MODE", "nebius")
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    monkeypatch.setenv("LIVE_RUN_MAX_USD", "2")
    assert runner.invoke(app, ["provider", "probe", "--live"]).exit_code == int(
        ExitState.BUDGET_EXCEEDED
    )
    assert runner.invoke(app, ["provider", "probe", "--live", "--max-usd", "9"]).exit_code == int(
        ExitState.BUDGET_EXCEEDED
    )


def test_learn_refuses_the_final_split_and_is_a_dry_run_without_live(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(
        app, ["learn", "--split", "final", "--live", "--max-usd", "1"]
    ).exit_code == int(ExitState.VALIDATION_FAILED)
    r = runner.invoke(app, ["learn"])
    assert r.exit_code == 0 and "DRY RUN" in r.output


def test_compare_dry_run_prints_the_matrix_and_ceiling_and_refuses_final(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(
        app, ["compare", "--episodes", "2", "--methods", "enumerative_reference,full_v1_2"]
    )
    assert (
        r.exit_code == 0
        and "4 runs" in r.output
        and "worst-case model tokens: 600000" in r.output
        and "DRY RUN" in r.output
    )
    assert runner.invoke(
        app, ["compare", "--split", "final", "--live", "--max-usd", "1"]
    ).exit_code == int(ExitState.VALIDATION_FAILED)
    assert runner.invoke(app, ["compare", "--methods", "nope"]).exit_code == int(
        ExitState.VALIDATION_FAILED
    )
