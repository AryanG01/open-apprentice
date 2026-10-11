"""Offline replay of a REAL evidence package from the live demo, and proof that it says no when the package is tampered with."""

import copy
import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from open_apprentice.cli import app as cli_app
from open_apprentice.evaluation.replay import replay_package
from tests.integration.conftest import TOKEN
from tests.integration.test_api_teach import _teach


@pytest.fixture(scope="module")
def packages(engine_url):
    import os

    os.environ["ENGINE_URL"], os.environ["EVALUATOR_TOKEN"] = engine_url, TOKEN
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        sid, _ = _teach(c)
        c.post(f"/api/teach/{sid}/run", json={"width": 260, "backend": "fabric"})
        good = c.get(f"/api/teach/{sid}/evidence.json").json()
        c.post(f"/api/teach/{sid}/break", json={"backend": "fabric", "samples": 6})
        good_with_stress = c.get(f"/api/teach/{sid}/evidence.json").json()
        c.post(
            f"/api/teach/{sid}/run", json={"width": 300, "backend": "fabric", "tool_change": True}
        )
        failing = c.get(f"/api/teach/{sid}/evidence.json").json()
    return good, good_with_stress, failing


def names(res, status):
    return [c["name"] for c in res["checks"] if c["passed"] is status]


def test_a_real_package_replays_clean_offline(packages):
    res = replay_package(packages[1])
    assert res["passed"] and not names(res, False), res
    assert "stress-test counts add up" in names(
        res, True
    ) and "sealed concept hash recomputed" in names(res, True)
    findings = [c["detail"] for c in res["checks"] if c["passed"] is None]
    assert any(d.startswith("matches") for d in findings), findings


def test_a_package_that_honestly_documents_a_failure_still_replays_consistently(packages):
    res = replay_package(packages[2])
    assert res["passed"], res  # its claim (FAIL) agrees with the recomputation
    assert any("DOES NOT MATCH" in c["detail"] for c in res["checks"] if c["passed"] is None)


@pytest.mark.parametrize(
    "tamper, expected_failure",
    [
        (
            lambda p: p["observed_geometry"][2].update(x=p["observed_geometry"][2]["x"] + 6)
            or p["observed_geometry"][0].update(x=0),
            "claim",
        ),
        (
            lambda p: p["concept"]["rule"][0].update(value=13),
            "sealed concept hash",
        ),
        (lambda p: p["ledger"][0]["payload"].update(tampered=True), "teaching ledger"),
        (lambda p: p["concept"].update(sealed_hash="0" * 64), "sealed concept hash"),
        (lambda p: p["result"]["binding"].update(program_hash="0" * 64), "native program matches"),
        (lambda p: p["result"].update(verifier_passed=False), "claim"),
        (
            lambda p: p.update(stress_test={"tested": 5, "passed": 5, "failed": 1, "failures": []}),
            "stress-test",
        ),
        (lambda p: p.update(confidence=0.97), "confidence"),
    ],
)
def test_tampering_is_detected(packages, tamper, expected_failure):
    p = copy.deepcopy(packages[1])
    tamper(p)
    res = replay_package(p)
    assert not res["passed"], "a tampered package must not replay clean"
    assert any(expected_failure in n for n in names(res, False)), (
        expected_failure,
        names(res, False),
    )


def test_cli_replays_a_file_and_exits_nonzero_on_tampering(packages, tmp_path):
    f = tmp_path / "ok.json"
    f.write_text(json.dumps(packages[1]))
    ok = CliRunner().invoke(cli_app, ["replay-evidence", str(f)])
    assert (
        ok.exit_code == 0
        and "every offline check passed" in ok.output
        and "does not re-run the graphics engine" in ok.output
    )
    bad = json.loads(f.read_text())
    bad["concept"]["rule"][0]["value"] = 99
    g = tmp_path / "bad.json"
    g.write_text(json.dumps(bad))
    r = CliRunner().invoke(cli_app, ["replay-evidence", str(g)])
    assert r.exit_code != 0 and "FAILED" in r.output
    assert (
        CliRunner().invoke(cli_app, ["replay-evidence", str(tmp_path / "nope.json")]).exit_code == 1
    )


def test_replay_endpoint_checks_any_package_and_rejects_nonsense(engine_url, packages):
    import os

    os.environ["ENGINE_URL"], os.environ["EVALUATOR_TOKEN"] = engine_url, TOKEN
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        ok = c.post("/api/replay", json={"package": packages[1]}).json()
        assert ok["passed"] is True
        bad = copy.deepcopy(packages[1])
        bad["concept"]["rule"][0]["value"] = 99
        assert c.post("/api/replay", json={"package": bad}).json()["passed"] is False
        assert c.post("/api/replay", json={"package": {"nonsense": 1}}).json()["passed"] is False
        assert c.post("/api/replay", json={"package": "text"}).status_code == 422
