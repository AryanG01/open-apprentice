"""Hardened .drawio reader (spec 6). Every refusal is a DrawioRefused whose message is shown to the user. Nothing here renders,
fetches or evaluates anything: it only reads bytes with expat and returns page models plus exact byte spans for the patcher."""

from __future__ import annotations

import base64
import hashlib
import urllib.parse
import xml.parsers.expat as expat
import zlib
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional

MAX_UPLOAD = 2 * 1024 * 1024
MAX_DECODED = 4 * 1024 * 1024
MAX_DEPTH = 32
MAX_CELLS = 2000
MAX_VALUE = 4000
HTML_TAGS = frozenset(
    {"b", "i", "u", "br", "span", "div", "font", "p", "strong", "em", "sub", "sup"}
)
HTML_ATTRS = frozenset({"style", "color", "face", "size", "align"})


class DrawioRefused(ValueError):
    """The document (or one page of it) was refused; the message says why in plain language."""


@dataclass(frozen=True)
class Cell:
    id: str
    parent: str
    vertex: bool
    edge: bool
    style: dict[str, str]
    value: str
    geometry: dict[str, str]
    geometry_span: Optional[
        tuple[int, int]
    ]  # byte span of the <mxGeometry ...> start tag in Page.xml
    wrapper: bool


@dataclass(frozen=True)
class Page:
    index: int
    id: str
    name: str
    compressed: bool
    xml: bytes  # the page's mxGraphModel XML (decoded for compressed pages)
    content_span: tuple[
        int, int
    ]  # in the file: the inline <mxGraphModel> element, or the base64 text
    model: dict[str, str]
    cells: tuple[Cell, ...]


@dataclass(frozen=True)
class DrawioFile:
    raw: bytes
    doc_hash: str
    pages: tuple[Page, ...]


def parse_style(style: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in style.split(";"):
        if part:
            k, _, v = part.partition("=")
            out[k] = v
    return out


class _LabelHtml(HTMLParser):
    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag not in HTML_TAGS or any(a not in HTML_ATTRS for a, _ in attrs):
            raise DrawioRefused(f"unsupported label content: <{tag}> with {[a for a, _ in attrs]}")
        if any("url(" in (v or "").lower() or "expression" in (v or "").lower() for _, v in attrs):
            raise DrawioRefused("unsupported label content: styles that load resources")


def _check_label_html(value: str) -> None:
    p = _LabelHtml(convert_charrefs=True)
    p.feed(value)
    p.close()


def _parser() -> expat.XMLParserType:
    p = expat.ParserCreate("UTF-8")
    p.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)

    def refuse(*_: object) -> None:
        raise DrawioRefused("DOCTYPE and entity declarations are not accepted")

    p.StartDoctypeDeclHandler = refuse
    p.EntityDeclHandler = refuse
    return p


def _tag_end(raw: bytes, start: int) -> int:
    return raw.index(b">", start) + 1


def _decode(text: bytes) -> bytes:
    try:
        data = base64.b64decode(b"".join(text.split()), validate=True)
        d = zlib.decompressobj(-15)
        out = d.decompress(data, MAX_DECODED + 1)
    except (ValueError, zlib.error) as e:
        raise DrawioRefused(f"a compressed page could not be decoded ({e})") from e
    if len(out) > MAX_DECODED or d.unconsumed_tail:
        raise DrawioRefused("a compressed page decodes to more than 4 MB")
    try:
        return urllib.parse.unquote(out.decode("ascii"), errors="strict").encode("utf-8")
    except UnicodeError as e:
        raise DrawioRefused("a compressed page is not valid UTF-8") from e


def compress_page_xml(xml: bytes) -> str:
    """draw.io's page encoding: base64(raw deflate(encodeURIComponent(xml)))."""
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    quoted = urllib.parse.quote(xml.decode("utf-8"), safe="~()*!.'").encode("ascii")
    return base64.b64encode(c.compress(quoted) + c.flush()).decode("ascii")


@dataclass
class _Diagram:
    id: str
    name: str
    text_start: int
    model_start: Optional[int] = None
    model_end: Optional[int] = None


def _diagrams(raw: bytes) -> list[tuple[str, str, bool, int, int]]:
    """(id, name, compressed, start, end) of each diagram's content in the file."""
    found: list[tuple[str, str, bool, int, int]] = []
    cur: list[_Diagram] = []
    depth = 0
    p = _parser()

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth
        depth += 1
        if depth > MAX_DEPTH:
            raise DrawioRefused("the document nests too deeply")
        if name == "diagram":
            cur.append(
                _Diagram(
                    attrs.get("id", ""), attrs.get("name", ""), _tag_end(raw, p.CurrentByteIndex)
                )
            )
        elif name == "mxGraphModel" and cur and cur[-1].model_start is None:
            cur[-1].model_start = p.CurrentByteIndex

    def end(name: str) -> None:
        nonlocal depth
        depth -= 1
        if not cur:
            return
        d = cur[-1]
        if name == "mxGraphModel" and d.model_start is not None and d.model_end is None:
            d.model_end = _tag_end(raw, p.CurrentByteIndex)
        elif name == "diagram":
            cur.pop()
            if d.model_start is not None and d.model_end is not None:
                found.append((d.id, d.name, False, d.model_start, d.model_end))
            else:
                found.append((d.id, d.name, True, d.text_start, p.CurrentByteIndex))

    p.StartElementHandler = start
    p.EndElementHandler = end
    try:
        p.Parse(raw, True)
    except expat.ExpatError as e:
        raise DrawioRefused(f"the file is not well-formed XML ({e})") from e
    if not found:
        raise DrawioRefused("the file has no pages")
    return found


