"""Does the banner's price agree with the product page the owner pointed to? Deterministic, no model.

Deliberately independent: this module parses prices with its own small parser and imports nothing from the agent-visible
packages (campaign/, agent/ ...), like evaluation/campaign_verifier.py. It proves the banner agrees with the page, not that
the page is right."""

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


def _on_page(amount: Decimal, cur: str | None, page: list[tuple[str, Decimal, str | None]]) -> bool:
    return any(amount == a and (cur is None or c is None or cur == c) for _, a, c in page)


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
    missing = [t for t, a, c in banner if not _on_page(a, c, page)]
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
        f"The banner {word} {', '.join(b_txt)} {verb} on the page.",
        notes,
    )


def _out(
    status: str, banner: list[str], page: list[str], ok: bool | None, detail: str, notes: list[str]
) -> dict:
    row = {"field": "price", "banner": banner, "page": page, "ok": ok, "detail": detail}
    return {"status": status, "rows": [row], "notes": notes}
