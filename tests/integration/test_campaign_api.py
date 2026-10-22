"""Campaign lane over HTTP on the REAL engine (opt-in: OA_ENGINE_TESTS=1)."""

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import TOKEN


@pytest.fixture()
def client(engine_url, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_URL", engine_url)
    monkeypatch.setenv("EVALUATOR_TOKEN", TOKEN)
    monkeypatch.setenv("OA_STORE_DIR", str(tmp_path))
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        c.engine_url = engine_url
        yield c


def _engine_sessions(c) -> int:
    return httpx.get(c.engine_url + "/health/live").json()["sessions"]


def _workspace(c) -> dict:
    r = c.post("/api/campaign/workspaces")
    assert r.status_code == 200, r.text
    return r.json()


def test_fixtures_are_listed_with_thumbnails(client):
    fx = client.get("/api/campaign/fixtures").json()["fixtures"]
    kinds = {f["id"]: f["kind"] for f in fx}
    assert kinds == {
        "teach_before": "teaching",
        "short_a": "banner",
        "short_b": "banner",
        "de_long_a": "banner",
        "de_long_b": "banner",
        "fr_long": "banner",
        "missing_role": "broken",
        "duplicate_role": "broken",
    }
    assert all(f["png"].startswith("data:image/png;base64,") for f in fx)
    assert {f["id"]: f["locale"] for f in fx}["de_long_a"] == "de"
    assert _engine_sessions(client) == 0


def test_a_workspace_learns_the_taught_layout(client):
    ws = _workspace(client)
    assert len(ws["workspace_id"]) == 32
    assert ws["learned"]["origin"] == "search"
    assert ws["learned"]["candidates"] == [{"origin": "search", "reproduces": True, "reason": ""}]
    assert ws["teaching"]["before_png"].startswith("data:image/png") and ws["teaching"][
        "after_png"
    ].startswith("data:image/png")
    assert _engine_sessions(client) == 0


def test_unknown_workspace_is_404(client):
    r = client.get("/api/campaign/workspaces/" + "0" * 32 + "/preferences")
    assert r.status_code == 404 and r.json()["detail"] == "unknown or expired workspace"


def test_the_oldest_workspace_is_evicted_past_the_cap(client):
    first = _workspace(client)["workspace_id"]
    for _ in range(20):
        _workspace(client)
    assert client.get(f"/api/campaign/workspaces/{first}/preferences").status_code == 404
