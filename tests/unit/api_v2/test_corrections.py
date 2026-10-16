import pytest

from tests.unit.api_v2.conftest import answer_until_done, import_and_confirm

# fresh document: node p1 (100,150,90,40); label q1's measured box is 30x14. The committed rule puts labels right of their node,
# gap 12, centred: q1 at (202, 163).


@pytest.fixture
def applied(client, v2, committed_skill, fresh_bytes, batch_bytes):
    ok = import_and_confirm(client, v2, fresh_bytes, "fresh.drawio")
    other = import_and_confirm(client, v2, batch_bytes, "other.drawio")
    run = client.post(
        f"/api/v2/skills/{committed_skill}/versions/1/apply",
        json={"documents": [ok, other], "idempotency_key": "ap"},
    ).json()
    v2.dispatcher.drain()
    skill = client.get(f"/api/v2/skills/{committed_skill}").json()
    return committed_skill, run["run_id"], ok, skill["active"]


def correct(client, skill_id, run_id, ref, active, boxes, key):
    body = {
        "base_version": active["version"],
        "base_pointer_generation": active["generation"],
        "run_id": run_id,
        "doc_id": ref["doc_id"],
        "page_id": ref["page_id"],
        "boxes": boxes,
        "mask": list(boxes),
        "full_approval": False,
        "idempotency_key": key,
    }
    return client.post(f"/api/v2/skills/{skill_id}/corrections", json=body)


def test_skill_reports_active_version_and_history(client, v2, applied):
    skill_id, _, _, active = applied
    s = client.get(f"/api/v2/skills/{skill_id}").json()
    assert active["version"] == 1 and s["versions"][0]["version"] == 1 and len(s["history"]) == 1


def test_unexplainable_correction_is_kept_as_an_override(client, v2, applied):
    skill_id, run_id, ref, active = applied
    r = correct(client, skill_id, run_id, ref, active, {"q1": ["202", "165"]}, "c1")
    assert r.status_code == 202, r.text
    v2.dispatcher.drain()
    sid = r.json()["session_id"]
    s = client.get(f"/api/v2/sessions/{sid}").json()
    assert s["kind"] == "correction" and s["state"] == "waiting_for_answer", s
    kinds = {i["kind"] for i in s["outstanding"]["request"]["interpretations"]}
    assert "revise" not in kinds and {"override", "accidental"} <= kinds
    s = answer_until_done(client, v2, sid)
    assert s["state"] == "override", s
    assert client.get(f"/api/v2/skills/{skill_id}").json()["active"]["version"] == 1


def test_explainable_correction_is_reviewed_and_activates_version_two(client, v2, applied):
    skill_id, run_id, ref, active = applied
    sid = correct(client, skill_id, run_id, ref, active, {"q1": ["206", "163"]}, "c2").json()[
        "session_id"
    ]
    v2.dispatcher.drain()
    s = answer_until_done(client, v2, sid, rounds=10)
    assert s["state"] == "activated", s
    skill = client.get(f"/api/v2/skills/{skill_id}").json()
    assert skill["active"]["version"] == 2 and [x["version"] for x in skill["versions"]] == [1, 2]


def test_stale_base_is_refused(client, v2, applied):
    skill_id, run_id, ref, active = applied
    stale = {**active, "generation": active["generation"] + 99}
    r = correct(client, skill_id, run_id, ref, stale, {"q1": ["206", "163"]}, "c3")
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_BASE"


def test_activation_by_compare_and_set(client, v2, applied):
    skill_id, _, _, active = applied
    url = f"/api/v2/skills/{skill_id}/activate"
    bad = client.post(
        url,
        json={
            "version": 1,
            "expected_generation": active["generation"] + 5,
            "idempotency_key": "x1",
        },
    )
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "ACTIVATION_REJECTED"
    ok = client.post(
        url,
        json={"version": 1, "expected_generation": active["generation"], "idempotency_key": "x2"},
    )
    assert (
        ok.status_code == 200
        and client.get(f"/api/v2/skills/{skill_id}").json()["active"]["version"] == 1
    )


def test_cancelling_a_correction_leaves_the_skill_alone(client, v2, applied):
    skill_id, run_id, ref, active = applied
    sid = correct(client, skill_id, run_id, ref, active, {"q1": ["206", "163"]}, "c4").json()[
        "session_id"
    ]
    v2.dispatcher.drain()
    assert client.post(f"/api/v2/sessions/{sid}/cancel").json() == {"cancelled": True}
    v2.dispatcher.drain()
    assert client.get(f"/api/v2/sessions/{sid}").json()["state"] == "cancelled"
    assert client.get(f"/api/v2/skills/{skill_id}").json()["active"]["version"] == 1
