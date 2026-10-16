from open_apprentice.teaching.events import SessionLog
from tests.unit.api_v2.conftest import import_and_confirm

RIGHT_12 = {
    "l1": ["152", "58"],
    "l2": ["412", "58"],
}  # fake render: label box = geometry + (2, 3), 30x14


def start(client, v2, doc_bytes, boxes, live=False, key="k1", batch=None):
    ref = import_and_confirm(client, v2, doc_bytes)
    refs = [ref] + ([import_and_confirm(client, v2, batch, "b.drawio")] if batch else [])
    scene_hash = client.get(f"/api/v2/documents/{ref['doc_id']}").json()["pages"][0]["scene_hash"]
    body = {
        "documents": refs,
        "demonstrations": [{"document_ref": 0, "before_scene_hash": scene_hash, "boxes": boxes}],
        "live": live,
        "idempotency_key": key,
    }
    return client.post("/api/v2/sessions", json=body)


def test_session_runs_and_reports_state_provenance_and_spend(client, v2, doc_bytes, batch_bytes):
    r = start(client, v2, doc_bytes, RIGHT_12, batch=batch_bytes)
    assert r.status_code == 202 and r.json()["status_url"].endswith(r.json()["session_id"])
    sid = r.json()["session_id"]
    v2.dispatcher.drain()
    s = client.get(f"/api/v2/sessions/{sid}").json()
    assert s["state"] in ("waiting_for_answer", "preview_ready", "committed"), s
    assert s["provenance"] == {"model": "Fixture", "teacher": "You"}
    assert set(s["spend"]) == {"recorded", "reserved", "uncertain"}
    assert s["budgets"]["attempts_used"] >= 1 and s["manifest_revision"] >= 1


def test_same_idempotency_key_returns_the_same_session(client, v2, doc_bytes, batch_bytes):
    ref = import_and_confirm(client, v2, doc_bytes)
    bref = import_and_confirm(client, v2, batch_bytes, "b.drawio")
    sh = client.get(f"/api/v2/documents/{ref['doc_id']}").json()["pages"][0]["scene_hash"]
    body = {"documents": [ref, bref], "demonstrations": [{"document_ref": 0, "before_scene_hash": sh, "boxes": RIGHT_12}],
            "live": False, "idempotency_key": "same"}  # fmt: skip
    a = client.post("/api/v2/sessions", json=body).json()
    b = client.post("/api/v2/sessions", json=body).json()
    assert a["session_id"] == b["session_id"]


def test_session_without_a_document_to_preview_is_refused(client, v2, doc_bytes):
    r = start(client, v2, doc_bytes, RIGHT_12)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NEED_BATCH"


def test_stale_demonstration_scene_is_refused(client, v2, doc_bytes):
    ref = import_and_confirm(client, v2, doc_bytes)
    body = {
        "documents": [ref],
        "demonstrations": [{"document_ref": 0, "before_scene_hash": "0" * 64, "boxes": {}}],
        "live": False,
        "idempotency_key": "s",
    }
    r = client.post("/api/v2/sessions", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE"


def test_live_requested_when_unavailable_is_refused_with_spec_wording(
    client, v2, doc_bytes, batch_bytes
):
    r = start(client, v2, doc_bytes, {"l1": ["152", "58"]}, live=True, batch=batch_bytes)
    assert r.status_code == 409
    assert (
        r.json()["error"]["message"] == "Live inference is unavailable. Open the recorded example."
    )


def test_concurrent_advances_keep_one_chain(client, v2, doc_bytes, batch_bytes):
    from open_apprentice.api.v2.tasks import Job

    sid = start(client, v2, doc_bytes, RIGHT_12, batch=batch_bytes).json()["session_id"]
    for _ in range(5):
        v2.dispatcher.submit(Job("advance", sid, {"sid": sid}))
    v2.dispatcher.drain()
    evs = SessionLog(v2.store, sid).events()
    assert [e.seq for e in evs] == list(range(1, len(evs) + 1))
    assert not v2.dispatcher.errors


def test_demonstration_of_an_unmovable_cell_is_refused(client, v2, doc_bytes, batch_bytes):
    r = start(client, v2, doc_bytes, {"n1": ["0", "0"]}, batch=batch_bytes)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_MOVABLE"
