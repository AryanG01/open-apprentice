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


SHRINK, SPLIT = "builtin_shrink_hero", "builtin_split_two_cards"


def _run(c, wid, fid, status=200):
    r = c.post(f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": fid})
    assert r.status_code == status, r.text
    assert _engine_sessions(c) == 0  # every session was snapshotted and closed
    return r.json()


def _answer(c, wid, rid, choice, expected_version=None, status=200):
    r = c.post(
        f"/api/campaign/workspaces/{wid}/runs/{rid}/answer",
        json={"choice": choice, "expected_version": expected_version},
    )
    assert r.status_code == status, r.text
    assert _engine_sessions(c) == 0
    return r.json()


def _passed(out):
    v = out["result"]["verification"]
    assert v["passed"] and len(v["checks"]) == 15, v
    assert out["result"]["png"].startswith("data:image/png")


def test_runs_questions_answers_and_reuse(client):
    wid = _workspace(client)["workspace_id"]
    out = _run(client, wid, "short_a")
    assert out["status"] == "ready" and out["provenance"]["procedure_origin"] == "reference"
    _passed(out)

    q = _run(client, wid, "de_long_a")
    assert q["status"] == "question" and q["result"] is None
    previews = {p["outcome"]: p for p in q["previews"]}
    assert previews[SHRINK]["fits"] and previews[SPLIT]["fits"]
    assert all(
        p["origin"] == "builtin" and p["png"].startswith("data:image/png") for p in q["previews"]
    )
    a = _answer(client, wid, q["run_id"], SHRINK)
    assert a["status"] == "applied" and a["preference"] == {"outcome": SHRINK, "version": 1}
    _passed(a)
    _answer(client, wid, q["run_id"], SHRINK, status=409)  # answered already

    q = _run(client, wid, "de_long_b")
    previews = {p["outcome"]: p for p in q["previews"]}
    assert q["status"] == "question" and not previews[SHRINK]["fits"] and previews[SPLIT]["fits"]
    _answer(client, wid, q["run_id"], SHRINK, status=409)  # does not fit
    a = _answer(client, wid, q["run_id"], SPLIT, expected_version=1)
    assert a["preference"] == {"outcome": SPLIT, "version": 2}
    _passed(a)

    reuse = _run(client, wid, "de_long_a")
    assert (
        reuse["status"] == "applied"
        and reuse["previews"] == []
        and reuse["preference"]["outcome"] == SPLIT
    )
    _passed(reuse)

    assert _run(client, wid, "fr_long")["status"] == "question"
    broken = _run(client, wid, "missing_role")
    assert broken["status"] == "needs_roles" and any("price" in p for p in broken["problems"])

    prefs = {
        s["locale"]: s
        for s in client.get(f"/api/campaign/workspaces/{wid}/preferences").json()["scopes"]
    }
    assert prefs["de"]["active"] == {"outcome": SPLIT, "version": 2} and [
        h["version"] for h in prefs["de"]["history"]
    ] == [1, 2]
    r = client.post(
        f"/api/campaign/workspaces/{wid}/preferences/rollback",
        json={"locale": "de", "to_version": 1, "expected_version": 2},
    )
    assert r.status_code == 200 and r.json()["active"] == {"outcome": SHRINK, "version": 1}
    stale = client.post(
        f"/api/campaign/workspaces/{wid}/preferences/rollback",
        json={"locale": "de", "to_version": 2, "expected_version": 2},
    )
    assert stale.status_code == 409


def test_an_expired_workspace_cannot_answer(client):
    wid = _workspace(client)["workspace_id"]
    q = _run(client, wid, "de_long_a")
    client.app.state.campaign[wid].touched -= 3600
    r = client.post(
        f"/api/campaign/workspaces/{wid}/runs/{q['run_id']}/answer",
        json={"choice": SHRINK, "expected_version": None},
    )
    assert r.status_code == 404


def test_a_result_without_gold_is_blocked_not_applied(client, monkeypatch):
    import open_apprentice.api.campaign as campaign_api

    monkeypatch.setattr(campaign_api, "_gold", lambda fid, outcome: None)
    wid = _workspace(client)["workspace_id"]
    out = _run(client, wid, "short_a")
    assert out["status"] == "blocked"
    assert "matches_gold" in out["result"]["verification"]["failed"]
    q = _run(client, wid, "de_long_a")
    blocked = _answer(client, wid, q["run_id"], SHRINK)
    assert (
        blocked["status"] == "blocked" and blocked["preference"] is None
    )  # nothing saved for a refused result
    prefs = {
        s["locale"]: s
        for s in client.get(f"/api/campaign/workspaces/{wid}/preferences").json()["scopes"]
    }
    assert prefs["de"]["active"] is None


def test_unknown_banner_is_404(client):
    wid = _workspace(client)["workspace_id"]
    assert (
        client.post(
            f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": "teach_after"}
        ).status_code
        == 404
    )
    assert (
        client.post(f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": "../x"}).status_code
        == 404
    )


def test_an_engine_at_its_session_cap_is_a_503_and_a_retry_works(client, monkeypatch):
    import open_apprentice.api.campaign as campaign_api

    wid = _workspace(client)["workspace_id"]
    real, calls = campaign_api._open, []

    def capped(harness, scene):
        calls.append(1)
        if len(calls) == 1:
            raise campaign_api.HTTPException(
                503, "the graphics engine is busy or unavailable; try again shortly"
            )
        return real(harness, scene)

    monkeypatch.setattr(campaign_api, "_open", capped)
    r = client.post(f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": "short_a"})
    assert r.status_code == 503 and "busy" in r.json()["detail"]
    assert _engine_sessions(client) == 0
    assert _run(client, wid, "short_a")["status"] == "ready"


def test_an_engine_failure_mid_run_is_a_plain_503_and_leaves_no_session(client, monkeypatch):
    from open_apprentice.environments.client import EngineSession

    wid = _workspace(client)["workspace_id"]
    real = EngineSession.call

    def flaky(self, tool, **args):
        if tool == "set_order":
            raise httpx.ConnectError("connection refused by http://engine:8090/sessions/x")
        return real(self, tool, **args)

    monkeypatch.setattr(EngineSession, "call", flaky)
    r = client.post(f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": "short_a"})
    assert r.status_code == 503 and "http" not in r.json()["detail"]
    assert _engine_sessions(client) == 0
    monkeypatch.setattr(EngineSession, "call", real)
    assert _run(client, wid, "short_a")["status"] == "ready"


def test_the_second_session_refused_mid_run_is_a_503_and_leaves_no_session(client, monkeypatch):
    import open_apprentice.api.campaign as campaign_api

    wid = _workspace(client)["workspace_id"]
    real, calls = campaign_api._open, []

    def second_refused(harness, scene):
        calls.append(1)
        if len(calls) == 2:
            raise campaign_api.HTTPException(
                503, "the graphics engine is busy or unavailable; try again shortly"
            )
        return real(harness, scene)

    monkeypatch.setattr(campaign_api, "_open", second_refused)
    r = client.post(f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": "de_long_a"})
    assert r.status_code == 503
    assert _engine_sessions(client) == 0


def test_store_and_verifier_work_never_runs_on_the_event_loop(client, monkeypatch):
    import asyncio

    from open_apprentice.campaign.preferences import PreferenceStore

    on_loop = []

    def watch(fn):
        def wrapper(*a, **k):
            try:
                asyncio.get_running_loop()
                on_loop.append(fn.__name__)
            except RuntimeError:
                pass
            return fn(*a, **k)

        return wrapper

    for name in ("get", "set", "rollback", "history"):
        monkeypatch.setattr(PreferenceStore, name, watch(getattr(PreferenceStore, name)))
    import open_apprentice.api.campaign as campaign_api

    monkeypatch.setattr(campaign_api, "verify_story", watch(campaign_api.verify_story))
    wid = _workspace(client)["workspace_id"]
    q = _run(client, wid, "de_long_a")
    _answer(client, wid, q["run_id"], SHRINK)
    client.get(f"/api/campaign/workspaces/{wid}/preferences")
    _answer(client, wid, _run(client, wid, "de_long_b")["run_id"], SPLIT, expected_version=1)
    client.post(
        f"/api/campaign/workspaces/{wid}/preferences/rollback",
        json={"locale": "de", "to_version": 1, "expected_version": 2},
    )
    assert on_loop == []
