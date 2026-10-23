"""The role-mapping comparison's scoring and wiring on the mock provider (no spend): proves the table, not Nemotron."""

import asyncio
import copy

import pytest

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.roles import opaque_ids
from open_apprentice.evaluation.campaign_roles_eval import run_cases, score, summarize
from open_apprentice.providers.mock import MockProvider

GOLD = {"bg": "background", "logo": "brand_mark", "hero": "product_image", "h": "headline"}
GOLD |= {"p": "price", "btn": "cta", "fine": "legal"}


def test_exact_needs_the_gold_mapping_and_abstain_needs_no_full_mapping():
    assert score(GOLD, GOLD, "map")["exact"]
    swapped = GOLD | {"h": "price", "p": "headline"}
    s = score(swapped, GOLD, "map")
    assert not s["exact"] and s["false_confident"] and s["corrections"] == 2
    partial = {k: v for k, v in GOLD.items() if k != "fine"}
    assert score(partial, partial, "abstain")["exact"]  # gave no complete mapping
    assert score({}, partial, "abstain")["exact"]
    full = partial | {"decor": "legal"}
    s = score(full, partial, "abstain")
    assert not s["exact"] and s["false_confident"]


def test_macro_f1_counts_a_wrong_layer_against_both_roles():
    rows = [{"pred": GOLD | {"h": "price", "p": "headline"}, "gold": GOLD, "expect": "map"}]
    f1 = summarize(rows)["macro_f1"]
    assert f1 == pytest.approx(5 / 7)  # headline and price each 0, the other five 1


def _case(cid, scene, expect="map"):
    return {"id": cid, "category": "t", "expect": expect, "artboard": "banner", "scene": scene}


def _answer(scene, mapping_real):
    ids = opaque_ids(scene, "banner")
    return {"roles": {ids[k]: v for k, v in mapping_real.items()}}


def test_arms_on_the_mock_with_a_decoy_image_larger_than_the_product():
    plain = load_fixture("short_a")["scene"]
    decoy = copy.deepcopy(plain)
    hero = next(n for n in decoy["nodes"] if n.get("role") == "product_image")
    decoy["nodes"].append(
        {
            **{k: v for k, v in hero.items() if k != "role"},
            "id": "decoy",
            "width": 900,
            "height": 880,
        }
    )
    gold = lambda s: {n["id"]: n["role"] for n in s["nodes"] if n.get("role")}  # noqa: E731
    provider = MockProvider(
        {
            "campaign_roles": [_answer(plain, gold(plain)), _answer(decoy, gold(decoy))],
            "campaign_roles_strong": [
                _answer(plain, gold(plain)) | {"abstain": False, "reason": ""},
                {"roles": {}, "abstain": True, "reason": "unclear"},
            ],
        }
    )
    rows = asyncio.run(run_cases(provider, [_case("plain", plain), _case("decoy", decoy)]))
    by = {r["id"]: r for r in rows}
    assert by["plain"]["arms"]["A"]["exact"] and by["plain"]["arms"]["C"]["exact"]
    assert not by["decoy"]["arms"]["A"][
        "exact"
    ]  # the heuristic takes the biggest image as the product
    assert by["decoy"]["arms"]["B"]["exact"] and by["decoy"]["arms"]["C"]["exact"]
    assert by["decoy"]["c_origin"] == "model"
    assert not by["decoy"]["arms"]["D"]["exact"] and not by["decoy"]["arms"]["D"]["false_confident"]
