"""Reading a rough wireframe: empty words are expected, everything else is checked like a banner reading."""

import asyncio

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.sketch import DEFAULT_FONT_PX, propose_sketch_layers
from open_apprentice.campaign.vision import Layer, check_layers, manual_template
from open_apprentice.providers.mock import MockProvider
from tests.pngs import png_url

PNG = png_url(1280, 720)
BOXES = {
    "brand_mark": [50, 66, 200, 133],
    "product_image": [62, 211, 450, 900],
    "headline": [500, 220, 950, 470],
    "price": [500, 490, 950, 560],
    "cta": [500, 600, 700, 700],
    "legal": [500, 780, 950, 930],
}


def reply(drop=(), **over):
    layers = [
        {"role": r, "box": b, "text": "", "font_px": 0, "bold": False, "color": "", "fill": ""}
        for r, b in BOXES.items()
        if r not in drop
    ]
    return {"language": "en", "layers": [{**l, **over.get(l["role"], {})} for l in layers]}


def read(script):
    provider = MockProvider({"campaign_sketch": script})
    return (
        asyncio.run(propose_sketch_layers(provider, Ledger(Limits(tokens=100_000, calls=4)), PNG)),
        provider,
    )


def test_empty_words_are_not_a_problem_and_sizes_come_from_the_role():
    p, provider = read([reply()])
    assert p.origin == "model" and p.problems == []
    sizes = {l.role: l.font_px for l in p.layers}
    assert all(sizes[r] == s for r, s in DEFAULT_FONT_PX.items())
    assert (
        provider.calls[0][1][-1].content[-1]["type"] == "image_url"
    )  # the sketch went to the model


def test_a_size_the_model_gave_is_kept():
    p, _ = read([reply(headline={"font_px": 70})])
    assert {l.role: l.font_px for l in p.layers}["headline"] == 70


def test_optional_roles_may_be_absent_but_required_ones_are_named():
    p, _ = read([reply(drop=("price", "cta", "legal"))])
    assert p.problems == []
    p, _ = read([reply(drop=("headline", "brand_mark", "product_image"))])
    for r in ("headline", "brand mark", "product image"):
        assert any(r.replace(" ", "_") in x and "missing" in x for x in p.problems), p.problems


def test_other_problems_still_count():
    p, _ = read([reply(headline={"box": [0, 150, 1000, 470]}, price={"text": "free"})])
    assert any("price" in x for x in p.problems)
    assert any("overlaps" in x for x in p.problems)


def test_fallbacks_match_the_banner_reader():
    p = asyncio.run(propose_sketch_layers(None, None, PNG))
    assert (
        p.origin == "manual"
        and p.note
        and [l.role for l in p.layers] == [l.role for l in manual_template()]
    )
    p, _ = read(["not json", "not json"])  # one repair retry, then the template
    assert p.origin == "manual" and p.note
    p, _ = read(
        [reply(headline={"text": "x" * 700})]
    )  # outside the Layer bounds: not a usable reading
    assert p.origin == "manual" and "not usable" in p.note


def test_allow_empty_text_skips_only_the_two_empty_text_problems():
    layers = [Layer(**{**l.model_dump(), "text": "", "font_px": 0}) for l in manual_template()]
    strict = check_layers(layers)
    assert any("text is empty" in x for x in strict) and any("size is missing" in x for x in strict)
    assert check_layers(layers, allow_empty_text=True) == []
    layers[2] = Layer(**{**layers[2].model_dump(), "text": "中", "font_px": 48})
    assert any("Liberation Sans" in x for x in check_layers(layers, allow_empty_text=True))
