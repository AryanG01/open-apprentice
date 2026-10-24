"""Reading a flat banner image: the model's proposal is checked deterministically, never trusted; the editor's layers
become the same scene shape the fixtures use, and pass the existing role gate."""

import asyncio
import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.roles import check_role_mapping
from open_apprentice.campaign.scene import role_map
from open_apprentice.campaign.vision import (
    ASSET_ID,
    Layer,
    build_scene,
    check_layers,
    from_vision,
    manual_template,
    propose_layers,
)
from open_apprentice.providers.mock import MockProvider
from tests.pngs import png_url

PNG = png_url(1280, 720)
BG = "#1d1240"


def layers_from(fid="short_a") -> list[Layer]:
    """The fixture's own geometry, as the editor would hold it."""
    nodes = load_fixture(fid)["scene"]["nodes"]
    kids = {n["parent"]: n for n in nodes if n.get("parent", "").endswith("-cta")}
    out = []
    for n in nodes:
        if n.get("parent") != "banner" or n.get("role") in (None, "background"):
            continue
        t = kids[n["id"]] if n["role"] == "cta" else n
        w = n.get("width") or kids[n["id"]]["width"]
        h = n.get("height") or kids[n["id"]]["height"]
        out.append(
            Layer(
                role=n["role"],
                box=[n["x"], n["y"], w, h],
                text=t.get("text", ""),
                font_px=t.get("fontSize", 0),
                bold=t.get("fontStyle") == "bold",
                color=t.get("fill", "") if n["role"] != "cta" else "#1d1240",
            )
        )
    return out


def crops_for(layers) -> dict[str, str]:
    """Browser-style crops: a PNG as large as each image box."""
    return {
        l.role: png_url(round(l.box[2]), round(l.box[3]))
        for l in layers
        if l.role in ("brand_mark", "product_image")
    }


def edit(layers, role, **changes):
    return [Layer(**{**l.model_dump(), **changes}) if l.role == role else l for l in layers]


def test_the_fixtures_own_layers_pass_every_check():
    assert check_layers(layers_from(), BG) == []


@pytest.mark.parametrize(
    "role,changes,needle",
    [
        ("headline", {"box": [1200, 100, 400, 100]}, "outside the banner"),
        ("brand_mark", {"box": [64, 48, 10, 10]}, "too small"),
        ("price", {"text": "Free shipping"}, "price"),
        ("price", {"text": "Now 159"}, "currency"),
        ("headline", {"text": ""}, "text"),
        ("headline", {"text": "x" * 300}, "too long"),
        ("legal", {"font_px": 60}, "legal"),
        ("headline", {"text": "Hear only what matters 中"}, "Liberation Sans"),
        ("headline", {"color": "red"}, "colour"),
        ("headline", {"color": "#1e1342"}, "contrast"),
        ("cta", {"box": [640, 432, 20, 10]}, "too small"),
        ("product_image", {"box": [600, 150, 400, 300]}, "overlaps"),
    ],
)
def test_each_bad_layer_is_named(role, changes, needle):
    problems = check_layers(edit(layers_from(), role, **changes), BG)
    assert any(needle in p for p in problems), problems


def test_a_missing_or_doubled_role_is_named():
    ls = [l for l in layers_from() if l.role != "legal"]
    assert any("legal" in p and "missing" in p for p in check_layers(ls, BG))
    ls = layers_from() + [layers_from()[0]]
    assert any("more than one" in p for p in check_layers(ls, BG))
    ls = layers_from() + [Layer(role="sticker", box=[0, 0, 100, 100])]
    assert any("unknown role" in p for p in check_layers(ls, BG))


def test_contrast_is_only_judged_once_the_background_is_known():
    ls = edit(layers_from(), "headline", color="#1e1342")
    assert check_layers(ls) == []  # proposal stage: no sampled background yet
    assert any("contrast" in p for p in check_layers(ls, BG))


def test_built_scene_passes_the_existing_role_gate_and_carries_its_assets():
    crops = crops_for(layers_from())
    scene = build_scene(
        layers_from(),
        background=BG,
        crops=crops,
        uid="0123456789ab",
        link="https://shop.example/x",
        locale="en",
    )
    assert role_map(scene, "banner")
    mapping = {n["id"]: n["role"] for n in scene["nodes"] if n.get("role")}
    assert check_role_mapping(scene, "banner", mapping) == []
    assert set(scene["assets"]) == {"u-0123456789ab-brand_mark", "u-0123456789ab-product_image"}
    assert all(ASSET_ID.fullmatch(a) for a in scene["assets"])
    imgs = [n for n in scene["nodes"] if n["type"] == "image"]
    assert {n["asset"] for n in imgs} == set(scene["assets"])
    texts = [n for n in scene["nodes"] if n["type"] == "text"]
    assert texts and all(
        n["fontFamily"] == "Liberation Sans" and n["fontStyle"] in ("normal", "bold") for n in texts
    )
    cta = next(n for n in scene["nodes"] if n.get("role") == "cta")
    assert cta["link"] == "https://shop.example/x"
    assert {k["type"] for k in scene["nodes"] if k.get("parent") == cta["id"]} == {"shape", "text"}
    assert scene["nodes"][0]["type"] == "artboard" and scene["canvas"] == {
        "width": 1280,
        "height": 720,
    }


