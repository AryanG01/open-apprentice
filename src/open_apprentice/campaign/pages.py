"""Reading the owner's product page. Tavily Extract fetches it (this server never fetches the owner's address itself);
MockPageFetcher serves two offline pages for tests and the keyless demo."""

from __future__ import annotations

import html.parser
import ipaddress
import logging
import pathlib
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

MAX_URL = 300
MAX_TEXT = 60_000
TIMEOUT_S = 25.0
TAVILY_URL = "https://api.tavily.com/extract"
INTERNAL_SUFFIXES = (".local", ".internal", ".lan", ".localhost", ".intranet", ".corp", ".home")
SAMPLE_PATH = "/samples/halden-h7.html"
SAMPLE_DE_PATH = "/samples/halden-h7-de.html"
_SAMPLE_FILE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "apps"
    / "web"
    / "public"
    / "samples"
    / "halden-h7.html"
)


class PageError(Exception):
    """A plain-language reason the page could not be read."""


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def validate_page_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("Paste the address of the product page.")
    if len(url) > MAX_URL:
        raise ValueError(f"That address is longer than {MAX_URL} characters.")
    if re.search(r"\s", url):
        raise ValueError("The address must not contain spaces.")
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError as e:
        raise ValueError("That does not look like a web address.") from e
    if parts.scheme != "https":
        raise ValueError("The address must start with https://.")
    if "@" in parts.netloc:
        raise ValueError("The address must not contain a user name or password.")
    if _is_ip(host):
        raise ValueError("Use the page's web address, not an IP number.")
    low = host.lower().rstrip(".")
    if "." not in low or low == "localhost" or low.endswith(INTERNAL_SUFFIXES):
        raise ValueError("The address must be a public website, not a local or internal one.")
    return url


@dataclass
class PageResult:
    url: str
    title: str
    text: str
    origin: str  # tavily | mock


class PageFetcher(Protocol):
    async def fetch(self, url: str) -> PageResult: ...


_IMAGE_LINE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")
_H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$")


def clean_markdown(raw: str) -> tuple[str, str]:
    """(title, text): image lines dropped, text cut to MAX_TEXT, title = first H1 else first non-empty line."""
    lines = [ln for ln in raw.replace("\r\n", "\n").split("\n") if not _IMAGE_LINE.match(ln)]
    text = "\n".join(lines).strip()[:MAX_TEXT]
    title = ""
    for ln in text.split("\n"):
        m = _H1.match(ln.strip())
        if m:
            title = m.group(1)
            break
    if not title:
        title = next((ln.strip() for ln in text.split("\n") if ln.strip()), "")
    return title[:200], text


class TavilyFetcher:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)

    async def fetch(self, url: str) -> PageResult:
        try:
            r = await self._client.post(
                TAVILY_URL,
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "urls": [url],
                    "extract_depth": "basic",
                    "format": "markdown",
                    "include_usage": True,
                },
            )
        except httpx.TimeoutException as e:
            raise PageError("the page reader took too long; try again") from e
        except httpx.HTTPError as e:
            raise PageError("the page reader could not be reached; try again later") from e
        if r.status_code == 401:
            raise PageError("the page reader refused this server's key")
        if r.status_code in (429, 432, 433):
            raise PageError(
                "the page reader is out of requests or credits right now; try again later"
            )
        if r.status_code >= 500:
            raise PageError("the page reader had a problem; try again later")
        if r.status_code != 200:
            raise PageError(f"the page reader refused the request (code {r.status_code})")
        try:
            data = r.json()
        except ValueError as e:
            raise PageError("the page reader sent an unreadable reply") from e
        results = data.get("results") or []
        if not results:
            why = next(
                (f.get("error") for f in data.get("failed_results") or [] if f.get("error")), ""
            )
            raise PageError(f"the page could not be read{': ' + str(why) if why else ''}")
        title, text = clean_markdown(str(results[0].get("raw_content") or ""))
        if not text:
            raise PageError("the page could not be read: it has no text")
        return PageResult(url, title, text, "tavily")

    async def aclose(self) -> None:
        await self._client.aclose()


class _Visible(html.parser.HTMLParser):
    """Visible text of the sample page as light markdown (h1 as '# ')."""

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "title", "head"):
            self.skip += 1
        elif tag in ("h1", "h2", "h3"):
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in ("p", "ul", "section", "div"):
            self.out.append("\n\n")
        elif tag == "li":
            self.out.append("\n* ")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "title", "head"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data.strip())


def html_to_text(src: str) -> str:
    p = _Visible()
    p.feed(src)
    return re.sub(r"\n{3,}", "\n\n", "".join(p.out)).strip()


DE_PAGE = """# Halden H7 Kopfhörer

Hören Sie nur, was zählt.

Jetzt 149,00 € statt 219,00 €

## Eigenschaften

* 40 Stunden Akkulaufzeit
* 30 dB adaptive Geräuschunterdrückung

## Garantie

Auf jeden Halden H7 gibt es 2 Jahre Garantie.

Angebot gültig bis 31.10.2026. Solange der Vorrat reicht. Es gelten unsere Bedingungen.
"""


class MockPageFetcher:
    """Offline: the sample product page (English) and a German fixture; anything else is refused in plain words."""

    async def fetch(self, url: str) -> PageResult:
        path = urlsplit(url).path
        if path.endswith(SAMPLE_DE_PATH):
            title, text = clean_markdown(DE_PAGE)
            return PageResult(url, title, text, "mock")
        if path.endswith(SAMPLE_PATH):
            try:
                text = html_to_text(_SAMPLE_FILE.read_text(encoding="utf-8"))
            except OSError as e:
                raise PageError("the sample page is not available on this server") from e
            title, text = clean_markdown(text)
            return PageResult(url, title, text, "mock")
        raise PageError("this server reads only the sample page without a page-reader key")

    async def aclose(self) -> None:
        return None
