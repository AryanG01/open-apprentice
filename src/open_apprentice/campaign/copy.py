"""Banner copy drafted from grounded page facts. Nemotron may word the headline; every option is checked against the page
text (length, numbers, currency, claim words, links, glyphs). The price line, button and small print are never generated."""

from __future__ import annotations

import pathlib
import re
import unicodedata
from dataclasses import dataclass, field

from pydantic import Field

from open_apprentice.budget import Ledger
from open_apprentice.campaign.facts import CODES, FactsResult
from open_apprentice.campaign.model import call_model
from open_apprentice.campaign.vision import _cmap
from open_apprentice.providers.base import Provider, StrictModel

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "campaign_copy.md"
MAX_HEADLINE = 90
MAX_LEGAL = 600
MAX_OPTIONS = 3
CTA = {
    "en": "Shop now",
    "de": "Jetzt kaufen",
    "fr": "Acheter",
    "es": "Comprar ahora",
    "it": "Acquista ora",
    "nl": "Koop nu",
    "pt": "Comprar agora",
}
CTA_OTHER = "Learn more"
CLAIMS = (
    "best", "number one", "#1", "guaranteed", "free", "cheapest", "lowest price", "proven", "miracle",
    "100%", "award-winning", "official",
    "beste", "garantiert", "gratis", "kostenlos",
    "meilleur", "garanti", "gratuit",
    "mejor", "garantizado",
)  # fmt: skip
URLISH = re.compile(
    r"https?://|www\.|\S@\S|\b[\w-]+\.(?:com|net|org|io|de|fr|es|co|app|dev|shop|store)\b", re.I
)
CODE_WORD = re.compile(r"\b(" + "|".join(CODES) + r")\b", re.I)


class CopyOut(StrictModel):
    headlines: list[str] = Field(default_factory=list, max_length=10)


@dataclass
class CopyResult:
    origin: str  # model | template
    options: list[dict]
    price: str
    cta: str
    legal: str
    problems: list[str] = field(default_factory=list)
    tokens: int = 0

    def as_dict(self) -> dict:
        return {
            "origin": self.origin,
            "options": self.options,
            "price": self.price,
            "cta": self.cta,
            "legal": self.legal,
            "problems": self.problems,
        }


def _fold(text: str) -> str:  # not facts.normalise: that strips '#', which '#1' needs
    return unicodedata.normalize("NFKC", text).casefold()


def _has_word(word: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) is not None


_TYPOGRAPHY = str.maketrans(
    {
        "\u2010": "-",  # hyphen, non-breaking hyphen, figure dash and the minus sign: the font draws none of them
        "\u2011": "-",
        "\u2012": "-",
        "\u2212": "-",
        "\u00a0": " ",  # no-break, figure and narrow no-break spaces
        "\u2007": " ",
        "\u202f": " ",
    }
)


def tidy(headline: str) -> str:
    """Plain typography for a model's headline. Changes how a character is drawn, never what the headline says."""
    return headline.translate(_TYPOGRAPHY).strip()


def check_headline(headline: str, page_text: str) -> list[str]:
    """Why this headline may not go on the banner (empty list: it may)."""
    problems: list[str] = []
    if not 1 <= len(headline) <= MAX_HEADLINE:
        problems.append(f"it must be 1 to {MAX_HEADLINE} characters, not {len(headline)}")
    page, low = _fold(page_text), _fold(headline)
    page_digits = set(re.findall(r"\d+", page))
    for run in dict.fromkeys(re.findall(r"\d+", low)):
        if run not in page_digits:
            problems.append(f"the number {run} is not on the page")
    for ch in dict.fromkeys(c for c in headline if unicodedata.category(c) == "Sc"):
        if ch not in page_text:
            problems.append(f"the currency symbol {ch} is not on the page")
    for code in dict.fromkeys(m.upper() for m in CODE_WORD.findall(headline)):
        if not re.search(rf"\b{code}\b", page_text, re.I):
            problems.append(f"the currency code {code} is not on the page")
    for w in CLAIMS:
        if _has_word(w, low) and not _has_word(w, page):
            problems.append(f'the claim word "{w}" is not on the page')
    if URLISH.search(headline):
        problems.append("it contains a link or e-mail address")
    missing = sorted({c for c in headline if not c.isspace() and ord(c) not in _cmap()})
    if missing:
        problems.append(f"the font cannot draw {''.join(missing)}")
    return problems


async def draft_copy(
    provider: Provider | None,
    ledger: Ledger | None,
    facts: FactsResult,
    language: str,
    page_text: str = "",
) -> CopyResult:
    """`page_text` is what headlines are checked against; without it the facts' own quotes stand in."""
    page = page_text or "\n".join(
        f["quote"]
        for f in [facts.product_name or {}, *facts.prices, *facts.features, *facts.legal]
        if f
    )
    name = (facts.product_name or {}).get("text", "")
    legal = next((f["text"] for f in facts.legal if len(f["text"]) <= MAX_LEGAL), "")
    price = facts.prices[0]["text"] if facts.prices else ""
    fixed = dict(price=price, cta=CTA.get(language, CTA_OTHER), legal=legal)
    template = CopyResult("template", [{"id": "c1", "headline": name}], **fixed)
    if not name:
        template.problems.append("The page has no product name; type your headline.")
    if provider is None:
        return template
    payload = {
        "language": language,
        "product_name": name,
        "prices": [p["text"] for p in facts.prices],
        "features": [f["text"] for f in facts.features],
        "legal": [f["text"] for f in facts.legal],
    }
    res = await call_model(
        provider,
        ledger,
        role="campaign_copy",
        prompt=PROMPT,
        payload=payload,
        schema=CopyOut,
        max_tokens=800,
    )
    template.tokens = res.tokens
    if res.parsed is None:
        template.problems.append(f"{res.error or 'no reply'}; the product name is the headline")
        return template
    problems, kept = [], []
    for h in dict.fromkeys(tidy(x) for x in res.parsed.headlines):
        why = check_headline(h, page)
        if why:
            problems.append(f"Rejected \"{h[:60]}\": {'; '.join(why)}.")
        elif len(kept) < MAX_OPTIONS:
            kept.append(h)
    if not kept:
        template.problems += problems
        return template
    opts = [{"id": f"c{i}", "headline": h} for i, h in enumerate(kept, 1)]
    return CopyResult("model", opts, problems=problems, tokens=res.tokens, **fixed)
