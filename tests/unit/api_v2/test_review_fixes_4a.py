"""Regression tests for the Plan 4A whole-branch review findings (each failed before its fix)."""

import threading
import time

from open_apprentice.api.v2 import records
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.events import SessionLog
from tests.unit.api_v2.conftest import import_and_confirm


# ---- 1: one bad document ref never hangs a run
def test_bad_document_ref_is_reported_and_the_others_still_run(
    client, v2, committed_skill, fresh_bytes
):
    ok = import_and_confirm(client, v2, fresh_bytes, "fresh.drawio")
    bad = {"doc_id": "0" * 32, "page_id": "x", "mapping_hash": "y"}
    r = client.post(
        f"/api/v2/skills/{committed_skill}/versions/1/apply",
        json={"documents": [bad, "junk", ok], "idempotency_key": "bad"},
    )
    v2.dispatcher.drain()
    run = client.get(f"/api/v2/runs/{r.json()['run_id']}").json()
    assert run["status"] == "done", run
    assert run["results"][f"{ok['doc_id']}:{ok['page_id']}"]["status"] == "published"
    failed = [x for k, x in run["results"].items() if not k.startswith(ok["doc_id"])]
    assert len(failed) == 2 and all(x["status"] == "failed" and x["reasons"] for x in failed)


# ---- 2: no answers after cancel
def test_answer_after_cancel_is_refused_and_changes_nothing(client, v2, two_docs_session):
    sid, s = two_docs_session
    client.post(f"/api/v2/sessions/{sid}/cancel")
    v2.dispatcher.drain()
    before = len(SessionLog(v2.store, sid).events())
    q = s["outstanding"]
    body = {
        "request_id": q["request_id"],
        "intent_revision": q["intent_revision"],
        **q["approve_all_answer"],
    }
    r = client.post(f"/api/v2/sessions/{sid}/responses", json=body)
    assert r.status_code == 409 and len(SessionLog(v2.store, sid).events()) == before


# ---- 3: a correction binds to the version that produced the run
def test_correction_of_a_run_from_an_older_version_is_refused(
    client, v2, committed_skill, fresh_bytes, batch_bytes
):
    from open_apprentice.skills.versions import SkillStore

    ok = import_and_confirm(client, v2, fresh_bytes, "fresh.drawio")
    run = client.post(
        f"/api/v2/skills/{committed_skill}/versions/1/apply",
        json={"documents": [ok], "idempotency_key": "r1"},
    ).json()
    v2.dispatcher.drain()
    skills = SkillStore(v2.store)
    art = dict(skills.version(committed_skill, 1), parent_version=1)
    art["program"] = {**art["program"], "summary": "edited"}
    n = skills.store_version(committed_skill, art)
    _, _, gen = skills.active(committed_skill)
    skills.activate(committed_skill, n, gen, "op", "test")
    active = client.get(f"/api/v2/skills/{committed_skill}").json()["active"]
    body = {"base_version": active["version"], "base_pointer_generation": active["generation"], "run_id": run["run_id"],
            "doc_id": ok["doc_id"], "page_id": ok["page_id"], "boxes": {"q1": ["206", "163"]}, "mask": ["q1"],
            "full_approval": True, "idempotency_key": "old"}  # fmt: skip
    r = client.post(f"/api/v2/skills/{committed_skill}/corrections", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_BASE"


# ---- 4: mock output is never labelled Live
def test_live_mode_with_the_mock_provider_stays_offline(monkeypatch, tmp_path):
    from open_apprentice.api.v2.context import make_v2

    monkeypatch.chdir(tmp_path)  # no developer .env: PROVIDER_MODE defaults to mock
    monkeypatch.setenv("DEMO_MODEL_ENABLED", "1")
    v = make_v2(None)
    try:
        assert v.model == "Fixture" and not v.live_available()
    finally:
        v.dispatcher.close()


# ---- 5: body size limits
def test_oversized_json_body_is_refused(client):
    r = client.post(
        "/api/v2/sessions",
        content=b'{"x":"' + b"a" * 300_000 + b'"}',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413


def test_oversized_upload_is_refused(client):
    r = client.post(
        "/api/v2/documents?name=x",
        content=b"x" * (3 * 1024 * 1024),
        headers={"content-type": "application/octet-stream"},
    )
    assert r.status_code == 413


# ---- 6: concurrent requests with one idempotency key run once
def test_concurrent_idempotent_requests_produce_once(tmp_path):
    s = LocalStore(tmp_path)
    calls, results = [], []

    def produce():
        calls.append(1)
        time.sleep(0.2)
        return {"id": len(calls)}

    def worker():
        results.append(records.idempotent(s, "o", "k", "d", produce))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1 and results == [{"id": 1}] * 5


# ---- 7: the live adapter never reuses a provider across event loops
def test_adapter_uses_a_fresh_provider_per_call():
    import asyncio

    from open_apprentice.providers.mock import MockProvider
    from open_apprentice.providers.teaching_adapter import ProviderProposer

    class LoopBound(MockProvider):
        loop = None

        async def _call(self, messages, *, max_tokens, ctx):
            here = asyncio.get_running_loop()
            if self.loop is not None and self.loop is not here:
                raise RuntimeError(
                    "Event loop is closed"
                )  # what a pooled httpx client does on a new loop
            self.loop = here
            return await super()._call(messages, max_tokens=max_tokens, ctx=ctx)

    made = []

    def factory():
        p = LoopBound({"hypotheses": [{"candidates": []}]})
        made.append(p)
        return p

    proposer = ProviderProposer(factory)
    proposer.propose({"teaching_evidence": []}, "initial", ())
    proposer.propose({"teaching_evidence": []}, "contrastive", ())
    assert len(made) == 2


# ---- 8: owner cookies survive a restart without SESSION_SECRET
def test_generated_secret_is_persisted_in_the_store(monkeypatch):
    from open_apprentice.api.v2.context import make_v2

    monkeypatch.delenv("SESSION_SECRET", raising=False)
    a, b = make_v2(None), make_v2(None)
    try:
        assert a.secret == b.secret and len(a.secret) >= 32
    finally:
        a.dispatcher.close()
        b.dispatcher.close()


# ---- 9: live sessions are rate-limited per client
def test_live_sessions_are_rate_limited_per_client(client, v2, doc_bytes, batch_bytes):
    from tests.unit.api_v2.conftest import RIGHT_12

    v2.live_available = lambda: True
    v2.model = "Live"
    ref = import_and_confirm(client, v2, doc_bytes)
    bref = import_and_confirm(client, v2, batch_bytes, "b.drawio")
    sh = client.get(f"/api/v2/documents/{ref['doc_id']}").json()["pages"][0]["scene_hash"]
    codes = []
    for i in range(5):
        body = {"documents": [ref, bref], "demonstrations": [{"document_ref": 0, "before_scene_hash": sh, "boxes": RIGHT_12}],
                "live": True, "idempotency_key": f"live{i}"}  # fmt: skip
        codes.append(client.post("/api/v2/sessions", json=body).status_code)
    v2.dispatcher.drain()
    assert codes[:3] == [202, 202, 202] and 429 in codes[3:]
