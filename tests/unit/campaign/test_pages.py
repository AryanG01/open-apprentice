import asyncio
import json
import pathlib

import httpx
import pytest

from open_apprentice.campaign.pages import (
    MAX_TEXT,
    MockPageFetcher,
    PageError,
    TavilyFetcher,
    clean_markdown,
    validate_page_url,
)

FIXTURE = pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "tavily_extract_response.json"
URL = "https://shop.example.com/p/1"


def run(coro):
    return asyncio.run(coro)


def test_good_urls_pass_and_are_trimmed():
    assert (
        validate_page_url("  https://shop.example.com/a?b=1 ") == "https://shop.example.com/a?b=1"
    )


@pytest.mark.parametrize(
    "url,needle",
    [
        ("", "Paste"),
        ("http://shop.example.com", "https://"),
        ("ftp://shop.example.com", "https://"),
        ("https://user:pw@shop.example.com/", "user name"),
        ("https://127.0.0.1/", "IP"),
        ("https://[::1]/", "IP"),
        ("https://localhost/", "public"),
        ("https://intranet/", "public"),
        ("https://printer.local/", "public"),
        ("https://wiki.internal/", "public"),
        ("https://nas.lan/", "public"),
        ("https://shop.example.com/a b", "spaces"),
        ("https://shop.example.com/" + "a" * 300, "300"),
        ("https://shop.example.com:abc/", "web address"),
    ],
)
def test_bad_urls_get_a_plain_sentence(url, needle):
    with pytest.raises(ValueError, match=needle):
        validate_page_url(url)


def test_clean_markdown_takes_h1_drops_images_and_truncates():
    title, text = clean_markdown("intro line\n![a](x.jpg)\n# Halden H7 #\nbody\n")
    assert title == "Halden H7" and "![" not in text and "body" in text
    assert clean_markdown("first line\nsecond")[0] == "first line"
    assert len(clean_markdown("x" * (MAX_TEXT + 500))[1]) == MAX_TEXT


def _fetcher(handler):
    return TavilyFetcher("tvly-secret", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_tavily_parses_a_real_response_and_sends_the_documented_request():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"], seen["body"] = req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    page = run(_fetcher(handler).fetch(URL))
    assert seen["auth"] == "Bearer tvly-secret"
    assert seen["body"] == {
        "urls": [URL],
        "extract_depth": "basic",
        "format": "markdown",
        "include_usage": True,
    }
    assert (
        page.origin == "tavily" and page.title == "A Light in the Attic" and "£51.77" in page.text
    )
    assert "![" not in page.text


@pytest.mark.parametrize(
    "status,needle",
    [
        (401, "key"),
        (429, "credits"),
        (432, "credits"),
        (433, "credits"),
        (500, "problem"),
        (503, "problem"),
    ],
)
def test_tavily_http_errors_become_plain_messages_without_the_key(status, needle):
    with pytest.raises(PageError) as e:
        run(_fetcher(lambda r: httpx.Response(status, json={"detail": "x"})).fetch(URL))
    assert needle in str(e.value) and "tvly-secret" not in str(e.value)


def test_tavily_failed_results_say_why():
    body = {"results": [], "failed_results": [{"url": URL, "error": "blocked by robots"}]}
    with pytest.raises(PageError, match="could not be read: blocked by robots"):
        run(_fetcher(lambda r: httpx.Response(200, json=body)).fetch(URL))


def test_tavily_timeout_and_empty_text():
    def boom(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(PageError, match="too long"):
        run(_fetcher(boom).fetch(URL))
    body = {"results": [{"url": URL, "raw_content": "![x](y.png)"}], "failed_results": []}
    with pytest.raises(PageError, match="no text"):
        run(_fetcher(lambda r: httpx.Response(200, json=body)).fetch(URL))


def test_mock_serves_the_sample_page_a_german_page_and_refuses_the_rest():
    m = MockPageFetcher()
    en = run(m.fetch("https://demo.example.com/samples/halden-h7.html"))
    assert en.origin == "mock" and en.title == "Halden H7 Headphones"
    assert "Now $159" in en.text and "Was $229" in en.text and "Offer ends 31 Oct 2026" in en.text
    assert (
        "font:" not in en.text and "<" not in en.text
    )  # the inline stylesheet and tags are not page text
    de = run(m.fetch("https://demo.example.com/samples/halden-h7-de.html"))
    assert "149,00 €" in de.text
    with pytest.raises(PageError, match="sample"):
        run(m.fetch("https://other.example.com/x"))
