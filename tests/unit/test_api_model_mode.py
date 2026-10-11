"""Nemotron mode plumbing with a SCRIPTED mock model: availability, metering, the global spend cap, and failure handling. No network."""

import pytest
from fastapi.testclient import TestClient

from open_apprentice.providers.base import TruncatedOutput
from open_apprentice.providers.mock import MockProvider
from tests.fixtures_rules import CLAMPED_MARGIN, CONST_MARGIN, PROP_MARGIN


def _cands():
    rules = [
        ("fixed 12px inset", CONST_MARGIN),
        ("8% inset", PROP_MARGIN()),
        ("clamped inset", CLAMPED_MARGIN()),
    ]
    return {"candidates": [{"summary": n, "rule": r} for n, r in rules]}


class Priced(MockProvider):
    """A mock that reports a cost per call, so the accounting path (not just the token path) is exercised."""

    async def _call(self, messages, *, max_tokens, ctx):
        raw = await super()._call(messages, max_tokens=max_tokens, ctx=ctx)
        raw.usd = 0.02
        return raw


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("OA_NO_LOCAL_ENGINE", "1")
    monkeypatch.delenv("ENGINE_URL", raising=False)
    monkeypatch.delenv("DEMO_MODEL_ENABLED", raising=False)
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        yield c


def test_model_mode_is_off_unless_the_operator_opts_in(client):
    assert client.get("/health/ready").json()["model"]["available"] is False
    r = client.post("/api/teach", json={"mode": "nemotron"})
    assert r.status_code == 503 and "not available" in r.json()["detail"]
    assert client.post("/api/teach", json={"mode": "bogus"}).status_code == 422
    assert (
        client.post("/api/teach").json()["mode"] == "reference"
    )  # the default never touches a model


def test_model_mode_labels_meters_and_counts_spend(client):
    from open_apprentice.api.app import app

    app.state.provider = Priced({"hypotheses": [_cands()]})
    st = client.post("/api/teach", json={"mode": "nemotron"}).json()
    assert st["mode"] == "nemotron" and st["label"]["mode"] == "LIVE ENGINE + NVIDIA NEMOTRON"
    m = st["meter"]
    assert m["label"] == "LIVE" and m["session_calls"] >= 1 and m["session_tokens"] > 0
    assert (
        m["server_spend_usd"]
        == pytest.approx(0.02 * m["session_calls"])
        == pytest.approx(m["session_usd"])
    )
    assert m["server_cap_usd"] == 2.0
    assert st["state"] == "AWAITING_USER" and len(st["question"]["options"]) >= 2
    ready = client.get("/health/ready").json()["model"]
    assert ready["available"] is True and ready["spend_usd"] == m["server_spend_usd"]


def test_spend_cap_refuses_model_mode_instead_of_degrading(client, monkeypatch):
    from open_apprentice.api.app import app

    app.state.provider = MockProvider({"hypotheses": [_cands()]})
    monkeypatch.setenv("DEMO_MODEL_MAX_USD", "1.0")
    app.state.spend["usd"] = 0.9  # less than the reserve left
    r = client.post("/api/teach", json={"mode": "nemotron"})
    assert r.status_code == 402 and "used up" in r.json()["detail"]
    assert client.post("/api/teach").status_code == 200  # the free mode keeps working


def test_a_failing_model_call_is_reported_not_swallowed_and_leaves_no_zombie_session(client):
    from open_apprentice.api.app import app

    class Broken(MockProvider):
        async def _call(self, messages, *, max_tokens, ctx):
            raise TruncatedOutput("hit the completion limit")

    app.state.provider = Broken({})
    n = len(app.state.live)
    r = client.post("/api/teach", json={"mode": "nemotron"})
    assert r.status_code == 502 and "MODEL_TRUNCATED" in r.json()["detail"]
    assert len(app.state.live) == n
