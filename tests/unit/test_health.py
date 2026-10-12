"""Readiness must reflect whether the graphics engine actually answers, not merely whether it was configured."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("OA_NO_LOCAL_ENGINE", "1")
    monkeypatch.delenv("ENGINE_URL", raising=False)
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        yield c


def test_ready_reports_an_unreachable_engine_as_down(client):
    from open_apprentice.api.app import app

    app.state.engine = ("http://127.0.0.1:9", "token")  # nothing listens on the discard port
    r = client.get("/health/ready").json()
    assert r["engine"] is False
    assert "not responding" in r["engine_error"]


def test_ready_without_an_engine_says_so(client):
    r = client.get("/health/ready").json()
    assert r["engine"] is False
