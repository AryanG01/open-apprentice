"""Is the banner's price an amount the product page lists? Deterministic, no model.

Deliberately independent: this module parses prices with its own small parser and imports nothing from the agent-visible
packages (campaign/, agent/ ...), like evaluation/campaign_verifier.py. It shows an amount occurs on the page, as a current
or a previous price, and that no other current price sits right after the product's name. It does not prove the offer is
current, that the page is right, or which product a price belongs to when the page does not put the two next to each other."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_SYM = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
_ISO = "USD|EUR|GBP|JPY|INR|CHF|CAD|AUD|SGD|CNY|SEK|NOK|DKK|PLN"
_C = rf"(?:US\$|[$€£¥₹]|(?:{_ISO})(?![A-Za-z]))"
_N = r"\d{1,3}(?:[.,   ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_WITH_CUR = re.compile(rf"(?:(?P<a>{_C})\s?(?P<x>{_N})|(?P<y>{_N})\s?(?P<b>{_C}))")
_BARE = re.compile(rf"(?<![\d.,])(?P<x>{_N})(?![\d])")


def _decimal(raw: str) -> Decimal | None:
    s = re.sub(r"[   ]", "", raw)
    marks = [i for i, c in enumerate(s) if c in ".,"]
    if marks:
        last = marks[-1]
        kinds = {s[i] for i in marks}
        tail = len(s) - last - 1
        decimal_here = len(kinds) == 2 or (len(marks) == 1 and tail != 3)
        if decimal_here:
            s = re.sub(r"[.,]", "", s[:last]) + "." + s[last + 1 :]
        else:
            s = re.sub(r"[.,]", "", s)
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _prices(text: str, allow_bare: bool = False) -> list[tuple[str, Decimal, str | None]]:
    """[(as written, amount, currency or None)] in reading order."""
    found = []
    for m in _WITH_CUR.finditer(text):
        cur = m.group("a") or m.group("b")
        amount = _decimal(m.group("x") or m.group("y"))
        if amount is not None:
            found.append((m.group(0).strip(), amount, _SYM.get(cur, cur.upper())))
    if not found and allow_bare:
        for m in _BARE.finditer(text):
            amount = _decimal(m.group("x"))
            if amount is not None:
                found.append((m.group(0), amount, None))
    return found


def _texts(scene: dict, role: str) -> str:
    return " ".join(str(n.get("text", "")) for n in scene.get("nodes", []) if n.get("role") == role)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


_PREVIOUS = re.compile(
    r"(?:\bwas|\bbefore|\bprevious(?:ly)?|\bregular|\boriginal|\bformerly|\binstead of|\bstatt|\bavant|\bantes)\W{0,3}$",
    re.I,
)


def _is_previous(text: str, start: int) -> bool:
    """Is the amount starting at `start` introduced as an old price ("was $229", "statt 249 €")?"""
    return _PREVIOUS.search(text[max(0, start - 14) : start]) is not None


def _on_page(amount: Decimal, cur: str | None, page: list[tuple[str, Decimal, str | None]]) -> bool:
    return any(amount == a and (cur is None or c is None or cur == c) for _, a, c in page)


def _flagged(text: str, allow_bare: bool = False) -> list[tuple[Decimal, str | None, bool]]:
    """[(amount, currency, is_previous)] with the position of each amount in reading order."""
    out = []
    for m in _WITH_CUR.finditer(text):
        cur = m.group("a") or m.group("b")
        amount = _decimal(m.group("x") or m.group("y"))
        if amount is not None:
            out.append((amount, _SYM.get(cur, cur.upper()), _is_previous(text, m.start())))
    if not out and allow_bare:
        for m in _BARE.finditer(text):
            amount = _decimal(m.group("x"))
            if amount is not None:
                out.append((amount, None, _is_previous(text, m.start())))
    return out


def _same_kind(
    banner: tuple[Decimal, str | None, bool], page: list[tuple[Decimal, str | None, bool]]
) -> bool:
    a, c, prev = banner
    return any(
        a == pa and (c is None or pc is None or c == pc) and prev == pp for pa, pc, pp in page
    )


def _beside_name(name: str, page_text: str) -> list[Decimal]:
    """The current price right after each place the page writes `name` (a product named in the banner's headline)."""
    out = []
    for m in re.finditer(re.escape(name), page_text, re.I):
        nxt = [f for f in _flagged(page_text[m.end() : m.end() + 160]) if not f[2]]
        if nxt:
            out.append(nxt[0][0])
    return out


def check_page(scene: dict, page_text: str) -> dict:
    banner = _prices(_texts(scene, "price"), allow_bare=True)
    page = _prices(page_text)
    b_txt, p_txt = _unique([t for t, _, _ in banner]), _unique([t for t, _, _ in page])
    notes: list[str] = []
    hp = _prices(_texts(scene, "headline"))
    head = [t for t, _, _ in hp]
    if any(not _on_page(a, c, page) for _, a, c in hp):
        notes.append(f"The headline mentions {', '.join(head)}, which is not a price on the page.")
    if not banner:
        return _out("unknown", b_txt, p_txt, None, "The banner has no price to compare.", notes)
    if not page:
        return _out("unknown", b_txt, p_txt, None, "No price was found on the page.", notes)
    page_flags = _flagged(page_text)
    banner_flags = _flagged(_texts(scene, "price"), allow_bare=True)
    missing = [t for t, a, c in banner if not _on_page(a, c, page)]
    # An amount that is on the page only as an old price, or only the other way round, is not the banner's price.
    mismatched_kind = [
        t
        for (t, *_), f in zip(banner, banner_flags)
        if t not in missing and not _same_kind(f, page_flags)
    ]
    name = _texts(scene, "headline").strip()
    beside = _beside_name(name, page_text) if len(name) >= 3 else []
    current = [f for f in banner_flags if not f[2]]
    if beside and current and not any(f[0] in beside for f in current):
        shown = ", ".join(sorted({str(b) for b in beside}))
        detail = (
            f"The page lists {shown} next to \"{name}\", not the banner price {', '.join(b_txt)}."
        )
        return _out("mismatch", b_txt, p_txt, False, detail, notes)
    if mismatched_kind:
        detail = (
            f"The banner shows {', '.join(_unique(mismatched_kind))} as a current price (or an old one) but the page lists it "
            "the other way round."
        )
        return _out("mismatch", b_txt, p_txt, False, detail, notes)
    word = "price" if len(b_txt) == 1 else "prices"
    if missing:
        detail = (
            f"The banner {word} {', '.join(b_txt)}: {', '.join(_unique(missing))} "
            f"{'is' if len(set(missing)) == 1 else 'are'} not on the page, which lists {', '.join(p_txt)}."
        )
        return _out("mismatch", b_txt, p_txt, False, detail, notes)
    verb = "is" if len(b_txt) == 1 else "are"
    return _out(
        "match",
        b_txt,
        p_txt,
        True,
        f"The banner {word} {', '.join(b_txt)} {verb} listed on the page.",
        notes,
    )


def _out(
    status: str, banner: list[str], page: list[str], ok: bool | None, detail: str, notes: list[str]
) -> dict:
    row = {
        "field": "price",
        "scope": "amount_on_page",  # an amount occurs on the page; not a check of the current offer or of the product it belongs to
        "banner": banner,
        "page": page,
        "ok": ok,
        "detail": detail,
    }
    return {"status": status, "rows": [row], "notes": notes}
