"""Price, button and small print are optional: real designs rarely have all six parts (docs/evaluation/real_world_coverage.md).
Logo, product image and headline stay required, and every part that is present is checked as strictly as before."""

import pytest

from open_apprentice.campaign.roles import check_role_mapping
from open_apprentice.campaign.scene import RoleError, role_map
from open_apprentice.campaign.vision import build_scene, check_layers

from .test_vision import BG, crops_for, layers_from

OPTIONAL = ("price", "cta", "legal")
REQUIRED = ("brand_mark", "product_image", "headline")


def without(*roles):
    return [l for l in layers_from() if l.role not in roles]


@pytest.mark.parametrize("gone", [("price",), ("cta",), ("legal",), OPTIONAL])
def test_optional_parts_may_be_absent(gone):
    assert check_layers(without(*gone), BG) == []


@pytest.mark.parametrize("gone", REQUIRED)
def test_required_parts_are_still_required(gone):
    assert any(gone in p and "missing" in p for p in check_layers(without(gone), BG))


@pytest.mark.parametrize("gone", [("price",), ("cta",), ("legal",), OPTIONAL])
def test_a_banner_without_optional_parts_passes_both_role_gates(gone):
    ls = without(*gone)
    scene = build_scene(
        ls, background=BG, crops=crops_for(ls), uid="0123456789ab", link=None, locale="en"
    )
    roles = {n["role"] for n in scene["nodes"] if n.get("role")}
    assert roles == {"background", *REQUIRED, *(r for r in OPTIONAL if r not in gone)}
    role_map(scene, "banner")
    mapping = {n["id"]: n["role"] for n in scene["nodes"] if n.get("role")}
    assert check_role_mapping(scene, "banner", mapping) == []


def test_role_map_still_stops_on_a_missing_required_role():
    ls = without("headline")
    scene = build_scene(
        without(),
        background=BG,
        crops=crops_for(layers_from()),
        uid="0123456789ab",
        link=None,
        locale="en",
    )
    scene["nodes"] = [n for n in scene["nodes"] if n.get("role") != "headline"]
    with pytest.raises(RoleError):
        role_map(scene, "banner")
    assert ls  # the editor-side check names it too (test above)


def test_checks_on_a_present_part_are_not_relaxed():
    ls = [l for l in layers_from() if l.role != "cta"]
    ls = [l.model_copy(update={"text": "Free shipping"}) if l.role == "price" else l for l in ls]
    assert any("price" in p for p in check_layers(ls, BG))
