"""Sketch door over HTTP on the REAL engine (opt-in: OA_ENGINE_TESTS=1): wireframe -> read -> confirm -> run."""

import pytest

from open_apprentice.providers.mock import MockProvider
from tests.integration.test_campaign_api import (  # noqa: F401 - `client` is the shared fixture
    _confirm,
    _engine_sessions,
    _gold_layers,
    _vision_reply,
    _workspace,
    client,
)
from tests.pngs import png_url


def _sketch(c, wid, image=None):
    return c.post(
        f"/api/campaign/workspaces/{wid}/sketches", json={"image": image or png_url(1280, 720)}
    )


def _blank(layers):
    """What the model says about a wireframe: boxes only, no legible words, no sizes."""
    return [{**l, "text": "", "font_px": 0, "color": "", "fill": ""} for l in layers]


def test_without_a_vision_model_a_sketch_gets_the_manual_template(client):
    wid = _workspace(client)["workspace_id"]
    client.app.state.vision_provider = None
    out = _sketch(client, wid).json()
    assert out["origin"] == "manual" and out["note"] and len(out["layers"]) == 6
    assert client.app.state.campaign[wid].uploads[out["upload_id"]]["kind"] == "sketch"


@pytest.mark.parametrize("image,needle", [(png_url(640, 360), "1280"), ("nope", "data URL")])
def test_a_sketch_must_be_a_1280_by_720_image(client, image, needle):
    wid = _workspace(client)["workspace_id"]
    r = _sketch(client, wid, image)
    assert r.status_code == 422 and needle in r.json()["detail"]


def test_the_model_reads_the_sketch_and_the_owner_confirms_it_into_a_story_card(client):
    gold = _gold_layers()
    client.app.state.vision_provider = MockProvider(
        {"campaign_sketch": [_vision_reply(_blank(gold))]}
    )
    wid = _workspace(client)["workspace_id"]
    up = _sketch(client, wid).json()
    assert up["origin"] == "model" and up["problems"] == [] and up["model"]
    assert {l["role"]: l["text"] for l in up["layers"]} == {
        l["role"]: "" for l in gold
    }, "empty words are expected from a sketch"
    # confirm still needs words: the owner types them (or pastes them from the page copy)
    words = {l["role"]: l["text"] for l in gold}
    layers = [{**l, "text": words[l["role"]]} for l in up["layers"]]
    got = _confirm(client, wid, up["upload_id"], layers, link=None)
    assert got.status_code == 200, got.text
    banner_id = got.json()["banner_id"]
    assert client.app.state.campaign[wid].uploads == {}
    run = client.post(f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": banner_id}).json()
    assert run["status"] in ("ready", "question"), run
    assert run["provenance"]["source"] == "upload"
    assert _engine_sessions(client) == 0


def test_confirming_a_sketch_without_words_is_refused(client):
    gold = _gold_layers()
    client.app.state.vision_provider = MockProvider(
        {"campaign_sketch": [_vision_reply(_blank(gold))]}
    )
    wid = _workspace(client)["workspace_id"]
    up = _sketch(client, wid).json()
    r = _confirm(client, wid, up["upload_id"], up["layers"])
    assert r.status_code == 422 and "text is empty" in r.json()["detail"]
    assert up["upload_id"] in client.app.state.campaign[wid].uploads  # kept so the owner can fix it
