"""Product-page endpoints over HTTP, with MockPageFetcher and MockProvider (opt-in: OA_ENGINE_TESTS=1)."""

import pytest
from fastapi.testclient import TestClient

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.pages import MockPageFetcher, PageError
from open_apprentice.providers.mock import MockProvider
from tests.integration.conftest import TOKEN

SAMPLE = "https://demo.example.com/samples/halden-h7.html"


@pytest.fixture()
def client(engine_url, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_URL", engine_url)
    monkeypatch.setenv("EVALUATOR_TOKEN", TOKEN)
    monkeypatch.setenv("OA_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("PAGE_MODE", "mock")
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        assert isinstance(c.app.state.page_fetcher, MockPageFetcher)
        yield c


def F(text, quote=None):
    return {"text": text, "quote": quote or text}


FACTS = {
    "language": "en",
    "product_name": F("Halden H7 Headphones"),
    "prices": [F("$159", "Now $159"), F("$229", "Was $229")],
    "features": [F("40-hour battery", "40-hour battery life"), F("waterproof", "fully waterproof")],
    "legal": [
        F("Offer ends 31 Oct 2026", "Offer ends 31 Oct 2026. While stocks last. Terms apply.")
    ],
}


def model(headlines=("Hear only what matters.",), facts=FACTS):
    return MockProvider(
        {"campaign_facts": [facts], "campaign_copy": [{"headlines": list(headlines)}]}
    )


def wid(c) -> str:
    r = c.post("/api/campaign/workspaces", json={"reading": "fixed"})
    assert r.status_code == 200, r.text
    return r.json()["workspace_id"]


def post_page(c, w, url=SAMPLE):
    return c.post(f"/api/campaign/workspaces/{w}/pages", json={"url": url})


def test_happy_path_returns_grounded_facts_and_copy(client):
    client.app.state.provider = model()
    w = wid(client)
    r = post_page(client, w)
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(out["page_id"]) == 12 and out["url"] == SAMPLE and out["origin"] == "mock"
    assert out["title"] == "Halden H7 Headphones" and out["chars"] > 200 and out["language"] == "en"
    assert out["facts"]["prices"][0] == {
        "text": "$159",
        "quote": "Now $159",
        "amount": "159.00",
        "currency": "USD",
    }
    assert [f["text"] for f in out["facts"]["features"]] == ["40-hour battery"]
    assert any(
        "waterproof" in p for p in out["problems"]
    ), "an invented fact is dropped and reported"
    assert out["copy"]["origin"] == "model" and out["copy"]["options"] == [
        {"id": "c1", "headline": "Hear only what matters.", "notes": []}
    ]
    assert out["copy"]["price"] == "$159" and out["copy"]["cta"] == "Shop now"
    assert out["copy"]["legal"] == "Offer ends 31 Oct 2026"
    stored = client.app.state.campaign[w].pages[out["page_id"]]
    assert set(stored) == {"url", "text", "facts", "copy"} and "Now $159" in stored["text"]
    assert client.app.state.spend["tokens"] > 0, "model use is metered"


def test_copy_rejects_an_invented_number_and_a_claim_word(client):
    client.app.state.provider = model(("Now only $99", "The best headphones", "Quiet. Clear."))
    out = post_page(client, wid(client)).json()
    assert [o["headline"] for o in out["copy"]["options"]] == ["Quiet. Clear."]
    probs = " ".join(out["copy"]["problems"])
    assert "number 99" in probs and "claim word" in probs


def test_no_model_uses_the_baseline_and_the_template(client):
    client.app.state.provider = None
    out = post_page(client, wid(client)).json()
    assert out["copy"]["origin"] == "template"
    assert out["copy"]["options"] == [{"id": "c1", "headline": "Halden H7 Headphones"}]
    assert [p["text"] for p in out["facts"]["prices"]] == ["$159", "$229"] and out["facts"][
        "features"
    ] == []


def test_a_german_page_gets_german_copy_fields(client):
    client.app.state.provider = None
    out = post_page(
        client, wid(client), "https://demo.example.com/samples/halden-h7-de.html"
    ).json()
    assert out["language"] == "de" and out["copy"]["cta"] == "Jetzt kaufen"
    assert (
        out["facts"]["prices"][0]["currency"] == "EUR"
        and out["facts"]["prices"][0]["amount"] == "149.00"
    )


@pytest.mark.parametrize(
    "url", ["http://demo.example.com/x", "https://localhost/x", "https://10.0.0.1/x", "nonsense"]
)
def test_a_bad_address_is_422_with_a_plain_sentence(client, url):
    r = post_page(client, wid(client), url)
    assert r.status_code == 422 and r.json()["detail"].endswith(".")


def test_a_page_that_cannot_be_read_is_502(client):
    r = post_page(client, wid(client), "https://other.example.com/x")
    assert r.status_code == 502 and r.json()["detail"].startswith("This server reads only")

    class Broke:
        async def fetch(self, url):
            raise PageError("the page could not be read: blocked by robots")

    client.app.state.page_fetcher = Broke()
    r = post_page(client, wid(client))
    assert (
        r.status_code == 502
        and r.json()["detail"] == "The page could not be read: blocked by robots"
    )


def test_a_workspace_holds_three_pages(client):
    client.app.state.provider = None
    w = wid(client)
    for _ in range(3):
        assert post_page(client, w).status_code == 200
    r = post_page(client, w)
    assert r.status_code == 409 and "3 pages" in r.json()["detail"]


def test_pages_are_limited_per_address_per_hour(client):
    client.app.state.provider = None
    codes = [post_page(client, wid(client)).status_code for _ in range(7)]
    assert codes == [200] * 6 + [429]
    assert "limited to 6 per hour" in post_page(client, wid(client)).json()["detail"]


def test_a_bad_address_does_not_use_up_the_quota(client):
    client.app.state.provider = None
    w = wid(client)
    for _ in range(8):
        assert post_page(client, w, "http://x.example.com").status_code == 422
    assert post_page(client, w).status_code == 200


def _banner(client, w, price):
    scene = load_fixture("short_a")["scene"]
    for n in scene["nodes"]:
        if n.get("role") == "price":
            n["text"] = price
    client.app.state.campaign[w].banners["u-abcdef123456"] = {
        "scene": scene,
        "locale": "en",
        "png": "",
    }
    return "u-abcdef123456"


def check(client, w, b, p):
    return client.post(
        f"/api/campaign/workspaces/{w}/page-check", json={"banner_id": b, "page_id": p}
    )


def test_page_check_match_mismatch_and_unknown(client):
    client.app.state.provider = None
    w = wid(client)
    p = post_page(client, w).json()["page_id"]
    r = check(client, w, _banner(client, w, "Now $159 (was $229)"), p)
    assert r.status_code == 200 and r.json()["status"] == "match"
    assert r.json()["rows"][0]["detail"] == "The banner prices $159, $229 are listed on the page."
    assert check(client, w, _banner(client, w, "Now $149"), p).json()["status"] == "mismatch"
    assert check(client, w, _banner(client, w, "Ask in store"), p).json()["status"] == "unknown"


def test_page_check_404s_on_unknown_banner_or_page(client):
    client.app.state.provider = None
    w = wid(client)
    p = post_page(client, w).json()["page_id"]
    b = _banner(client, w, "$159")
    assert check(client, w, "u-000000000000", p).status_code == 404
    assert check(client, w, b, "0" * 12).status_code == 404
    assert (
        client.post(f"/api/campaign/workspaces/{'0' * 32}/pages", json={"url": SAMPLE}).status_code
        == 404
    )


def test_copy_false_skips_both_model_calls_and_still_feeds_the_page_check(client):
    prov = model()
    client.app.state.provider = prov
    w = wid(client)
    out = client.post(
        f"/api/campaign/workspaces/{w}/pages", json={"url": SAMPLE, "copy": False}
    ).json()
    assert prov.calls == [] and client.app.state.spend["tokens"] == 0
    assert out["copy"] == {
        "origin": "template",
        "options": [],
        "price": "$159",
        "cta": "",
        "legal": "",
        "problems": [],
    }
    assert out["facts"]["prices"][0] == {
        "text": "$159",
        "quote": "Now $159",
        "amount": "159.00",
        "currency": "USD",
    }
    assert (
        check(client, w, _banner(client, w, "Now $159"), out["page_id"]).json()["status"] == "match"
    )
