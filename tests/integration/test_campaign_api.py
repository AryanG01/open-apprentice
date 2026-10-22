"""Campaign lane over HTTP on the REAL engine (opt-in: OA_ENGINE_TESTS=1)."""

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
        "untagged_short_b": "untagged",
        "untagged_de_long_a": "untagged",
        "untagged_fr_long": "untagged",
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

    def capped(harness, scene, backend="konva"):
        calls.append(1)
        if len(calls) == 1:
            raise campaign_api.HTTPException(
                503, "the graphics engine is busy or unavailable; try again shortly"
            )
        return real(harness, scene, backend)

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

    def second_refused(harness, scene, backend="konva"):
        calls.append(1)
        if len(calls) == 2:
            raise campaign_api.HTTPException(
                503, "the graphics engine is busy or unavailable; try again shortly"
            )
        return real(harness, scene, backend)

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


def test_runs_and_answers_on_fabric(client):
    wid = _workspace(client)["workspace_id"]
    r = client.post(
        f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": "short_a", "backend": "fabric"}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "ready" and out["backend"] == "fabric"
    _passed(out)
    q = client.post(
        f"/api/campaign/workspaces/{wid}/runs",
        json={"fixture_id": "de_long_a", "backend": "fabric"},
    ).json()
    assert q["status"] == "question" and q["backend"] == "fabric"
    a = _answer(client, wid, q["run_id"], SPLIT)
    assert a["status"] == "applied" and a["backend"] == "fabric"
    _passed(a)
    assert _engine_sessions(client) == 0


def test_an_unknown_backend_is_refused(client):
    wid = _workspace(client)["workspace_id"]
    r = client.post(
        f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": "short_a", "backend": "svg"}
    )
    assert r.status_code == 422


# ---- Plan 9E: Nemotron role proposals, explanations and procedures (mock provider) ----
def _payload(messages):
    import json as _json

    return _json.loads(messages[-1].content)


def _mock(roles=None, explain_ok=True, procedure=None):
    from open_apprentice.campaign.explain import template_explanation
    from open_apprentice.providers.mock import MockProvider

    fns = {
        "campaign_explain": lambda m: {
            "text": template_explanation(_payload(m)) if explain_ok else "It needs 999 px."
        }
    }
    if roles is not None:
        fns["campaign_roles"] = lambda m: {"roles": roles}
    if procedure is not None:
        fns["campaign_procedure"] = lambda m: {
            "candidates": [{"program": procedure, "summary": "s"}]
        }
    return MockProvider({}, functions=fns)


def _opaque_truth(fid, src):
    """The authored roles keyed by the opaque ids the model is shown (what a correct model would answer)."""
    from open_apprentice.campaign.fixtures import load_fixture
    from open_apprentice.campaign.roles import opaque_ids

    ids = opaque_ids(load_fixture(fid)["scene"], "banner")
    return {ids[k]: v for k, v in _truth(src).items()}


def _truth(src):
    from open_apprentice.campaign.fixtures import load_fixture

    return {n["id"]: n["role"] for n in load_fixture(src)["scene"]["nodes"] if n.get("role")}


def test_an_untagged_banner_needs_confirmed_roles(client):
    client.app.state.provider = _mock(roles=_opaque_truth("untagged_short_b", "short_b"))
    wid = _workspace(client)["workspace_id"]
    r = client.post(f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": "untagged_short_b"})
    assert r.status_code == 422 and "roles" in r.json()["detail"]
    p = client.post(
        f"/api/campaign/workspaces/{wid}/roles", json={"fixture_id": "untagged_short_b"}
    ).json()
    assert (
        p["origin"] == "model"
        and p["mapping"] == _truth("short_b")
        and p["model"] == "on"
        and len(p["candidates"]) == 7
    )
    bad = dict(p["mapping"])
    bad[next(k for k, v in bad.items() if v == "price")] = "headline"
    assert (
        client.post(
            f"/api/campaign/workspaces/{wid}/runs",
            json={"fixture_id": "untagged_short_b", "roles": bad},
        ).status_code
        == 422
    )
    out = _run_with(client, wid, {"fixture_id": "untagged_short_b", "roles": p["mapping"]})
    assert out["status"] == "ready" and out["provenance"]["roles_origin"] == "owner"
    _passed(out)


def _run_with(c, wid, body):
    r = c.post(f"/api/campaign/workspaces/{wid}/runs", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_question_carries_a_checked_explanation(client):
    client.app.state.provider = _mock()
    wid = _workspace(client)["workspace_id"]
    q = _run(client, wid, "de_long_b")
    assert q["explanation"]["origin"] == "model" and "headline" in q["explanation"]["text"]
    client.app.state.provider = _mock(explain_ok=False)
    q = _run(client, wid, "de_long_a")
    assert q["explanation"]["origin"] == "template" and q["explanation"]["problems"]


def test_an_accepted_model_procedure_is_used_by_later_runs(client, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_MODEL_PROCEDURES", "1")
    from open_apprentice.campaign.procedures import APPLY_PLAN

    client.app.state.provider = _mock(procedure=APPLY_PLAN)
    wid = _workspace(client)["workspace_id"]
    r = client.post(f"/api/campaign/workspaces/{wid}/procedures", json={"backend": "fabric"})
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] and r.json()["origin"] == "model"
    assert _engine_sessions(client) == 0
    out = _run_with(client, wid, {"fixture_id": "short_a", "backend": "fabric"})
    assert out["provenance"]["procedure_origin"] == "model"
    _passed(out)


def test_model_mode_off_uses_every_baseline(client):
    client.app.state.provider = None
    wid = _workspace(client)["workspace_id"]
    p = client.post(
        f"/api/campaign/workspaces/{wid}/roles", json={"fixture_id": "untagged_fr_long"}
    ).json()
    assert p["origin"] == "heuristic" and p["model"] == "off"
    assert _run(client, wid, "de_long_a")["explanation"]["origin"] == "template"
    proc = client.post(
        f"/api/campaign/workspaces/{wid}/procedures", json={"backend": "konva"}
    ).json()
    assert proc["origin"] == "reference" and not proc["accepted"]


def test_a_provider_out_of_budget_degrades_to_baselines(client):
    from open_apprentice.budget import BudgetExhausted
    from open_apprentice.providers.mock import MockProvider

    class Broke(MockProvider):
        async def _call(self, messages, *, max_tokens, ctx):
            raise BudgetExhausted("usd", "cap")

    client.app.state.provider = Broke({})
    wid = _workspace(client)["workspace_id"]
    p = client.post(
        f"/api/campaign/workspaces/{wid}/roles", json={"fixture_id": "untagged_short_b"}
    )
    assert p.status_code == 200 and p.json()["origin"] == "heuristic" and p.json()["problems"]
    assert _run(client, wid, "de_long_b")["explanation"]["origin"] == "template"


# ---- Plan 9E final review fixes ----
def test_the_procedure_check_never_raises_on_an_engine_failure(engine_url, monkeypatch):
    from open_apprentice.campaign.procedures import APPLY_PLAN
    from open_apprentice.evaluation import campaign_procedure_check as cpc

    def broken(self, *a, **k):
        raise httpx.ConnectError("engine went away")

    monkeypatch.setattr(cpc.EvaluatorHarness, "open_session", broken)
    r = cpc.check_procedure(APPLY_PLAN, "konva", engine_url, TOKEN)
    assert not r.passed and all("engine went away" in c["error"] for c in r.cases)


def test_a_server_out_of_model_budget_says_so_on_procedures(client, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_MODEL_PROCEDURES", "1")
    from open_apprentice.campaign.procedures import APPLY_PLAN

    client.app.state.provider = _mock(procedure=APPLY_PLAN)
    client.app.state.spend["usd"] = 1e9
    wid = _workspace(client)["workspace_id"]
    p = client.post(f"/api/campaign/workspaces/{wid}/procedures", json={"backend": "konva"}).json()
    assert p["origin"] == "reference" and any("budget" in n for n in p["notes"])


def test_an_accepted_procedure_is_reused_by_every_workspace_without_new_calls(client, monkeypatch):
    monkeypatch.setenv("CAMPAIGN_MODEL_PROCEDURES", "1")
    from open_apprentice.campaign.procedures import APPLY_PLAN

    provider = _mock(procedure=APPLY_PLAN)
    client.app.state.provider = provider
    a = _workspace(client)["workspace_id"]
    assert client.post(
        f"/api/campaign/workspaces/{a}/procedures", json={"backend": "konva"}
    ).json()["accepted"]
    calls = len(provider.calls)
    b = _workspace(client)["workspace_id"]
    p = client.post(f"/api/campaign/workspaces/{b}/procedures", json={"backend": "konva"}).json()
    assert p["accepted"] and p.get("cached") is True and len(provider.calls) == calls


def test_model_use_per_address_is_scarce_and_degrades_to_baselines(client):
    client.app.state.provider = _mock(roles=_opaque_truth("untagged_short_b", "short_b"))
    wid = _workspace(client)["workspace_id"]
    origins = [
        client.post(
            f"/api/campaign/workspaces/{wid}/roles", json={"fixture_id": "untagged_short_b"}
        ).json()["origin"]
        for _ in range(8)
    ]
    assert origins[0] == "model" and origins[-1] == "heuristic"


def test_a_model_procedure_that_fails_on_a_banner_falls_back_to_the_reference(client):
    client.app.state.provider = None
    wid = _workspace(client)["workspace_id"]
    bad = [{"op": "call", "tool": "move_node", "args": {"node_id": "nope", "x": 0, "y": 0}}]
    client.app.state.campaign[wid].procedures["konva"] = (bad, "model")
    out = _run(client, wid, "short_a")
    assert out["status"] == "ready" and out["provenance"]["procedure_origin"] == "reference"
    assert "procedure_fallback" in out["provenance"]
    _passed(out)


def test_model_written_procedures_are_off_unless_the_operator_turns_them_on(client):
    from open_apprentice.campaign.procedures import APPLY_PLAN

    provider = _mock(procedure=APPLY_PLAN)
    client.app.state.provider = provider
    wid = _workspace(client)["workspace_id"]
    p = client.post(f"/api/campaign/workspaces/{wid}/procedures", json={"backend": "konva"}).json()
    assert p["origin"] == "reference" and not p["accepted"] and any("off" in n for n in p["notes"])
    assert provider.calls == []  # nothing was spent


def test_model_calls_fit_the_production_completion_floor(client):
    """Production reserves NEBIUS_COMPLETION_CAP=32000 tokens per call: a workspace must still be able to make calls."""
    provider = _mock(roles=_opaque_truth("untagged_short_b", "short_b"))
    provider.completion_floor = 32_000
    client.app.state.provider = provider
    wid = _workspace(client)["workspace_id"]
    p = client.post(
        f"/api/campaign/workspaces/{wid}/roles", json={"fixture_id": "untagged_short_b"}
    ).json()
    assert p["origin"] == "model", p["problems"]
    q = _run(client, wid, "de_long_a")
    assert q["explanation"]["origin"] == "model", q["explanation"]["problems"]


def test_the_owner_role_table_is_keyed_like_the_mapping(client):
    """The owner edits the mapping row by row: every row must name a layer the mapping uses, while still showing the
    opaque label the model saw (a table keyed by L1..Ln showed every role as the first option)."""
    client.app.state.provider = _mock(roles=_opaque_truth("untagged_short_b", "short_b"))
    wid = _workspace(client)["workspace_id"]
    p = client.post(
        f"/api/campaign/workspaces/{wid}/roles", json={"fixture_id": "untagged_short_b"}
    ).json()
    assert {c["id"] for c in p["candidates"]} == set(p["mapping"])
    assert sorted(c["label"] for c in p["candidates"]) == [f"L{k}" for k in range(1, 8)]
