import json

from typer.testing import CliRunner

from open_apprentice.cli import app
from tests.unit.drawio.fixtures import drawio, model, node


def test_drawio_check_reports_refusal_reason(tmp_path):
    p = tmp_path / "bad.drawio"
    p.write_bytes(drawio(model([node("n1", -5, 0)])))
    r = CliRunner().invoke(app, ["drawio-check", str(p)])
    assert r.exit_code == 2 and "outside the page" in r.output


def test_staging_check_store_race_on_local_store(tmp_path, monkeypatch):
    monkeypatch.setenv("OA_STORE", "local")
    monkeypatch.setenv("OA_STORE_DIR", str(tmp_path))
    r = CliRunner().invoke(app, ["staging-check", "--only", "race"])
    line = json.loads(r.output.strip().splitlines()[-1])
    assert r.exit_code == 0
    assert line == {"check": "race", "ok": True, "winners": 1, "precondition_failures": 1}


def test_staging_check_survival_reads_back_what_it_wrote(tmp_path, monkeypatch):
    monkeypatch.setenv("OA_STORE", "local")
    monkeypatch.setenv("OA_STORE_DIR", str(tmp_path))
    runner = CliRunner()
    assert (
        runner.invoke(app, ["staging-check", "--only", "survival", "--phase", "read"]).exit_code
        == 1
    )
    assert (
        runner.invoke(app, ["staging-check", "--only", "survival", "--phase", "write"]).exit_code
        == 0
    )
    assert (
        runner.invoke(app, ["staging-check", "--only", "survival", "--phase", "read"]).exit_code
        == 0
    )
