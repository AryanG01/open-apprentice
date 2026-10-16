from fractions import Fraction

from tests.unit.api_v2.conftest import import_and_confirm


def test_scene_route_returns_geometry_and_image_offset(client, v2, doc_bytes):
    ref = import_and_confirm(client, v2, doc_bytes)
    r = client.get(
        f"/api/v2/documents/{ref['doc_id']}/pages/{ref['page_id']}/scene",
        params={"mapping_hash": ref["mapping_hash"]},
    )
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["canvas"] == {"w": "600", "h": "400"} and set(s["image_offset"]) == {"x", "y"}
    l1 = next(o for o in s["objects"] if o["id"] == "l1")
    assert (l1["kind"], l1["x"], l1["y"], l1["w"], l1["h"]) == ("label", "52", "103", "30", "14")
    assert sorted(s["movable"]) == ["l1", "l2"] and len(s["scene_hash"]) == 64


def test_parse_render_reads_translate_and_defaults_to_zero():
    from open_apprentice.drawio.render import parse_render

    base = {"labels": {}, "nodes": {}}
    assert parse_render(base).translate == (0, 0)
    got = parse_render({**base, "translate": {"x": -32, "y": 12.5}}).translate
    assert got == (Fraction(-32), Fraction(25, 2))


def test_draft_reports_the_image_offset(client, v2, doc_bytes):
    ref = import_and_confirm(client, v2, doc_bytes)
    r = client.post(
        f"/api/v2/documents/{ref['doc_id']}/draft",
        json={
            "page_id": ref["page_id"],
            "mapping_hash": ref["mapping_hash"],
            "boxes": {"l1": ["150", "58"]},
        },
    ).json()
    assert set(r["image_offset"]) == {"x", "y"}


def test_item_pngs_and_checks_for_an_open_question(client, v2, two_docs_session):
    sid, s = two_docs_session
    q = s["outstanding"]
    assert q["item_ids"] and set(q["checks"]) == set(q["item_ids"])
    url = f"/api/v2/sessions/{sid}/requests/{q['request_id']}/items/{q['item_ids'][0]}.png"
    png = client.get(url)
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert client.get(url).content == png.content  # cached
    bad = f"/api/v2/sessions/{sid}/requests/{q['request_id']}/items/nope.png"
    assert client.get(bad).status_code == 404


def test_blocked_preview_item_cannot_be_approved(client, v2, doc_bytes):
    from tests.unit.api_v2.conftest import start_session
    from tests.unit.drawio.fixtures import drawio, label, model, node

    # the batch page is narrow: "right of the node, gap 12" pushes its label off the page
    narrow = drawio(model([node("m1", 300, 100, 120, 60), label("k1", 300, 180)], w=440, h=300))
    sid = start_session(client, v2, doc_bytes, narrow, key="narrow")
    s = client.get(f"/api/v2/sessions/{sid}").json()
    q = s["outstanding"]
    assert q and q["request"]["type"] == "ConfirmPreview", s
    blocked = [i for i, c in q["checks"].items() if not c["ok"]]
    assert blocked and "outside the page" in " ".join(q["checks"][blocked[0]]["reasons"])
    body = {
        "request_id": q["request_id"],
        "intent_revision": q["intent_revision"],
        "kind": "items",
        "per_item": [[i, "approve"] for i in q["item_ids"]],
    }
    r = client.post(f"/api/v2/sessions/{sid}/responses", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "BLOCKED_ITEM"
    assert dict(q["approve_all_answer"]["per_item"])[blocked[0]] == "reject"


def test_config_reports_live_availability(client):
    c = client.get("/api/v2/config").json()
    assert c == {"live_available": False, "model": "Fixture", "max_upload_bytes": 2 * 1024 * 1024}
