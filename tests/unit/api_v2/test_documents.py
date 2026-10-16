from tests.unit.api_v2.conftest import upload


def test_import_render_map_confirm(client, v2, doc_bytes):
    r = upload(client, doc_bytes)
    assert r.status_code == 201 and r.cookies.get("oa_owner")
    doc = r.json()
    v2.dispatcher.drain()
    d = client.get(f"/api/v2/documents/{doc['doc_id']}").json()
    page = d["pages"][0]
    assert d["render"] == "done" and page["mapping"]["proposed"] and page["mapping_hash"] is None
    png = client.get(f"/api/v2/documents/{doc['doc_id']}/pages/{page['page_id']}/preview.png")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    m = client.post(
        f"/api/v2/documents/{doc['doc_id']}/mapping",
        json={"page_id": page["page_id"], "labels": {"l1": {"role": "Warning"}}, "confirm": True},
    ).json()
    assert (
        m["confirmed"] and m["labels"]["l1"]["role"] == "warning" and len(m["mapping_hash"]) == 64
    )
    page = client.get(f"/api/v2/documents/{doc['doc_id']}").json()["pages"][0]
    assert page["mapping_hash"] == m["mapping_hash"] and len(page["scene_hash"]) == 64


def test_refused_file_answers_422_with_reason(client):
    r = upload(client, b'<!DOCTYPE x [<!ENTITY a "b">]><mxfile/>')
    assert r.status_code == 422 and "DOCTYPE" in r.json()["error"]["message"]


def test_other_owner_gets_404(client, doc_bytes):
    doc = upload(client, doc_bytes).json()
    client.cookies.clear()
    r = client.get(f"/api/v2/documents/{doc['doc_id']}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_draft_render_returns_png_and_boxes_without_storing(client, v2, doc_bytes):
    doc = upload(client, doc_bytes).json()
    v2.dispatcher.drain()
    pid = doc["pages"][0]["page_id"]
    mh = client.post(
        f"/api/v2/documents/{doc['doc_id']}/mapping",
        json={"page_id": pid, "labels": {}, "confirm": True},
    ).json()["mapping_hash"]
    r = client.post(
        f"/api/v2/documents/{doc['doc_id']}/draft",
        json={"page_id": pid, "mapping_hash": mh, "boxes": {"l1": ["150", "58"]}},
    )
    assert r.status_code == 200 and r.json()["boxes"]["l1"]["x"] == "150" and r.json()["png"]
    d = client.get(f"/api/v2/documents/{doc['doc_id']}").json()
    assert d["pages"][0]["mapping_hash"] == mh  # nothing about the document changed


def test_mapping_before_render_or_with_wrong_page_is_refused(client, doc_bytes):
    doc = upload(client, doc_bytes).json()
    r = client.post(
        f"/api/v2/documents/{doc['doc_id']}/mapping",
        json={"page_id": "nope", "labels": {}, "confirm": True},
    )
    assert r.status_code in (404, 409)


def test_render_failure_is_recorded_with_its_reason(client, v2, doc_bytes):
    from open_apprentice.drawio.parse import DrawioRefused

    def broken(page):
        raise DrawioRefused("the renderer is unavailable (ConnectError)")

    v2.render = broken
    doc = upload(client, doc_bytes).json()
    v2.dispatcher.drain()
    d = client.get(f"/api/v2/documents/{doc['doc_id']}").json()
    assert d["render"] == "failed" and "unavailable" in d["render_error"]
