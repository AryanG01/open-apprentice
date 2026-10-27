import asyncio

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.copy import CTA_OTHER, check_headline, draft_copy
from open_apprentice.campaign.facts import extract_facts
from open_apprentice.providers.mock import MockProvider

PAGE = """# Halden H7 Headphones

Hear only what matters.

Now $159 (was $229)

* 40-hour battery life
* 30 dB adaptive noise cancelling

Offer ends 31 Oct 2026. While stocks last. Terms apply.
"""


def test_a_plain_headline_passes():
    assert check_headline("Hear only what matters.", PAGE) == []
    assert check_headline("40-hour battery for $159", PAGE) == []


def test_length_rule():
    assert "characters" in check_headline("", PAGE)[0]
    assert "characters" in check_headline("a" * 91, PAGE)[0]
    assert check_headline("a" * 90, PAGE) == []


def test_digits_must_be_on_the_page():
    assert any("number 50" in p for p in check_headline("50 hour battery", PAGE))
    assert check_headline("30 dB of quiet", PAGE) == []


def test_currency_must_be_on_the_page():
    assert any("€" in p for p in check_headline("Now €159", PAGE))
    assert any("GBP" in p for p in check_headline("Only 159 GBP", PAGE))
    assert not any("currency" in p for p in check_headline("Only 159 USD", PAGE + " USD"))


@pytest.mark.parametrize(
    "headline",
    [
        "The best headphones", "Number one choice", "Voted #1", "Guaranteed quiet", "Free shipping",
        "The cheapest H7", "Lowest price ever", "Proven quiet", "A miracle", "100% quiet",
        "Award-winning sound", "Official partner",
        "Beste Kopfhörer", "Garantiert leise", "Gratis dazu", "Kostenlos testen",
        "Meilleur son", "Son garanti", "Livraison gratuit", "Mejor sonido", "Sonido garantizado",
    ],
)  # fmt: skip
def test_claim_words_are_refused_unless_the_page_has_them(headline):
    assert any("claim word" in p for p in check_headline(headline, PAGE))


def test_a_claim_word_the_page_itself_uses_is_allowed():
    assert check_headline("The best sound", PAGE + " The best sound.") == []


def test_links_and_emails_are_refused():
    for h in [
        "See www.halden.com",
        "Visit https://halden.com",
        "mail me@halden.com",
        "halden.shop now",
    ]:
        assert any("link" in p for p in check_headline(h, PAGE)), h


def test_glyphs_must_be_drawable_by_the_font():
    assert any("cannot draw" in p for p in check_headline("Hear 🎧 only", PAGE))
    assert check_headline("Hören Sie nur, was zählt.", "Hören Sie nur, was zählt.") == []


def facts_for(page=PAGE):
    return asyncio.run(extract_facts(None, Ledger(Limits(tokens=1000, calls=5)), page))


def draft(provider, language="en", page=PAGE, facts=None):
    f = facts or facts_for(page)
    return asyncio.run(
        draft_copy(provider, Ledger(Limits(tokens=100_000, calls=10)), f, language, page)
    )


def test_template_fallback_is_the_product_name_with_the_pages_own_price_and_a_table_button():
    c = draft(None)
    assert c.origin == "template" and c.options == [
        {"id": "c1", "headline": "Halden H7 Headphones"}
    ]
    assert c.price == "$159" and c.cta == "Shop now" and c.legal == ""


def test_model_headlines_are_kept_deduplicated_and_capped_at_three():
    heads = [
        "Hear only what matters.",
        "Hear only what matters.",
        "Quiet. Clear.",
        "40 hours of music",
        "30 dB of calm",
    ]
    c = draft(MockProvider({"campaign_copy": [{"headlines": heads}]}))
    assert c.origin == "model" and [o["headline"] for o in c.options] == heads[:1] + heads[2:4]
    assert [o["id"] for o in c.options] == ["c1", "c2", "c3"]


def test_typographic_hyphens_and_non_breaking_spaces_are_normalised_not_rejected():
    heads = ["Halden H7 \u2011 40\u2011hour battery\u00a0life", "Quiet\u2010clear"]
    c = draft(MockProvider({"campaign_copy": [{"headlines": heads}]}))
    assert c.origin == "model"
    assert [o["headline"] for o in c.options] == ["Halden H7 - 40-hour battery life", "Quiet-clear"]


def test_an_invented_number_and_a_claim_word_are_rejected_and_the_template_is_used():
    c = draft(
        MockProvider(
            {"campaign_copy": [{"headlines": ["Now only $99", "The best headphones ever"]}]}
        )
    )
    assert c.origin == "template" and c.options[0]["headline"] == "Halden H7 Headphones"
    joined = " ".join(c.problems)
    assert "number 99" in joined and "claim word" in joined


def test_one_bad_option_does_not_cost_the_good_one():
    c = draft(MockProvider({"campaign_copy": [{"headlines": ["Free for you", "Quiet. Clear."]}]}))
    assert c.origin == "model" and [o["headline"] for o in c.options] == ["Quiet. Clear."]
    assert any("Free for you" in p for p in c.problems)


def test_a_failed_model_reply_uses_the_template_with_a_reason():
    c = draft(MockProvider({"campaign_copy": ["nope", "nope"]}))
    assert c.origin == "template" and "could not be used" in c.problems[0]


def test_button_table_and_unknown_language():
    assert draft(None, "de").cta == "Jetzt kaufen"
    assert {draft(None, l).cta for l in ("fr", "es", "it", "nl", "pt")} == {
        "Acheter", "Comprar ahora", "Acquista ora", "Koop nu", "Comprar agora"
    }  # fmt: skip
    assert draft(None, "ja").cta == CTA_OTHER


def test_legal_is_the_first_grounded_legal_fact_within_600_characters():
    page = PAGE
    f = facts_for(page)
    f.legal = [
        {"text": "x" * 601, "quote": "x"},
        {"text": "Offer ends 31 Oct 2026", "quote": "Offer ends 31 Oct 2026."},
    ]
    assert draft(None, facts=f).legal == "Offer ends 31 Oct 2026"
    f.legal = []
    assert draft(None, facts=f).legal == ""


def test_no_product_name_and_no_price_leave_empty_fields_with_a_problem():
    page = "just some words"
    c = draft(None, page=page)
    assert c.options == [{"id": "c1", "headline": ""}] and c.price == "" and c.problems


def test_review_notes_flag_what_the_checks_cannot_settle():
    """The four drafts the hard checks let through (a reviewer's counterexamples): each now carries a note for the owner."""
    from open_apprentice.campaign.copy import review_notes

    assert (
        check_headline("Acme headphones", "Halden headphones. Up to 40 hours battery life.") == []
    )
    assert any(
        "Acme" in n
        for n in review_notes("Acme headphones", "Halden headphones. Up to 40 hours battery life.")
    )
    neg = "Halden headphones: up to 40 hours. This is not guaranteed."
    assert check_headline("40 hours guaranteed", neg) == []
    assert any("not/no" in n for n in review_notes("40 hours guaranteed", neg))
    assert any(
        "saving" in n for n in review_notes("Save $159", "Model A costs $159; Model B costs $229.")
    )
    assert any(
        "up to" in n
        for n in review_notes("Battery lasts 40 hours", "Battery lasts up to 40 hours.")
    )


def test_a_faithful_headline_has_no_notes():
    from open_apprentice.campaign.copy import review_notes

    assert review_notes("Hear only what matters.", PAGE) == []
    assert review_notes("40-hour battery for $159", PAGE) == []
    assert review_notes("Battery lasts up to 40 hours", "Battery lasts up to 40 hours.") == []
