"""Facts lifted from a product page. Nemotron proposes, a deterministic check disposes: a fact survives only when its quote
is in the page text and its words are inside that quote. Price amounts and currencies are parsed from the text here, never
taken from the model."""

from __future__ import annotations

import pathlib
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from pydantic import Field

from open_apprentice.budget import Ledger
from open_apprentice.campaign.model import call_model
from open_apprentice.providers.base import Provider, StrictModel

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "campaign_facts.md"
MAX_PRICES, MAX_FEATURES, MAX_LEGAL = 6, 4, 2
MODEL_TEXT_CHARS = 12_000  # what the model reads; grounding is checked against the whole page
SYMBOLS = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
CODES = (
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "INR",
    "CHF",
    "CAD",
    "AUD",
    "SGD",
    "CNY",
    "SEK",
    "NOK",
    "DKK",
    "PLN",
)
_CUR = r"(?:US\$|\$|€|£|¥|₹|" + "|".join(CODES) + r")"
_NUM = r"\d{1,3}(?:[.,   ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
PRICE = re.compile(rf"(?P<c1>{_CUR})\s?(?P<n1>{_NUM})|(?P<n2>{_NUM})\s?(?P<c2>{_CUR})(?![A-Za-z])")


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).casefold()
    t = re.sub(r"[*_\[\]()#>]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def is_grounded(quote: str, page_text: str) -> bool:
    q = normalise(quote)
    return bool(q) and q in normalise(page_text)


def _amount(num: str) -> Decimal | None:
    s = re.sub(r"[   ]", "", num)
    dot, comma = s.rfind("."), s.rfind(",")
    if dot >= 0 and comma >= 0:  # both: the later one is the decimal mark
        dec = "." if dot > comma else ","
    else:
        sep = "." if dot >= 0 else "," if comma >= 0 else ""
        # one kind of mark: several, or exactly three digits after it, means thousands ("1,299", "1.299")
        dec = sep if sep and s.count(sep) == 1 and len(s) - s.rfind(sep) - 1 != 3 else ""
    thousands = "," if dec == "." else "."
    s = s.replace(thousands, "") if dec else s.replace(".", "").replace(",", "")
    s = s.replace(dec, ".") if dec else s
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_price(text: str) -> tuple[Decimal, str] | None:
    """(amount, ISO currency) of the first price in `text`, or None when there is no amount with a currency."""
    m = PRICE.search(text)
    if not m:
        return None
    cur = m.group("c1") or m.group("c2")
    amount = _amount(m.group("n1") or m.group("n2"))
    return None if amount is None else (amount, SYMBOLS.get(cur, cur))


def _price_fact(text: str, quote: str) -> dict | None:
    p = parse_price(text)
    if p is None:
        return None
    return {"text": text, "quote": quote, "amount": f"{p[0]:.2f}", "currency": p[1]}


@dataclass
class FactsResult:
    language: str
    product_name: dict | None
    prices: list[dict]
    features: list[dict]
    legal: list[dict]
    origin: str  # model | baseline
    problems: list[str] = field(default_factory=list)
    tokens: int = 0

    def as_dict(self) -> dict:
        return {
            "product_name": self.product_name,
            "prices": self.prices,
            "features": self.features,
            "legal": self.legal,
        }


class Fact(StrictModel):
    text: str = Field(max_length=300)
    quote: str = Field(max_length=500)


class FactsOut(StrictModel):
    language: str = "en"
    product_name: Fact | None = None
    prices: list[Fact] = Field(default_factory=list, max_length=20)
    features: list[Fact] = Field(default_factory=list, max_length=20)
    legal: list[Fact] = Field(default_factory=list, max_length=20)


_STOP = {
    "de": ("und", "der", "die", "das", "mit", "für", "jetzt", "statt", "bis", "nicht"),
    "fr": ("et", "le", "la", "les", "avec", "pour", "jusqu", "des", "une", "sans"),
    "es": ("y", "el", "los", "las", "con", "para", "una", "hasta", "por", "ahora"),
}


def guess_language(text: str) -> str:
    words = re.findall(r"[a-zà-ÿ]+", text.casefold())
    score = {k: sum(w in v for w in words) for k, v in _STOP.items()}
    best = max(score, key=score.get)
    return best if score[best] >= 3 else "en"


def baseline_facts(page_text: str) -> FactsResult:
    """No model: the first H1 as the product name, every price pattern on the page, no features."""
    lines = page_text.split("\n")
    name = None
    for ln in lines:
        m = re.match(r"^#\s+(.+?)\s*#*\s*$", ln.strip())
        if m:
            name = {"text": m.group(1), "quote": m.group(1)}
            break
    prices, seen = [], set()
    for ln in lines:
        for m in PRICE.finditer(ln):
            t = m.group(0).strip()
            if t in seen or len(prices) >= MAX_PRICES:
                continue
            seen.add(t)
            f = _price_fact(t, ln.strip()[:300])
            if f:
                prices.append(f)
    problems = [] if prices else ["No price was found on this page."]
    return FactsResult(guess_language(page_text), name, prices, [], [], "baseline", problems)


_BULLET = re.compile(r"^\s*(?:[-*+\u2022])\s+(.+?)\s*$")
_NOT_A_FEATURE = re.compile(r"\b(terms|offer ends|while stocks|valid until|all rights)\b", re.I)


def page_bullets(page_text: str) -> list[dict]:
    """The page's own list items as features: grounded by construction (the quote is the line), used only when the model
    found no feature. Price lines and legal-sounding lines are left out."""
    out: list[dict] = []
    for ln in page_text.split("\n"):
        m = _BULLET.match(ln)
        if not m:
            continue
        t = re.sub(r"[*_`]+", "", m.group(1)).strip()
        if (
            3 <= len(t) <= 80
            and not PRICE.search(t)
            and not _NOT_A_FEATURE.search(t)
            and len(out) < MAX_FEATURES
        ):
            out.append({"text": t, "quote": ln.strip()})
    return out


def _keep(
    items: list[Fact], page: str, cap: int, label: str, problems: list[str], price: bool = False
) -> list[dict]:
    kept: list[dict] = []
    for f in items:
        if not is_grounded(f.quote, page):
            problems.append(f'Dropped {label} "{f.text[:60]}": its quote is not on the page.')
        elif normalise(f.text) not in normalise(f.quote):
            problems.append(f'Dropped {label} "{f.text[:60]}": its words are not inside its quote.')
        elif price and (d := _price_fact(f.text, f.quote)) is None:
            problems.append(f'Dropped {label} "{f.text[:60]}": no amount with a currency.')
        elif len(kept) < cap:
            kept.append(d if price else {"text": f.text, "quote": f.quote})
    return kept


async def extract_facts(
    provider: Provider | None, ledger: Ledger | None, page_text: str
) -> FactsResult:
    base = baseline_facts(page_text)
    if provider is None:
        return base
    res = await call_model(
        provider,
        ledger,
        role="campaign_facts",
        prompt=PROMPT,
        payload={"page_text": page_text[:MODEL_TEXT_CHARS]},
        schema=FactsOut,
        max_tokens=1500,
    )
    if res.parsed is None:
        base.problems.insert(0, f"{res.error or 'no reply'}; the page's own prices are shown")
        base.tokens = res.tokens
        return base
    out: FactsOut = res.parsed
    problems: list[str] = []
    name_list = _keep(
        [out.product_name] if out.product_name else [], page_text, 1, "product name", problems
    )
    prices = _keep(out.prices, page_text, MAX_PRICES, "price", problems, price=True)
    if (
        not prices
    ):  # the deterministic reading of the page's own text is as grounded as a fact can be
        prices = base.prices
    if not prices:
        problems.append("No price was found on this page.")
    lang = out.language.lower()[:2]
    return FactsResult(
        lang if re.fullmatch(r"[a-z]{2}", lang) else base.language,
        name_list[0] if name_list else base.product_name,
        prices,
        _keep(out.features, page_text, MAX_FEATURES, "feature", problems)
        or page_bullets(page_text),
        _keep(out.legal, page_text, MAX_LEGAL, "legal line", problems),
        "model",
        problems,
        res.tokens,
    )
