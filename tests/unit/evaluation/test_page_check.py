import ast
import pathlib

import pytest

from open_apprentice.evaluation import page_check
from open_apprentice.evaluation.page_check import check_page

PAGE = "# Halden H7\nNow $159\nWas $229\nOffer ends 31 Oct 2026."


def scene(price=None, headline="Hear only what matters."):
    nodes = [{"id": "h", "type": "text", "role": "headline", "text": headline}]
    if price is not None:
        nodes.append({"id": "p", "type": "text", "role": "price", "text": price})
    return {"nodes": nodes}


def test_match_when_every_banner_amount_is_on_the_page():
    r = check_page(scene("Now $159 (was $229)"), PAGE)
    assert r["status"] == "match" and r["notes"] == []
    row = r["rows"][0]
    assert row["field"] == "price" and row["ok"] is True
    assert row["banner"] == ["$159", "$229"] and row["page"] == ["$159", "$229"]
    assert row["detail"] == "The banner prices $159, $229 are on the page."
    assert (
        check_page(scene("$159"), PAGE)["rows"][0]["detail"]
        == "The banner price $159 is on the page."
    )


def test_mismatch_when_an_amount_is_not_on_the_page():
    r = check_page(scene("Now $149"), PAGE)
    assert r["status"] == "mismatch" and r["rows"][0]["ok"] is False
    assert "$149" in r["rows"][0]["detail"] and "$159, $229" in r["rows"][0]["detail"]


def test_a_different_currency_is_a_mismatch_but_only_when_both_state_one():
    assert check_page(scene("€159"), PAGE)["status"] == "mismatch"
    assert check_page(scene("159"), PAGE)["status"] == "match"  # the banner states no currency


def test_amounts_are_compared_as_decimals_across_formats():
    assert check_page(scene("1.299,00 €"), "Jetzt 1299 EUR")["status"] == "match"
    assert check_page(scene("$1,299.00"), "Price $1299")["status"] == "match"
    assert check_page(scene("$159.0"), PAGE)["status"] == "match"
    assert check_page(scene("$159.50"), PAGE)["status"] == "mismatch"


def test_unknown_when_the_banner_or_the_page_has_no_price():
    r = check_page(scene(None), PAGE)
    assert (
        r["status"] == "unknown"
        and r["rows"][0]["ok"] is None
        and "no price" in r["rows"][0]["detail"]
    )
    r = check_page(scene("$159"), "No prices at all")
    assert r["status"] == "unknown" and "page" in r["rows"][0]["detail"]


def test_a_headline_amount_not_on_the_page_is_a_note_not_a_status_change():
    r = check_page(scene("$159", headline="Only $99 today"), PAGE)
    assert r["status"] == "match" and "$99" in r["notes"][0]


@pytest.mark.parametrize("bad", ["campaign", "agent", "skills", "concepts"])
def test_the_checker_is_independent_of_agent_visible_code(bad):
    tree = ast.parse(pathlib.Path(page_check.__file__).read_text())
    mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module] + [
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    ]
    assert not any(f"open_apprentice.{bad}" in m for m in mods)
