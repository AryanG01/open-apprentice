from tests.unit.api_v2.conftest import import_and_confirm


def test_apply_publishes_and_blocks_per_document(
    client, v2, committed_skill, fresh_bytes, crowded_bytes
):
    ok = import_and_confirm(client, v2, fresh_bytes, "fresh.drawio")
    bad = import_and_confirm(client, v2, crowded_bytes, "crowded.drawio")
    r = client.post(
        f"/api/v2/skills/{committed_skill}/versions/1/apply",
        json={"documents": [ok, bad], "idempotency_key": "a1"},
    )
    assert r.status_code == 202, r.text
    v2.dispatcher.drain()
    run = client.get(f"/api/v2/runs/{r.json()['run_id']}").json()
    res = run["results"]
    assert run["status"] == "done" and run["provenance"] == {"model": "Fixture", "teacher": "You", "policy": "A"}
    assert res[f"{ok['doc_id']}:{ok['page_id']}"]["status"] == "published", res
    blocked = res[f"{bad['doc_id']}:{bad['page_id']}"]
    assert blocked["status"] == "blocked" and blocked["reasons"], blocked
    q = {"doc_id": ok["doc_id"], "page_id": ok["page_id"]}
    exp = client.get(f"/api/v2/runs/{run['run_id']}/export", params={**q, "format": "drawio"})
    assert exp.status_code == 200 and exp.content.startswith(b"<mxfile")
    rec = client.get(
        f"/api/v2/runs/{run['run_id']}/export", params={**q, "format": "receipt"}
    ).json()
    assert {"conformance", "preservation", "layout", "intent"} <= set(rec)
    svg = client.get(f"/api/v2/runs/{run['run_id']}/export", params={**q, "format": "svg"})
    assert svg.status_code == 409  # the fake renderer cannot export SVG
    nothing = client.get(
        f"/api/v2/runs/{run['run_id']}/export",
        params={"doc_id": bad["doc_id"], "page_id": bad["page_id"], "format": "drawio"},
    )
    assert nothing.status_code == 409  # blocked documents publish nothing


def test_apply_is_idempotent_and_cancellable(client, v2, committed_skill, fresh_bytes):
    ok = import_and_confirm(client, v2, fresh_bytes, "fresh.drawio")
    url = f"/api/v2/skills/{committed_skill}/versions/1/apply"
    a = client.post(url, json={"documents": [ok], "idempotency_key": "same"}).json()
    b = client.post(url, json={"documents": [ok], "idempotency_key": "same"}).json()
    assert a["run_id"] == b["run_id"]
    v2.dispatcher.drain()
    assert client.post(f"/api/v2/runs/{a['run_id']}/cancel").status_code == 200


def test_unknown_version_is_refused(client, v2, committed_skill, fresh_bytes):
    ok = import_and_confirm(client, v2, fresh_bytes, "fresh.drawio")
    r = client.post(
        f"/api/v2/skills/{committed_skill}/versions/9/apply",
        json={"documents": [ok], "idempotency_key": "v9"},
    )
    assert r.status_code == 404


def test_published_documents_export_their_rendered_after_image(
    client, v2, committed_skill, fresh_bytes, crowded_bytes
):
    ok = import_and_confirm(client, v2, fresh_bytes, "fresh.drawio")
    bad = import_and_confirm(client, v2, crowded_bytes, "crowded.drawio")
    r = client.post(
        f"/api/v2/skills/{committed_skill}/versions/1/apply",
        json={"documents": [ok, bad], "idempotency_key": "png1"},
    )
    v2.dispatcher.drain()
    rid = r.json()["run_id"]
    png = client.get(
        f"/api/v2/runs/{rid}/export",
        params={"doc_id": ok["doc_id"], "page_id": ok["page_id"], "format": "png"},
    )
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert png.content.startswith(b"\x89PNG")
    blocked = client.get(
        f"/api/v2/runs/{rid}/export",
        params={"doc_id": bad["doc_id"], "page_id": bad["page_id"], "format": "png"},
    )
    assert blocked.status_code == 409
