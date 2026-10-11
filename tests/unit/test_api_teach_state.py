"""Teaching API state machine WITHOUT the engine (no Chromium needed)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("OA_NO_LOCAL_ENGINE", "1")
    monkeypatch.delenv("ENGINE_URL", raising=False)
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        yield c


def _teach_to_ready(client):
    st = client.post("/api/teach").json()
    sid = st["id"]
    for _ in range(3):
        if st["state"] != "AWAITING_USER":
            break
        q = st["question"]
        st = client.post(
            f"/api/teach/{sid}/answer",
            json={
                "query_id": q["query_id"],
                "answer": q["options"][0]["id"],
                "candidate_set_hash": q["candidate_set_hash"],
            },
        ).json()
    return sid, st


def test_start_asks_a_real_question_with_distinct_pictures_and_labels_the_mode(client):
    st = client.post("/api/teach").json()
    assert st["state"] == "AWAITING_USER" and st["label"]["mode"] == "LIVE ENGINE, NO MODEL"
    opts = st["question"]["options"]
    assert len(opts) >= 2
    badge_x = {o["id"]: next(b for b in o["boxes"] if b["role"] == "badge")["x"] for o in opts}
    assert len(set(badge_x.values())) == len(
        opts
    ), "every option must be a visibly different outcome"
    assert [c["label"] for c in st["demonstration"]["canvases"]] == ["Before", "Your demonstration"]


def test_answering_seals_a_concept_and_ledger_chain_verifies(client):
    sid, st = _teach_to_ready(client)
    assert st["state"] == "INTENT_READY" and st["concept"]["ledger_chain_verified"] is True
    assert len(st["concept"]["sealed_hash"]) == 64 and st["concept"]["answer_source"] == "you"
    assert (
        client.get(f"/api/teach/{sid}").json()["concept"]["sealed_hash"]
        == st["concept"]["sealed_hash"]
    )


def test_stale_or_wrong_answers_are_rejected_not_applied(client):
    st = client.post("/api/teach").json()
    q = st["question"]
    bad = client.post(
        f"/api/teach/{st['id']}/answer",
        json={"query_id": "nope", "answer": "A", "candidate_set_hash": q["candidate_set_hash"]},
    )
    assert bad.status_code == 409
    stale = client.post(
        f"/api/teach/{st['id']}/answer",
        json={"query_id": q["query_id"], "answer": "A", "candidate_set_hash": "0" * 64},
    )
    assert stale.status_code == 409
    assert (
        client.post(
            f"/api/teach/{st['id']}/answer",
            json={
                "query_id": q["query_id"],
                "answer": "Z",
                "candidate_set_hash": q["candidate_set_hash"],
            },
        ).status_code
        == 422
    )
    assert client.get(f"/api/teach/{st['id']}").json()["queries_asked"] == 0


def test_neither_is_not_silently_resolved(client):
    st = client.post("/api/teach").json()
    q = st["question"]
    out = client.post(
        f"/api/teach/{st['id']}/answer",
        json={
            "query_id": q["query_id"],
            "answer": "neither",
            "candidate_set_hash": q["candidate_set_hash"],
        },
    ).json()
    assert (
        out["state"] == "AWAITING_USER"
        and out["correction"]["supported"] is False
        and "concept" not in out
    )


def test_run_before_teaching_is_refused_and_without_engine_is_503(client):
    st = client.post("/api/teach").json()
    assert client.post(f"/api/teach/{st['id']}/run", json={"width": 300}).status_code == 409
    sid, _ = _teach_to_ready(client)
    assert client.post(f"/api/teach/{sid}/run", json={"width": 300}).status_code == 503
    assert client.post(f"/api/teach/{sid}/run", json={"width": 5}).status_code == 422
    assert (
        client.post(
            f"/api/teach/{sid}/run", json={"width": 300, "backend": "konva", "tool_change": True}
        ).status_code
        == 422
    )
    assert client.get("/api/teach/doesnotexist").status_code == 404


def test_session_cap_evicts_the_oldest(client):
    from open_apprentice.api import teach

    first = client.post("/api/teach").json()["id"]
    for _ in range(teach.MAX_SESSIONS):
        client.post("/api/teach")
    assert client.get(f"/api/teach/{first}").status_code == 404


def test_paid_mode_is_rate_limited_per_client_and_free_mode_is_not_starved(client):
    from open_apprentice.api import teach
    from open_apprentice.api.app import app
    from open_apprentice.providers.mock import MockProvider

    app.state.provider = MockProvider(
        {"hypotheses": [{"candidates": [{"summary": "x", "rule": []}]}] * 20}
    )
    app.state.rate.clear()
    codes = [
        client.post("/api/teach", json={"mode": "nemotron"}).status_code
        for _ in range(teach.RATE_LIMITS["nemotron"] + 2)
    ]
    assert codes[: teach.RATE_LIMITS["nemotron"]] == [502] * teach.RATE_LIMITS["nemotron"]
    assert codes[-1] == 429 and codes[-2] == 429
    assert client.post("/api/teach").status_code == 200


def test_security_headers_are_set(client):
    h = client.get("/health/live").headers
    assert (
        h["x-content-type-options"] == "nosniff"
        and h["x-frame-options"] == "DENY"
        and "frame-ancestors 'none'" in h["content-security-policy"]
    )