@dataclass
class _Rec:
    attrs: dict[str, str]
    wrapper: Optional[dict[str, str]]
    geometry: dict[str, str] = field(default_factory=dict)
    span: Optional[tuple[int, int]] = None


def _cells(xml: bytes) -> tuple[dict[str, str], tuple[Cell, ...]]:
    model: dict[str, str] = {}
    recs: list[_Rec] = []
    stack: list[_Rec] = []
    wrapper: list[dict[str, str]] = []
    depth = 0
    p = _parser()

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth
        depth += 1
        if depth > MAX_DEPTH:
            raise DrawioRefused("the page nests too deeply")
        if name == "mxGraphModel" and not model:
            model.update(attrs)
        elif name in ("UserObject", "object"):
            for (
                k,
                v,
            ) in attrs.items():  # placeholders can substitute any wrapper attribute into a label
                if "<" in v:
                    _check_label_html(v)
            wrapper.append({"id": attrs.get("id", ""), "value": attrs.get("label", "")})
        elif name == "mxCell":
            rec = _Rec(dict(attrs), wrapper[-1] if wrapper else None)
            recs.append(rec)
            stack.append(rec)
            if len(recs) > MAX_CELLS:
                raise DrawioRefused(f"the page has more than {MAX_CELLS} cells")
        elif (
            name == "mxGeometry"
            and stack
            and attrs.get("as") == "geometry"
            and stack[-1].span is None
        ):
            s = p.CurrentByteIndex
            stack[-1].geometry = dict(attrs)
            stack[-1].span = (s, _tag_end(xml, s))

    def end(name: str) -> None:
        nonlocal depth
        depth -= 1
        if name == "mxCell" and stack:
            stack.pop()
        elif name in ("UserObject", "object") and wrapper:
            wrapper.pop()

    p.StartElementHandler = start
    p.EndElementHandler = end
    try:
        p.Parse(xml, True)
    except expat.ExpatError as e:
        raise DrawioRefused(f"a page is not well-formed XML ({e})") from e
    out: list[Cell] = []
    seen: set[str] = set()
    for r in recs:
        cid = r.wrapper["id"] if r.wrapper else r.attrs.get("id", "")
        value = r.wrapper["value"] if r.wrapper else r.attrs.get("value", "")
        if not cid:
            raise DrawioRefused("a cell has no id")
        if cid in seen:
            raise DrawioRefused(f"duplicate cell id {cid!r}")
        if len(value) > MAX_VALUE:
            raise DrawioRefused(f"cell {cid!r} has a label longer than {MAX_VALUE} characters")
        seen.add(cid)
        style = parse_style(r.attrs.get("style", ""))
        if style.get("html") == "1" and "<" in value:
            _check_label_html(value)
        out.append(
            Cell(
                cid,
                r.attrs.get("parent", ""),
                r.attrs.get("vertex") == "1",
                r.attrs.get("edge") == "1",
                style,
                value,
                r.geometry,
                r.span,
                r.wrapper is not None,
            )
        )
    parents = {c.id: c.parent for c in out}
    for c in out:
        if c.parent and c.parent not in seen:
            raise DrawioRefused(f"cell {c.id!r} has an unknown parent {c.parent!r}")
    for c in out:
        cur, steps = c.id, 0
        while parents.get(cur):
            cur, steps = parents[cur], steps + 1
            if cur == c.id or steps > MAX_DEPTH:
                raise DrawioRefused(f"cell {c.id!r} has a cyclic or too deep parent chain")
    return model, tuple(out)


def load_drawio(raw: bytes) -> DrawioFile:
    if len(raw) > MAX_UPLOAD:
        raise DrawioRefused(f"the file is {len(raw)} bytes; the limit is 2 MB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise DrawioRefused("the file is not UTF-8") from e
    decl = text[:200].lower().split("?>")[0] if text.startswith("<?xml") else ""
    if "encoding=" in decl and "utf-8" not in decl:
        raise DrawioRefused("the file declares a non-UTF-8 encoding")
    pages = []
    for i, (pid, name, compressed, s, e) in enumerate(_diagrams(raw)):
        xml = _decode(raw[s:e]) if compressed else raw[s:e]
        model, cells = _cells(xml)
        pages.append(Page(i, pid, name, compressed, xml, (s, e), model, cells))
    return DrawioFile(raw, hashlib.sha256(raw).hexdigest(), tuple(pages))


def page_document(page: Page) -> str:
    """One page as an uncompressed <mxfile>, the form the engine's renderer takes. No file text is interpolated outside the
    page XML itself (whose bytes were validated), so a crafted page id cannot inject markup."""
    return f'<mxfile><diagram id="p" name="page">{page.xml.decode("utf-8")}</diagram></mxfile>'
