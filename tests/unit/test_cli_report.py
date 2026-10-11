import dataclasses
import json

from typer.testing import CliRunner

from open_apprentice.cli import app
from open_apprentice.evaluation.metrics import Row


def _row(method, episode, ok):
    return dataclasses.asdict(
        Row(
            episode=episode,
            rep=0,
            method=method,
            task_id=f"{episode}-t",
            stage="transfer",
            committed=True,
            claimed_success=True,
            correct=ok,
            origin="live",
        )
    )


def test_report_rebuilds_from_stored_rows_and_marks_dev_runs(tmp_path):
    run = tmp_path / "development-x"
    run.mkdir()
    rows = [
        _row(m, f"e{i}", ok)
        for i in range(3)
        for m, ok in (("full_v1_2", True), ("structured_procedure", i == 0))
    ]
    (run / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    res = CliRunner().invoke(app, ["report", "--run-dir", str(run), "--write"])
    assert res.exit_code == 0, res.output
    rep = json.loads((run / "report.json").read_text())
    assert rep["gates_27_5"]["status"] == "not_evaluated_on_non_final_runs"
    assert "DEVELOPMENT/PILOT RUN" in rep["label"] and (run / "report.md").exists()


def test_report_refuses_missing_rows(tmp_path):
    assert CliRunner().invoke(app, ["report", "--run-dir", str(tmp_path)]).exit_code == 1
