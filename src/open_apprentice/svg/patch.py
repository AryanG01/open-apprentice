"""Typed, whitelisted `set_attribute` patch against ONE specific document (spec 6.8).

Each op names the document hash, the element id, the attribute, the expected old value and the new value. Stale hashes or values, duplicate or conflicting writes, values outside
the whitelist and edits to shared definitions are REJECTED, and the patch is transactional: either every op applies or none does. Applying edits the original bytes only
inside the targeted start tags, then PROVES that nothing else changed.
"""

from __future__ import annotations

import math
import re
from typing import Optional

from pydantic import BaseModel, Field

from open_apprentice.svg.document import Document, doc_hash, parse_document, parse_translate

MAX_OPS = 50
LIMIT = 100_000.0
NAMED = {
    "none",
    "black",
    "white",
    "red",
    "green",
    "blue",
    "gray",
    "grey",
    "orange",
    "purple",
    "yellow",
    "currentColor",
}
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
WHITELIST = {"rect": {"x", "y", "width", "height", "fill", "stroke", "stroke-width", "transform"}}


class Op(BaseModel):
    element: str = Field(max_length=100)
    attribute: str = Field(max_length=40)
    expected_old: Optional[str] = Field(default=None, max_length=200)
    new: str = Field(max_length=200)


class Patch(BaseModel):
    doc_hash: str = Field(min_length=64, max_length=64)
    ops: list[Op] = Field(max_length=MAX_OPS)


