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
