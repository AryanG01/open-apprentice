import asyncio

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.explain import (
    check_explanation,
    explain,
    overflow_facts,
    template_explanation,
)
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.run import CampaignRun, Preview
from open_apprentice.providers.mock import MockProvider

SHRINK, SPLIT = "builtin_shrink_hero", "builtin_split_two_cards"


def _run():
    run = CampaignRun("r", "de", "question", "h")
    run.provenance["base_violations"] = [
        {"kind": "text_overflow", "node_id": "db-head", "detail": "316.8 > 160"},
        {"kind": "text_overflow", "node_id": "db-legal", "detail": "218.4 > 160"},
    ]
    run.previews = {
        SHRINK: Preview(SHRINK, "builtin", "s1", False, []),
        SPLIT: Preview(SPLIT, "builtin", "s2", True, []),
    }
    return run


FACTS = overflow_facts(_run(), load_fixture("de_long_b")["scene"])


def test_facts_name_roles_and_measured_numbers():
    assert FACTS["violations"] == [
        {"role": "headline", "kind": "text_overflow", "needed": 317, "available": 160},
        {"role": "legal", "kind": "text_overflow", "needed": 218, "available": 160},
    ]
    assert FACTS["outcomes"] == {SHRINK: False, SPLIT: True}


def test_the_template_passes_its_own_check():
    text = template_explanation(FACTS)
    assert check_explanation(text, FACTS) == [] and len(text) <= 320


def test_a_wrong_number_is_rejected():
    bad = "The headline needs 400 px but has 160 px, and the legal line needs 218 px. Only splitting across two cards fits."
    assert any("400" in p for p in check_explanation(bad, FACTS))


def test_a_role_that_did_not_overflow_is_rejected():
    bad = "The headline needs 317 px of 160 px and the legal line 218 px of 160 px; the price also overflows. Splitting fits."
    assert any("price" in p for p in check_explanation(bad, FACTS))


def test_claiming_a_non_fitting_outcome_fits_is_rejected():
    bad = "The headline needs 317 px of 160 px and the legal line 218 px of 160 px. Shrinking the product image fixes it."
    assert any("shrink" in p.lower() for p in check_explanation(bad, FACTS))


def test_a_rejected_model_explanation_falls_back_to_the_template():
    provider = MockProvider({"campaign_explain": [{"text": "The headline needs 5 lines."}]})
    e = asyncio.run(explain(provider, Ledger(Limits(tokens=50_000, calls=2)), FACTS))
    assert e.origin == "template" and e.text == template_explanation(FACTS) and e.problems


def test_a_good_model_explanation_is_used():
    good = "Your German headline needs 317 px but only 160 px fit, and the legal line needs 218 px of 160 px. Shrinking the product image is not enough; splitting across two cards fits."
    provider = MockProvider({"campaign_explain": [{"text": good}]})
    e = asyncio.run(explain(provider, Ledger(Limits(tokens=50_000, calls=2)), FACTS))
    assert e.origin == "model" and e.text == good


def test_without_a_provider_the_template_is_used():
    e = asyncio.run(explain(None, None, FACTS))
    assert e.origin == "template"


# Final review fixes: contradictions, raw ids, booleans, links.
import pytest


@pytest.mark.parametrize(
    "bad",
    [
        "The headline needs 160 px but its frame holds 317 px; the legal line needs 218 px of 160 px. Shrinking works and splitting does not help.",
        "The headline needs 317 px of 160 px and the legal line 218 px of 160 px. Shrink is not bad: it fits; splitting fits.",
        "The headline needs 317 px of 160 px and the legal line 218 px of 160 px. Shrinking does not fit; splitting cannot help.",
        "The headline needs 317 px of 160 px and the legal line 218 px of 160 px.",
        "The headline needs 317 px of 160 px and the legal line 218 px of 160 px. shrink_hero does not fit (false); split_two_cards fits (true).",
        "The headline needs 317 px of 160 px and the legal line 218 px of 160 px. Shrinking does not fit; splitting fits. See evil.example/x",
    ],
)
def test_contradictions_raw_ids_and_links_are_rejected(bad):
    assert check_explanation(bad, FACTS), bad


def test_a_word_containing_cta_is_not_a_role_mention():
    ok = template_explanation(FACTS).replace(
        "Splitting across two cards fits.", "Splitting across two cards fits, as the facts dictate."
    )
    assert check_explanation(ok, FACTS) == []