class PatchRejected(ValueError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def fmt(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _number(v: str) -> Optional[float]:
    try:
        f = float(v)
    except ValueError:
        return None
    return f if math.isfinite(f) and abs(f) <= LIMIT else None


def valid_value(attribute: str, value: str) -> Optional[str]:
    """None if acceptable, else the reason."""
    if attribute in ("x", "y"):
        return None if _number(value) is not None else "must be a plain number within +/-100000"
    if attribute in ("width", "height"):
        n = _number(value)
        return None if n is not None and n >= 0 else "must be a plain non-negative number"
    if attribute == "stroke-width":
        n = _number(value)
        return None if n is not None and 0 <= n <= 100 else "must be a number between 0 and 100"
    if attribute in ("fill", "stroke"):
        return (
            None
            if _HEX.match(value) or value in NAMED
            else "must be a #hex colour or a short named colour (no url(), no references)"
        )
    if attribute == "transform":
        return (
            None
            if parse_translate(value) is not None and value.strip().startswith("translate")
            else "only a plain translate(x y) is allowed"
        )
    return "attribute is not on the whitelist"


# ------------------------------------------------------------------------------------------------- byte-exact tag editing
def _tokenise_tag(tag: bytes) -> tuple[int, list[tuple[bytes, int, int, bytes]], int]:
    """-> (offset after the tag name, [(name, value_start, value_end, quote)], offset of the closing '/>' or '>')."""
    i = 1
    while i < len(tag) and tag[i : i + 1] not in b" \t\r\n/>":
        i += 1
    name_end, attrs = i, []
    while i < len(tag):
        while i < len(tag) and tag[i : i + 1] in b" \t\r\n":
            i += 1
        if tag[i : i + 1] in (b"/", b">"):
            break
        n0 = i
        while tag[i : i + 1] not in b"= \t\r\n":
            i += 1
        name = tag[n0:i]
        while tag[i : i + 1] in b" \t\r\n":
            i += 1
        i += 1  # '='
        while tag[i : i + 1] in b" \t\r\n":
            i += 1
        q = tag[i : i + 1]
        v0 = i + 1
        i = tag.index(q, v0)
        attrs.append((name, v0, i, q))
        i += 1
    return name_end, attrs, i


def edit_tag(tag: bytes, changes: dict[str, str]) -> bytes:
    _, attrs, close = _tokenise_tag(tag)
    spans = {a[0].decode(): a for a in attrs}
    out, last = bytearray(), 0
    for name, (_, v0, v1, _q) in sorted(
        ((n, spans[n]) for n in changes if n in spans), key=lambda kv: kv[1][1]
    ):
        out += tag[last:v0] + changes[name].encode() + b""
        last = v1
    out += tag[last:]
    new_attrs = [n for n in changes if n not in spans]
    if new_attrs:
        # insert before the closing marker, after trimming whitespace that precedes it
        _, attrs2, close2 = _tokenise_tag(bytes(out))
        body = bytes(out)
        cut = close2
        while cut > 0 and body[cut - 1 : cut] in b" \t\r\n":
            cut -= 1
        add = b"".join(f' {n}="{changes[n]}"'.encode() for n in new_attrs)
        body = body[:cut] + add + body[cut:]
        return body
    return bytes(out)


class PatchResult(BaseModel):
    text: str
    hash_before: str
    hash_after: str
    diff: list[dict]
    unrelated_byte_changes: int
    scope: str


def apply_patch(text: str, patch: Patch) -> PatchResult:
    doc: Document = parse_document(text)
    reasons: list[str] = []
    if patch.doc_hash != doc.hash:
        reasons.append("stale patch: it was written for a different version of the document")
    seen: set[tuple[str, str]] = set()
    per_element: dict[int, dict[str, str]] = {}
    diff: list[dict] = []
    for n, op in enumerate(patch.ops):
        tag = f"op {n} ({op.element}.{op.attribute})"
        if (op.element, op.attribute) in seen:
            reasons.append(f"{tag}: duplicate or conflicting write")
            continue
        seen.add((op.element, op.attribute))
        if op.element not in doc.by_id:
            reasons.append(f"{tag}: no element with that id")
            continue
        e = doc.get(op.element)
        if e.in_defs:
            reasons.append(f"{tag}: shared definitions are not editable")
            continue
        if e.tag not in WHITELIST or op.attribute not in WHITELIST[e.tag]:
            reasons.append(
                f"{tag}: <{e.tag}> {op.attribute!r} is not an editable attribute in this lane"
            )
            continue
        bad = valid_value(op.attribute, op.new)
        if bad:
            reasons.append(f"{tag}: value {op.new!r} {bad}")
            continue
        if e.attrs.get(op.attribute) != op.expected_old:
            reasons.append(
                f"{tag}: stale value, the document currently has {e.attrs.get(op.attribute)!r}, the patch expected {op.expected_old!r}"
            )
            continue
        per_element.setdefault(e.index, {})[op.attribute] = op.new
        diff.append(
            {
                "element": op.element,
                "attribute": op.attribute,
                "old": op.expected_old,
                "new": op.new,
            }
        )
    if reasons:
        raise PatchRejected(reasons)  # transactional: nothing was applied

    raw = text.encode("utf-8")
    pieces, last, delta, new_spans = [], 0, 0, []
    for idx in sorted(per_element, key=lambda i: doc.elements[i].start):
        e = doc.elements[idx]
        new_tag = edit_tag(raw[e.start : e.end], per_element[idx])
        pieces += [raw[last : e.start], new_tag]
        new_spans.append((e.start + delta, e.start + delta + len(new_tag)))
        delta += len(new_tag) - (e.end - e.start)
        last = e.end
    pieces.append(raw[last:])
    new_raw = b"".join(pieces)
    # PROOF of "no unrelated changes": everything outside the edited start tags is byte-identical
    out_old = b"".join(raw[a:b] for a, b in zip([0] + [doc.elements[i].end for i in sorted(per_element, key=lambda i: doc.elements[i].start)],
                                                  [doc.elements[i].start for i in sorted(per_element, key=lambda i: doc.elements[i].start)] + [len(raw)]))  # fmt: skip
    out_new = b"".join(
        new_raw[a:b]
        for a, b in zip([0] + [s[1] for s in new_spans], [s[0] for s in new_spans] + [len(new_raw)])
    )
    unrelated = 0 if out_old == out_new else abs(len(out_old) - len(out_new)) + 1
    new_text = new_raw.decode("utf-8")
    after = parse_document(
        new_text
    )  # the result must itself be a valid, accepted document with the same elements
    if len(after.elements) != len(doc.elements) or unrelated:
        raise PatchRejected(
            [
                "internal check failed: the edit changed more than the targeted attributes; nothing was applied"
            ]
        )
    for e0, e1 in zip(doc.elements, after.elements):
        expected = {**e0.attrs, **per_element.get(e0.index, {})}
        if e1.attrs != expected:
            raise PatchRejected(
                [
                    "internal check failed: an attribute outside the patch changed; nothing was applied"
                ]
            )
    return PatchResult(
        text=new_text, hash_before=doc.hash, hash_after=doc_hash(new_text), diff=diff, unrelated_byte_changes=unrelated,
        scope="checked: every byte outside the edited start tags, and every other attribute of every element, is identical to the original. Rendered geometry is verified separately.",
    )  # fmt: skip
