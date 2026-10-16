def answer(client, sid, req, **override):
    body = {
        "request_id": req["request_id"],
        "intent_revision": req["intent_revision"],
        **req["approve_all_answer"],
    }
    return client.post(f"/api/v2/sessions/{sid}/responses", json={**body, **override})


def test_answer_flow_then_duplicate_then_unknown_request(client, v2, two_docs_session):
    sid, s = two_docs_session
    req = s["outstanding"]
    assert answer(client, sid, req).json() == {"accepted": True, "duplicate": False}
    assert answer(client, sid, req).json() == {"accepted": True, "duplicate": True}
    assert answer(client, sid, req, request_id="q-nope").status_code == 409
    v2.dispatcher.drain()
    state = client.get(f"/api/v2/sessions/{sid}").json()["state"]
    assert state in ("committed", "waiting_for_answer", "preview_ready", "failed")


def test_old_intent_revision_is_refused_and_changes_nothing(client, v2, two_docs_session):
    sid, s = two_docs_session
    req = s["outstanding"]
    r = answer(client, sid, req, intent_revision=req["intent_revision"] - 1)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_OUTSTANDING"
    assert (
        client.get(f"/api/v2/sessions/{sid}").json()["manifest_revision"] == s["manifest_revision"]
    )


def test_invalid_answer_shape_is_refused(client, v2, two_docs_session):
    sid, s = two_docs_session
    r = answer(client, sid, s["outstanding"], kind="choose", selected="Z", per_item=[])
    assert r.status_code == 409


def test_cancel_is_terminal(client, v2, two_docs_session):
    sid, _ = two_docs_session
    assert client.post(f"/api/v2/sessions/{sid}/cancel").json() == {"cancelled": True}
    v2.dispatcher.drain()
    s = client.get(f"/api/v2/sessions/{sid}").json()
    assert s["state"] == "cancelled" and s["outstanding"] is None


def test_answering_through_preview_commits_and_activates(client, v2, two_docs_session):
    sid, s = two_docs_session
    for _ in range(6):
        if s["state"] in ("committed", "failed", "cancelled"):
            break
        assert answer(client, sid, s["outstanding"]).status_code == 200
        v2.dispatcher.drain()
        s = client.get(f"/api/v2/sessions/{sid}").json()
    assert s["state"] == "committed", s
    assert s["result"]["version"] == 1 and s["result"]["activated"]
