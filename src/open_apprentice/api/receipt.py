"""The change receipt: a record of what the independent checker measured on a finished story card, with hashes so the record can be
checked against the files without trusting the app (`scripts/verify_receipt.py`). It is a tamper-evident record, not a proof that the
card looks right or that the page it was checked against is true. Also the "try to break it" mutations: a copy of the finished
result with one defect injected, run through the same verifier."""

from __future__ import annotations

import base64
import copy
import datetime
import hashlib
import json
import os
from typing import Any

SCHEMA = "open-apprentice-change-receipt/1"
LIMITS_NOTE = [
    "The checks are structural: copy, link, logo, image proportions, safe areas, minimum sizes, text fit, overlaps.",
    "They do not look inside the pictures; the picture clean-up is done in the browser before the build and is not part of this record.",
    "A price found on a page is an amount that occurs there, not proof of today's offer.",
    "The record matches the files by hash; it does not prove the card looks good.",
]
COPY_ROLES = ("headline", "price", "legal")


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _png_bytes(data_url: str) -> bytes:
    prefix = "data:image/png;base64,"
    return base64.b64decode(data_url[len(prefix) :]) if data_url.startswith(prefix) else b""


def _strings(scene: dict) -> dict[str, str]:
    nodes = scene["nodes"]
    out = {
        n["role"]: n["text"]
        for n in nodes
        if n.get("role") in COPY_ROLES and n.get("type") == "text"
    }
    cta = next((n for n in nodes if n.get("role") == "cta"), None)
    if cta:
        label = next(
            (k for k in nodes if k.get("parent") == cta["id"] and k.get("type") == "text"), None
        )
        if label:
            out["cta_label"] = label["text"]
    return out


def _link(scene: dict) -> str | None:
    cta = next((n for n in scene["nodes"] if n.get("role") == "cta"), None)
    return cta.get("link") if cta else None


def build_receipt(
    *,
    source: dict,
    native: dict,
    png_data_url: str,
    verification: dict,
    choice: dict,
    page_check: dict | None = None,
    reading_origin: str = "",
) -> dict:
    want, got = _strings(source), _strings(native)
    png = _png_bytes(png_data_url)
    pictures = {}
    for aid, url in sorted((source.get("assets") or {}).items()):
        data = _png_bytes(url) if isinstance(url, str) else b""
        pictures[aid] = {"sha256": hashlib.sha256(data).hexdigest() if data else None, "bytes": len(data)}
    body = {
        "schema": SCHEMA,
        "created_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "app_commit": os.environ.get("APP_COMMIT", "unknown"),
        "what_this_is": "A record of what the independent checker measured on this result, tied to the files by hash.",
        "reading": {"origin": reading_origin or "unknown"},
        "approved_text": {
            k: {"text": v, "sha256": sha256_text(v)} for k, v in sorted(want.items())
        },
        "result_text": {
            k: {"text": v, "sha256": sha256_text(v), "identical_to_approved": want.get(k) == v}
            for k, v in sorted(got.items())
        },
        "link": {"approved": _link(source), "result": _link(native), "identical": _link(source) == _link(native)},
        "pictures": pictures,
        "result": {
            "cards": sum(1 for n in native["nodes"] if n.get("type") == "artboard"),
            "png_sha256": hashlib.sha256(png).hexdigest() if png else None,
        },
        "choice": choice,
        "checks": verification.get("checks", []),
        "all_checks_passed": bool(verification.get("passed")),
        "page_check": page_check,
        "limits": LIMITS_NOTE,
    }
    body["receipt_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    return body


def mutate(native: dict, name: str) -> dict:
    """A copy of the finished result with one defect injected (never touches the stored result)."""
    out = copy.deepcopy(native)
    nodes = out["nodes"]
    first = lambda role: next((n for n in nodes if n.get("role") == role), None)  # noqa: E731
    if name == "delete_product":
        out["nodes"] = [n for n in nodes if n.get("role") != "product_image"]
    elif name == "change_price":
        p = first("price")
        if p is None:
            raise KeyError("no price on this banner")
        digits = [i for i, c in enumerate(p["text"]) if c.isdigit()]
        if digits:
            i = digits[0]
            p["text"] = p["text"][:i] + str((int(p["text"][i]) + 1) % 10) + p["text"][i + 1 :]
        else:
            p["text"] += "0"
    elif name == "push_headline_out":
        h = first("headline")
        if h is None:
            raise KeyError("no headline")
        h["x"] = 1075
    else:
        raise KeyError(name)
    return out


MUTATIONS = {
    "delete_product": "Delete the product picture",
    "change_price": "Change a digit of the price",
    "push_headline_out": "Push the headline off the card",
}
