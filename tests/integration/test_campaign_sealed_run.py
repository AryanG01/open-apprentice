import json

from open_apprentice.evaluation.campaign_sealed import run_sealed, seal

from ..unit.evaluation.test_campaign_sealed import _write
from .conftest import TOKEN


def test_a_sealed_toy_set_runs_on_both_backends(engine_url, tmp_path):
    root = tmp_path / "set"
    _write(root, "toy_short", "short_b", ["layout"])
    _write(root, "toy_long", "de_long_a", ["split"])
    seal(root, tmp_path / "manifest.json")
    summary = run_sealed(root, tmp_path / "manifest.json", engine_url, TOKEN, tmp_path / "out")
    rows = summary["rows"]
    assert {(r["banner"], r["backend"]) for r in rows} == {
        (b, e) for b in ("toy_short", "toy_long") for e in ("konva", "fabric")
    }
    assert all(r["passed"] for r in rows), rows
    report = (tmp_path / "out" / "report.md").read_text()
    assert "4 of 4" in report and json.loads((tmp_path / "out" / "rows.json").read_text()) == rows
