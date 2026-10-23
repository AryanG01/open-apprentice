"""Teaching API state machine WITHOUT the engine (no Chromium needed)."""

import json

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
    from open_apprentice.providers.base import TruncatedOutput
    from open_apprentice.providers.mock import MockProvider

    class Failing(MockProvider):  # every paid attempt is counted even when the model call fails
        async def _call(self, messages, *, max_tokens, ctx):
            raise TruncatedOutput("x")

    app.state.provider = Failing({})
    app.state.rate.clear()
    limit = teach.RATE_LIMITS["nemotron"]
    codes = [
        client.post("/api/teach", json={"mode": "nemotron"}).status_code for _ in range(limit + 2)
    ]
    assert (
        codes[:limit] == [200] * limit
    )  # a failing model degrades to search-only, but every paid attempt is still counted
    assert codes[-1] == 429 and codes[-2] == 429
    assert client.post("/api/teach").status_code == 200


def test_security_headers_are_set(client):
    h = client.get("/health/live").headers
    assert (
        h["x-content-type-options"] == "nosniff"
        and h["x-frame-options"] == "DENY"
        and "frame-ancestors 'none'" in h["content-security-policy"]
    )


def test_a_visitor_demonstration_is_used_exactly_as_placed(client):
    st = client.post(
        "/api/teach",
        json={"demonstration": {"width": 200, "height": 100, "inset_right": 20, "inset_top": 20}},
    ).json()
    after = {b["id"]: b for b in st["demonstration"]["canvases"][1]["boxes"]}
    # card at (100, 100) 200 wide: badge 20 wide, 20 px from the right edge and 20 px from the top
    assert (after["badge"]["x"], after["badge"]["y"]) == (100 + 200 - 20 - 20, 100 + 20)
    assert st["state"] in ("AWAITING_USER", "INTENT_READY")


def test_a_placement_no_rule_can_express_ends_unresolved_honestly_not_forced(client):
    st = client.post(
        "/api/teach",
        json={"demonstration": {"width": 150, "height": 80, "inset_right": 5, "inset_top": 40}},
    ).json()
    assert (
        st["state"] == "UNRESOLVED"
        and "no proposed rule fits" in st["note"]
        and "concept" not in st
    )


@pytest.mark.parametrize("bad", [{"width": 5}, {"inset_right": 9999}, {"height": 1000}])
def test_demonstration_values_are_range_checked(client, bad):
    assert client.post("/api/teach", json={"demonstration": bad}).status_code == 422


def test_rate_limit_keys_on_the_address_cloud_run_appended_not_a_spoofed_prefix(monkeypatch):
    """Production runs uvicorn with FORWARDED_ALLOW_IPS=*, which makes request.client the LEFTMOST X-Forwarded-For entry:
    whatever the visitor sent. Cloud Run appends the real address, so the limit must key on the rightmost one.
    """
    monkeypatch.setenv("OA_NO_LOCAL_ENGINE", "1")
    monkeypatch.delenv("ENGINE_URL", raising=False)
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    from open_apprentice.api import teach
    from open_apprentice.api.app import app
    from open_apprentice.providers.base import TruncatedOutput
    from open_apprentice.providers.mock import MockProvider

    class Failing(MockProvider):
        async def _call(self, messages, *, max_tokens, ctx):
            raise TruncatedOutput("x")

    with TestClient(ProxyHeadersMiddleware(app, trusted_hosts="*")) as c:
        app.state.provider = Failing({})
        app.state.rate.clear()
        limit = teach.RATE_LIMITS["nemotron"]
        codes = [
            c.post(
                "/api/teach",
                json={"mode": "nemotron"},
                headers={"x-forwarded-for": f"10.9.9.{i}, 203.0.113.7"},
            ).status_code
            for i in range(limit + 1)
        ]
        assert codes[-1] == 429
        other = c.post(
            "/api/teach", json={"mode": "nemotron"}, headers={"x-forwarded-for": "203.0.113.8"}
        )
        assert other.status_code == 200


WITNESS_STATUSES = {"witness_found", "no_witness_in_model", "incomplete", "timeout", "unsupported"}


def test_the_question_shows_its_work_without_revealing_which_rule_gives_which_option(client):
    st = client.post("/api/teach").json()
    r = st["reasoning"]
    assert r["candidate_count"] >= 2
    sel = r["selection"]
    assert sel["source"] == st["question"]["source"]
    assert len(sel["split"]) >= 2 and sum(sel["split"]) <= r["candidate_count"]
    assert sel["split"] == sorted(
        sel["split"], reverse=True
    )  # sizes only, not tied to option letters
    assert sel["entropy_bits"] > 0 and sel["scenes_considered"] >= 1
    for w in sel["witness_searches"]:
        assert w["status"] in WITNESS_STATUSES and w["elapsed_ms"] >= 0
        assert "rule" not in json.dumps(w).lower()
    assert r["solver"]["max_calls"] >= r["solver"]["calls"] >= len(sel["witness_searches"])
    assert "rule_text" not in json.dumps(r)


def test_a_settled_session_reports_the_final_solver_check(client):
    sid, st = _teach_to_ready(client)
    assert st["state"] in ("INTENT_READY", "UNRESOLVED")
    settle = st["reasoning"][
        "settle"
    ]  # None when the answers left one candidate and no final check was needed
    assert settle is None or settle["status"] in WITNESS_STATUSES
    assert st["reasoning"]["selection"] is None  # no open question
