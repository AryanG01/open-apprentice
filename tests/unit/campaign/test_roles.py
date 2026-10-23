import asyncio

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.roles import (
    apply_roles,
    check_role_mapping,
    heuristic_roles,
    propose_roles,
    role_candidates,
)
from open_apprentice.providers.mock import MockProvider

UNTAGGED = {
    "untagged_short_b": "short_b",
    "untagged_de_long_a": "de_long_a",
    "untagged_fr_long": "fr_long",
}


def _truth(src):
    return {n["id"]: n["role"] for n in load_fixture(src)["scene"]["nodes"] if n.get("role")}


@pytest.mark.parametrize("fid,src", UNTAGGED.items())
def test_the_heuristic_recovers_the_authored_roles(fid, src):
    scene = load_fixture(fid)["scene"]
    assert heuristic_roles(scene, "banner") == _truth(src)
    assert check_role_mapping(scene, "banner", _truth(src)) == []


def test_candidates_are_what_the_model_sees():
    c = role_candidates(load_fixture("untagged_short_b")["scene"], "banner")
    assert len(c) == 7 and all("role" not in x for x in c)
    assert {x["type"] for x in c} == {"rect", "image", "text", "group"}


def _ledger():
    return Ledger(Limits(tokens=100_000, calls=4))


def _propose(fid, mapping):
    from open_apprentice.campaign.roles import opaque_ids

    to_opaque = opaque_ids(load_fixture(fid)["scene"], "banner")
    mapping = {
        to_opaque.get(k, k): v for k, v in mapping.items()
    }  # the model only ever sees opaque ids
    provider = MockProvider({"campaign_roles": [{"roles": mapping}]})
    return (
        asyncio.run(propose_roles(provider, _ledger(), load_fixture(fid)["scene"], "banner")),
        provider,
    )


def test_a_correct_model_mapping_is_accepted():
    p, provider = _propose("untagged_de_long_a", _truth("de_long_a"))
    assert (
        p.origin == "model"
        and p.mapping == _truth("de_long_a")
        and p.problems == []
        and len(provider.calls) == 1
    )


def test_a_swapped_price_and_headline_is_rejected_and_the_heuristic_is_used():
    swapped = dict(_truth("short_b"))
    swapped["sb-head"], swapped["sb-price"] = "price", "headline"
    p, _ = _propose("untagged_short_b", swapped)
    assert p.origin == "heuristic" and p.mapping == _truth("short_b")
    assert any("price" in x or "sizes" in x for x in p.problems)


def test_a_mapping_missing_a_role_is_rejected():
    partial = {k: v for k, v in _truth("short_b").items() if v != "legal"}
    assert any(
        "legal" in x
        for x in check_role_mapping(load_fixture("untagged_short_b")["scene"], "banner", partial)
    )


def test_without_a_provider_the_heuristic_is_used_and_nothing_is_called():
    p = asyncio.run(propose_roles(None, None, load_fixture("untagged_fr_long")["scene"], "banner"))
    assert p.origin == "heuristic" and p.mapping == _truth("fr_long")


def test_apply_roles_returns_a_tagged_copy():
    scene = load_fixture("untagged_short_b")["scene"]
    tagged = apply_roles(scene, "banner", _truth("short_b"))
    assert {n["id"]: n.get("role") for n in tagged["nodes"] if n.get("role")} == _truth("short_b")
    assert all("role" not in n for n in scene["nodes"])


# Final review fixes: swaps the type checks alone cannot see; ids must not name roles.
@pytest.mark.parametrize(
    "a,b", [("price", "legal"), ("headline", "legal"), ("brand_mark", "product_image")]
)
def test_swapped_roles_are_rejected(a, b):
    m = dict(_truth("short_b"))
    ka, kb = next(k for k, v in m.items() if v == a), next(k for k, v in m.items() if v == b)
    m[ka], m[kb] = b, a
    assert check_role_mapping(load_fixture("untagged_short_b")["scene"], "banner", m)


def test_the_model_sees_opaque_ids_and_no_asset_names():
    import json

    seen = json.dumps(role_candidates(load_fixture("untagged_short_b")["scene"], "banner"))
    for leak in (
        "sb-",
        "head",
        "price",
        "logo",
        "hero",
        "legal",
        "cta",
        "bg",
        "wordmark",
        "headphones",
    ):
        assert leak not in seen, leak


def test_a_proposal_in_opaque_ids_is_mapped_back():
    from open_apprentice.campaign.roles import opaque_ids

    scene = load_fixture("untagged_de_long_a")["scene"]
    to_opaque = opaque_ids(scene, "banner")
    p, _ = _propose("untagged_de_long_a", {to_opaque[k]: v for k, v in _truth("de_long_a").items()})
    assert p.origin == "model" and p.mapping == _truth("de_long_a")


# Fixes from the pre-registered role comparison (docs/evaluation/campaign_roles.md): the checker rejected correct answers.
def _short_b_with(**changes):
    scene = load_fixture("untagged_short_b")["scene"]
    truth = _truth("short_b")
    for role, fields in changes.items():
        nid = next(k for k, v in truth.items() if v == role)
        next(n for n in scene["nodes"] if n["id"] == nid).update(fields)
    return scene, truth


def test_a_sale_banner_whose_price_outsizes_the_headline_is_accepted():
    scene, truth = _short_b_with(price={"fontSize": 120})
    assert check_role_mapping(scene, "banner", truth) == []


@pytest.mark.parametrize(
    "text", ["199 zł", "1 495 kr", "R$ 89,90", "CHF 49.–", "₹2,499", "49,99 Kč"]
)
def test_prices_in_other_currencies_are_accepted(text):
    scene, truth = _short_b_with(price={"text": text})
    assert check_role_mapping(scene, "banner", truth) == []


@pytest.mark.parametrize("text", ["Free shipping", "Since 2024", "kr"])
def test_a_price_needs_both_a_number_and_a_currency(text):
    scene, truth = _short_b_with(price={"text": text})
    assert any("price" in p for p in check_role_mapping(scene, "banner", truth))


def test_legal_must_still_be_the_smallest_text():
    scene, truth = _short_b_with(legal={"fontSize": 200})
    assert any("legal" in p for p in check_role_mapping(scene, "banner", truth))


def test_layers_the_model_labels_with_an_empty_role_count_as_unlabelled():
    from open_apprentice.campaign.roles import opaque_ids

    scene = load_fixture("untagged_short_b")["scene"]
    scene["nodes"].append(
        {**next(n for n in scene["nodes"] if n.get("type") == "text"), "id": "decor"}
    )
    ids = opaque_ids(scene, "banner")
    answer = {ids[k]: v for k, v in _truth("short_b").items()} | {ids["decor"]: ""}
    provider = MockProvider({"campaign_roles": [{"roles": answer}]})
    p = asyncio.run(propose_roles(provider, _ledger(), scene, "banner"))
    assert p.origin == "model" and p.mapping == _truth("short_b")