def test_build_scene_refuses_what_the_checks_refuse_and_unsafe_links():
    crops = crops_for(layers_from())
    bad = edit(layers_from(), "price", text="Free")
    with pytest.raises(ValueError, match="price"):
        build_scene(bad, background=BG, crops=crops, uid="0123456789ab", link=None, locale="en")
    with pytest.raises(ValueError, match="https"):
        build_scene(
            layers_from(),
            background=BG,
            crops=crops,
            uid="0123456789ab",
            link="javascript:alert(1)",
            locale="en",
        )
    with pytest.raises(ValueError, match="crop"):
        build_scene(
            layers_from(),
            background=BG,
            crops={"brand_mark": crops_for(layers_from())["brand_mark"]},
            uid="0123456789ab",
            link=None,
            locale="en",
        )
    with pytest.raises(ValueError, match="uid"):
        build_scene(layers_from(), background=BG, crops=crops, uid="../etc", link=None, locale="en")


def test_text_sizes_are_clamped_to_their_boxes():
    ls = edit(layers_from(), "headline", font_px=500)
    scene = build_scene(
        ls, background=BG, crops=crops_for(ls), uid="0123456789ab", link=None, locale="en"
    )
    head = next(n for n in scene["nodes"] if n.get("role") == "headline")
    assert head["fontSize"] <= head["height"]


def test_model_boxes_are_corner_pairs_on_a_0_to_1000_grid():
    out = from_vision(
        {
            "language": "de",
            "layers": [
                {
                    "role": "headline",
                    "box": [500, 250, 1000, 500],
                    "text": "Hallo",
                    "font_px": 40,
                    "bold": True,
                    "color": "#ffffff",
                }
            ],
        }
    )
    (l,) = out.layers
    assert out.language == "de" and l.box == [640.0, 180.0, 640.0, 180.0]


def test_the_manual_template_needs_the_owner_to_type_the_words():
    ls = manual_template()
    assert {l.role for l in ls} == {
        "brand_mark",
        "product_image",
        "headline",
        "price",
        "cta",
        "legal",
    }
    assert any("text" in p for p in check_layers(ls))


def _scripted(reply):
    return MockProvider({"campaign_vision": [reply]})


def _propose(provider):
    return asyncio.run(propose_layers(provider, Ledger(Limits(tokens=200_000, calls=4)), PNG))


def test_a_good_model_reply_is_returned_in_pixels_with_no_problems_and_sees_the_image():
    ls = layers_from()
    reply = {
        "language": "en",
        "layers": [
            {
                "role": l.role,
                "box": [
                    l.box[0] / 1.28,
                    l.box[1] / 0.72,
                    (l.box[0] + l.box[2]) / 1.28,
                    (l.box[1] + l.box[3]) / 0.72,
                ],
                "text": l.text,
                "font_px": l.font_px,
                "bold": l.bold,
                "color": l.color,
            }
            for l in ls
        ],
    }
    provider = _scripted(reply)
    p = _propose(provider)
    assert p.origin == "model" and p.language == "en"
    assert check_layers(p.layers) == [] and p.problems == []
    got = {l.role: l.box for l in p.layers}
    assert all(
        abs(a - b) < 0.5
        for a, b in zip(got["headline"], next(l.box for l in ls if l.role == "headline"))
    )
    user = provider.calls[0][1][-1].content
    assert user[-1]["type"] == "image_url" and user[-1]["image_url"]["url"] == PNG


def test_a_flawed_model_reply_is_kept_for_the_owner_to_fix_with_its_problems_listed():
    reply = {
        "language": "en",
        "layers": [
            {
                "role": "headline",
                "box": [0, 0, 500, 200],
                "text": "Hi",
                "font_px": 40,
                "bold": True,
                "color": "",
            }
        ],
    }
    p = _propose(_scripted(reply))
    assert p.origin == "model" and len(p.layers) == 1
    assert any("missing" in x for x in p.problems)


def test_no_provider_or_a_failed_call_gives_the_manual_template():
    assert asyncio.run(propose_layers(None, None, PNG)).origin == "manual"
    p = _propose(MockProvider({"campaign_vision": ["not json at all", "still not json"]}))
    assert p.origin == "manual" and p.note


def test_a_layer_has_a_four_number_box_and_bounded_strings():
    from pydantic import ValidationError

    for bad in (
        dict(role="headline", box=[1, 2, 3]),
        dict(role="headline", box=[1, 2, 3, 4, 5]),
        dict(role="headline", box=[1, 2, 3, 4], text="x" * 601),
        dict(role="x" * 40, box=[1, 2, 3, 4]),
        dict(role="headline", box=[1, 2, 3, 4], color="#" + "f" * 30),
    ):
        with pytest.raises(ValidationError):
            Layer(**bad)
    assert Layer(role="headline", box=[1, 2, 3, 4]).font_px == 0


def test_a_real_length_legal_line_is_fine_and_an_oversized_model_reply_falls_back_instead_of_crashing():
    long_legal = (
        "Angebot gültig bis 31.10.2026 und nur, solange der Vorrat reicht. " * 8
    )  # ~520 characters
    assert check_layers(edit(layers_from(), "legal", text=long_legal), BG) == []
    reply = {
        "language": "en",
        "layers": [
            {
                "role": "headline",
                "box": [0, 0, 500, 200],
                "text": "x" * 5000,
                "font_px": 40,
                "bold": True,
                "color": "",
            }
        ],
    }
    p = _propose(_scripted(reply))
    assert p.origin == "manual" and "usable" in p.note
