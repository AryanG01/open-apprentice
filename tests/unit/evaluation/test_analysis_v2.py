import json

from open_apprentice.evaluation.analysis_v2 import episode_rates, paired, report, sign_test


def _row(ep, system, outcome, stratum="catalogue", rep=0, origin="mock", **kw):
    base = {
        "episode": ep, "method": system, "rep": rep, "stratum": stratum, "spec_kind": "catalogue",
        "terminal_outcome": outcome, "origin": origin, "model": "Fixture", "correction": None,
        "release_blocking": [], "diagnostics": {}, "usd": 0.0, "tokens": 0, "wall_s": 1.0,
    }  # fmt: skip
    return base | kw


def test_sign_test_matches_hand_computation():
    assert round(sign_test(7, 1)["p_exact"], 4) == 0.0703
    assert sign_test(0, 0)["p_exact"] == 1.0


def _pairs(pos, neg, ties):
    rows, k = [], 0
    for a, b, n in (("correct_complete", "wrong_commit", pos), ("wrong_commit", "correct_complete", neg),
                    ("correct_complete", "correct_complete", ties)):  # fmt: skip
        for _ in range(n):
            rows += [_row(f"e{k}", "A", a), _row(f"e{k}", "B", b)]
            k += 1
    return rows


def test_episode_rates_average_repeats():
    rows = [_row("e1", "A", "correct_complete", rep=0), _row("e1", "A", "wrong_commit", rep=1)]
    assert episode_rates(rows, "A") == {"e1": 0.5}


def test_paired_counts_signs_and_ties():
    p = paired(_pairs(7, 1, 2), "A", "B")
    assert p["sign"] == {"pos": 7, "neg": 1, "ties": 2, "p_exact": sign_test(7, 1)["p_exact"]}
    assert p["mean_diff"] == 0.6 and p["n_episodes"] == 10


def test_bootstrap_is_deterministic_per_seed():
    rows = _pairs(5, 3, 2)
    assert paired(rows, "A", "B", seed=3)["ci95"] == paired(rows, "A", "B", seed=3)["ci95"]
    cis = {tuple(paired(rows, "A", "B", draws=40, seed=s)["ci95"]) for s in range(20)}
    assert len(cis) > 1  # the seed drives the resampling


def test_report_labels_mock_rows_and_lists_release_blocking_failures_first(tmp_path):
    rows = _pairs(3, 1, 1) + [_row("e9", "A", "error", release_blocking=["boundary_violation"]),
                              _row("e9", "B", "correct_complete")]  # fmt: skip
    (tmp_path / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (tmp_path / "manifest.json").write_text(
        json.dumps({"run_id": "x", "split": "dev", "mode": "mock"})
    )
    md = report(tmp_path)
    assert "not a model result" in md
    assert md.index("Release-blocking") < md.index("Primary endpoints")
    assert "boundary violations: 1" in md
    assert "Intervals describe this task collection only." in md
    assert "learning success" in md and "correction success" in md


def test_a_mock_row_presented_as_live_is_release_blocking(tmp_path):
    rows = [_row("e1", "A", "correct_complete", origin="live"), _row("e1", "B", "wrong_commit")]
    (tmp_path / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (tmp_path / "manifest.json").write_text(
        json.dumps({"run_id": "x", "split": "dev", "mode": "mock"})
    )
    assert "rows labelled live in a mock run: 1" in report(tmp_path)


def test_cli_report_writes_report_md(tmp_path):
    from typer.testing import CliRunner

    from open_apprentice.cli import app

    (tmp_path / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in _pairs(2, 1, 0)))
    (tmp_path / "manifest.json").write_text(
        json.dumps({"run_id": "x", "split": "dev", "mode": "mock"})
    )
    r = CliRunner().invoke(app, ["eval", "report", "--run-dir", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "report.md").read_text().startswith("# Evaluation report")


def test_token_estimate_reads_attempts_from_the_kept_outcomes(tmp_path):
    from open_apprentice.evaluation.analysis_v2 import COMPLETION_ASSUMED, token_estimate

    rows = [_row("e1", "B", "correct_complete"), _row("e1", "A", "correct_complete")]
    (tmp_path / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    turn = {"type": "AgentTurn", "payload": {"usage": {"prompt_tokens": 1000}}}
    issued = {"type": "ActionIssued", "payload": {"kind": "AgentTurn"}}
    prop = {"log": "learn", "type": "ActionIssued", "payload": {"kind": "RequestModelProposal"}}
    for name, events in (("e1-B-r0", [issued, turn, issued, turn]), ("e1-A-r0", [prop])):
        d = tmp_path / "episodes" / name
        d.mkdir(parents=True)
        (d / "outcome.json").write_text(json.dumps({"events": events}))
    est = token_estimate(tmp_path)
    assert est["per_system"]["B"]["attempts_mean"] == 2
    assert est["per_system"]["B"]["tokens_per_episode"] == 2 * (1000 + COMPLETION_ASSUMED)
    assert est["per_system"]["A"]["attempts_mean"] == 1
    assert est["per_system"]["A"]["tokens_per_episode"] > COMPLETION_ASSUMED
