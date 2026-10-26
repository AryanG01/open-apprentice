import asyncio
from decimal import Decimal

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.facts import (
    baseline_facts,
    extract_facts,
    is_grounded,
    normalise,
    parse_price,
)
from open_apprentice.providers.mock import MockProvider

PAGE = """# Halden H7 Headphones

Hear only what matters.

Now $159

Was $229

* 40-hour battery life
* 30 dB adaptive noise cancelling

Offer ends 31 Oct 2026. While stocks last.
"""


def ledger():
    return Ledger(Limits(tokens=100_000, calls=10))


def run(provider, page=PAGE):
    return asyncio.run(extract_facts(provider, ledger(), page))


@pytest.mark.parametrize(
    "text,expected",
    [
        ("$1,299.00", (Decimal("1299.00"), "USD")),
        ("1.299,00 €", (Decimal("1299.00"), "EUR")),
        ("159 EUR", (Decimal("159"), "EUR")),
        ("Now $159", (Decimal("159"), "USD")),
        ("£51.77", (Decimal("51.77"), "GBP")),
        ("¥12,800", (Decimal("12800"), "JPY")),
        ("₹1,499", (Decimal("1499"), "INR")),
        ("149,00 €", (Decimal("149.00"), "EUR")),
        ("USD 20", (Decimal("20"), "USD")),
        ("1.299 €", (Decimal("1299"), "EUR")),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize("text", ["no price here", "159", "40 hour battery"])
def test_parse_price_needs_an_amount_and_a_currency(text):
    assert parse_price(text) is None


def test_normalise_and_grounding():
    assert normalise("**Now  $159**\n[Shop](x)") == "now $159 shopx"
    assert is_grounded("now $159", PAGE) and is_grounded("NOW\n$159", PAGE)
    assert not is_grounded("Now $149", PAGE) and not is_grounded("", PAGE)
    assert is_grounded("ＮＯＷ $159", PAGE)  # NFKC folds full-width letters


def test_baseline_has_title_all_prices_and_no_features():
    b = baseline_facts(PAGE)
    assert b.origin == "baseline" and b.product_name["text"] == "Halden H7 Headphones"
    assert [p["text"] for p in b.prices] == ["$159", "$229"]
    assert b.prices[0]["amount"] == "159.00" and b.prices[0]["currency"] == "USD"
    assert b.features == [] and b.language == "en" and b.problems == []
    assert baseline_facts("# Thing\nnothing").problems == ["No price was found on this page."]
    assert (
        baseline_facts("Das ist der Preis und die Farbe mit dem Zubehör für Sie.").language == "de"
    )


def F(text, quote=None):
    return {"text": text, "quote": quote or text}


GOOD = {
    "language": "en",
    "product_name": F("Halden H7 Headphones"),
    "prices": [F("$159", "Now $159"), F("$229", "Was $229")],
    "features": [F("40-hour battery", "* 40-hour battery life")],
    "legal": [F("Offer ends 31 Oct 2026", "Offer ends 31 Oct 2026. While stocks last.")],
}


def test_model_facts_are_kept_when_grounded_and_amounts_come_from_the_text():
    reply = dict(GOOD, prices=[dict(F("$159", "Now $159"))])
    r = run(MockProvider({"campaign_facts": [reply]}))
    assert r.origin == "model" and r.problems == []
    assert r.prices == [
        {"text": "$159", "quote": "Now $159", "amount": "159.00", "currency": "USD"}
    ]
    assert (
        r.features[0]["text"] == "40-hour battery"
        and r.legal[0]["text"] == "Offer ends 31 Oct 2026"
    )


def test_an_invented_quote_or_text_outside_the_quote_is_dropped_with_a_reason():
    reply = dict(
        GOOD,
        product_name=F("Halden H9", "Halden H9 Headphones"),
        features=[
            F("40-hour battery", "* 40-hour battery life"),
            F("waterproof", "fully waterproof"),
            F("wireless", "40-hour battery life"),
        ],
        legal=[F("Lifetime warranty", "Lifetime warranty")],
    )
    r = run(MockProvider({"campaign_facts": [reply]}))
    assert [f["text"] for f in r.features] == ["40-hour battery"]
    assert r.legal == []
    assert r.product_name["text"] == "Halden H7 Headphones"  # falls back to the page's own H1
    joined = " ".join(r.problems)
    assert (
        "waterproof" in joined
        and "wireless" in joined
        and "Lifetime" in joined
        and "Halden H9" in joined
    )


def test_a_price_without_a_readable_amount_is_dropped_and_lists_are_capped():
    page = (
        PAGE
        + "\n".join(f"* feature {i}" for i in range(9))
        + "\n"
        + "\n".join(f"Pay ${i + 10}" for i in range(9))
    )
    reply = {
        "language": "en",
        "product_name": None,
        "prices": [F("Now", "Now $159")] + [F(f"${i + 10}", f"Pay ${i + 10}") for i in range(9)],
        "features": [F(f"feature {i}") for i in range(9)],
        "legal": [F("Offer ends 31 Oct 2026"), F("While stocks last"), F("Offer ends")],
    }
    r = run(MockProvider({"campaign_facts": [reply]}), page)
    assert len(r.prices) == 6 and len(r.features) == 4 and len(r.legal) == 2
    assert "no amount" in " ".join(r.problems)


def test_model_prices_missing_fall_back_to_the_pages_own_prices():
    r = run(MockProvider({"campaign_facts": [dict(GOOD, prices=[])]}))
    assert [p["text"] for p in r.prices] == ["$159", "$229"]


def test_no_provider_or_a_bad_reply_falls_back_to_the_baseline():
    assert run(None).origin == "baseline"
    r = run(MockProvider({"campaign_facts": ["not json", "not json"]}))
    assert r.origin == "baseline" and r.prices and "could not be used" in r.problems[0]
    r = run(
        MockProvider({"campaign_facts": [{"surprise": 1}, {"surprise": 1}]})
    )  # unknown field: schema rejects
    assert r.origin == "baseline"


def test_the_model_sees_the_page_text_and_the_prompt_says_never_invent():
    p = MockProvider({"campaign_facts": [GOOD]})
    run(p)
    system, user = p.calls[0][1]
    assert "Never invent" in system.content and "Now $159" in user.content
