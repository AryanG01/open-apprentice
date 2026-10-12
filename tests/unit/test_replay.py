"""Record/replay of a provider session: faithful, labelled, free, and refuses anything it did not record. Scripted mock, no network."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from open_apprentice.budget import Ledger, Limits
from open_apprentice.providers.base import CallContext, Message
from open_apprentice.providers.mock import MockProvider
from open_apprentice.providers.replay import (
    RecordingProvider,
    ReplayMismatch,
    ReplayProvider,
    load_tape,
)
from tests.unit.test_api_model_mode import Priced, _cands
from pydantic import BaseModel


class Reply(BaseModel):
    answer: str


def _ledger() -> Ledger:
    return Ledger(Limits(tokens=10_000, calls=50, actions=0))


def test_replay_returns_recorded_text_and_refuses_unrecorded_requests(tmp_path):
    path = tmp_path / "tape.json"
    rec = RecordingProvider(MockProvider({"x": [{"answer": "a"}]}), path, {"model": "mock-model"})
    msgs = [Message("user", "hello")]
    ctx = CallContext(role="x")
    got = asyncio.run(
        rec.complete_json(messages=msgs, output_schema=Reply, ctx=ctx, ledger=_ledger())
    )
    assert got.parsed.answer == "a"

    rep = ReplayProvider(load_tape(path))
    assert rep.label == "REPLAY"
    again = asyncio.run(
        rep.complete_json(messages=msgs, output_schema=Reply, ctx=ctx, ledger=_ledger())
    )
    assert again.parsed.answer == "a" and again.provider_label == "REPLAY"
    with pytest.raises(ReplayMismatch):  # each recorded call is consumed once
        asyncio.run(
            rep.complete_json(messages=msgs, output_schema=Reply, ctx=ctx, ledger=_ledger())
        )
    with pytest.raises(ReplayMismatch):  # a different request is never answered from the tape
        asyncio.run(
            ReplayProvider(load_tape(path)).complete_json(
                messages=[Message("user", "other")],
                output_schema=Reply,
                ctx=ctx,
                ledger=_ledger(),
            )
        )


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("OA_NO_LOCAL_ENGINE", "1")
    monkeypatch.delenv("ENGINE_URL", raising=False)
    monkeypatch.delenv("DEMO_MODEL_ENABLED", raising=False)
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        yield c


def test_replay_mode_is_labelled_free_and_only_covers_the_recorded_demonstration(client, tmp_path):
    from open_apprentice.api.app import app

    app.state.tape = None
    assert (
        client.post("/api/teach", json={"mode": "replay"}).status_code == 503
    )  # no tape installed

    path = tmp_path / "tape.json"
    app.state.provider = RecordingProvider(
        Priced({"hypotheses": [_cands()]}),
        path,
        {"model": "mock-model", "recorded_at": "2026-10-12"},
    )
    live = client.post("/api/teach", json={"mode": "nemotron"}).json()
    spent = app.state.spend["usd"]
    assert spent > 0

    app.state.provider = None  # the model is now unavailable; replay must not need it
    app.state.tape = load_tape(path)
    assert client.get("/health/ready").json()["replay"] == {
        "available": True,
        "recorded_at": "2026-10-12",
        "id": "mock-model",
    }
    st = client.post("/api/teach", json={"mode": "replay"}).json()
    assert st["label"]["mode"].startswith("REPLAY")
    assert st["meter"]["label"] == "REPLAY" and st["meter"]["session_usd"] == 0.0
    assert app.state.spend["usd"] == spent  # replay never touches the live budget
    assert st["state"] == "AWAITING_USER"
    assert [o["id"] for o in st["question"]["options"]] == [
        o["id"] for o in live["question"]["options"]
    ]

    bad = client.post("/api/teach", json={"mode": "replay", "demonstration": {"inset_top": 30}})
    assert bad.status_code == 422 and "recorded demonstration" in bad.json()["detail"]
