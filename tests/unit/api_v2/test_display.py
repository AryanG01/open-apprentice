"""Readable names and colours for the interface: shown to the person, never part of the teaching scene."""

from open_apprentice.drawio.parse import plain_text
from tests.unit.api_v2.conftest import import_and_confirm, upload
from tests.unit.drawio.fixtures import drawio, label, model, node


def test_plain_text_strips_label_html_and_entities():
    assert plain_text("<b>GPU</b> pool<br>8x &amp; more") == "GPU pool 8x & more"
    assert plain_text("  Plain  ") == "Plain"


def _doc():
    return drawio(
        model(
            [
                node("n1", 40, 40, 100, 50, value="Train"),
                label("l1", 50, 100, value="&lt;b&gt;8x H100&lt;/b&gt;"),
            ]
        )
    )


def test_document_pages_carry_display_names_and_colours(client, v2):
    doc = upload(client, _doc()).json()
    v2.dispatcher.drain()
    page = client.get(f"/api/v2/documents/{doc['doc_id']}").json()["pages"][0]
    assert page["display"]["n1"]["text"] == "Train"
    assert page["display"]["l1"]["text"] == "8x H100"
    assert set(page["display"]["n1"]) == {"text", "fill", "stroke", "font_color"}


def test_scene_view_has_display_but_the_teaching_scene_does_not(client, v2):
    ref = import_and_confirm(client, v2, _doc())
    view = client.get(
        f"/api/v2/documents/{ref['doc_id']}/pages/{ref['page_id']}/scene",
        params={"mapping_hash": ref["mapping_hash"]},
    ).json()
    assert view["display"]["l1"]["text"] == "8x H100"
    assert all("text" not in o for o in view["objects"])
