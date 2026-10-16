# draw.io Adapter and Engine Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn an uploaded `.drawio` file into a measured teaching scene, and turn a program's label targets back into a new, checked
`.drawio` artifact. Publish that artifact only when conformance, preservation and layout safety all pass, each reported separately.

**Architecture:**
- A hardened Python reader (`open_apprentice.drawio`) parses and classifies one page. Rendering and measurement happen in the engine
  service: a new `/drawio/render` route runs the pinned draw.io viewer in a fresh, network-blocked Chromium context, with bundled
  Liberation Sans mapped onto Helvetica.
- Python turns the measurements into exact 1/64 rationals and builds the teaching scene (spec 3.5 object format). It also stores the
  offset `d = box − geometry` per label.
- The patcher writes whole-unit coordinates into the exact `<mxGeometry>` byte spans. Publication re-parses the new file, re-renders it
  and re-measures it before anything is stored.

**Tech Stack:** Python 3.12 (expat, zlib, html.parser, fractions, httpx), Node 22 + Fastify + Playwright Chromium, the draw.io
`viewer-static.min.js` v32.4.1, and Liberation Sans 2.1.5 (SIL OFL 1.1).

**Spec:** `docs/superpowers/specs/2026-10-15-teach-correct-reuse-design.md` (section 6, plus 3.6 tolerance and 10 staging). Spike
evidence: `docs/spikes/2026-10-16-drawio-roundtrip.md`.

## Global Constraints

- Deadline 30 Oct 2026 17:00 UTC. Python 3.12 target, black, type hints, ruff. Conventional commits. No `eval`/`exec`/dynamic code loading.
- Native input and primary output is the `.drawio` file. The SVG is a convenience export. Previews are PNG.
- Editing area: one page, rectangle `(0, 0, pageWidth, pageHeight)`, and `pageScale=1` is required. `page="0"`, other page scales, and
  content outside the rectangle (including negative coordinates) are refused with a reason.
- Parsing: expat. Reject DTDs, entity declarations and external entities. Upload ≤ 2 MB; decompression aborts above 4 MB decoded. UTF-8
  only. Cell IDs must be unique and parents valid. A missing `x`/`y` means 0, and the patcher inserts the attribute. `UserObject`/`object`
  wrappers are never moved; they are kept as obstacles.
- Movable label: `vertex=1`, style `text;`, parent is a layer, absolute geometry, rotation 0, renders on a single line. Limits: ≤ 32
  objects and ≤ 16 movable labels. Edges are preserved, and connector crossings are not checked (every receipt says so).
- Rendering: the pinned viewer (SHA-256 `bc7586cb62eec98018c13b78619078d3a7179cc7bfc711c566dda19527520a30`), scale 1, all network
  blocked. Wait for `document.fonts.ready` plus two animation frames. Liberation Sans (hashes recorded) is mapped onto `Helvetica`; any
  other font family is refused.
- Measurement primitives:
  - HTML label: one `Range` per non-empty text node (union of client rects) plus visible background, border and padding.
  - Fixed shapes: cell-state bounds, cross-checked against the rendered element. A mismatch above 0.5 (after stroke) blocks.
  - Quantum 1/64.
- Arithmetic: target geometry = `target_box − d`. Three values are kept separately: the exact rational target, the serialized coordinate
  (**whole document units, half rounds up**) and the measured result. Conformance tolerance is 0.5 + that rounding error (≤ 0.5).
- Publication: write a new artifact only if every check passes. For uncompressed pages, bytes outside the edited spans are identical. A
  compressed page is written uncompressed, with preservation claimed at model level. Other pages' bytes are identical. The output must
  stay ≤ 2 MB.
- The four checks are separate axes (conformance, preservation, layout safety, intent) and never become one score. `PROVIDER_MODE=mock`
  stays the default, and nothing in this plan calls a paid model.
- No GCP resource is created without the owner's approval of `docs/deploy_staging_proposal.md`.
- **Downloads approved by approving this plan:** Liberation Sans 2.1.5 TTF release from `liberationfonts/liberation-fonts`, and moving
  the already-approved viewer into the engine as a committed vendored file (Apache-2.0; 4.3 MB) so CI and Docker builds need no network.

## Review Focus

1. **Hostile files:** an HTML label with `<img onerror=…>`/`<script>`, a DOCTYPE or entity declaration, or a compressed page that inflates
   past 4 MB must be refused before any rendering, with a reason. The renderer never makes a network request. (Task 2 tests.)
2. **Font substitution wraps a label:** a label that renders on two lines under Liberation Sans must be demoted to an obstacle with a
   reason. It must never be moved, and never cause a crash. (Task 5 test.)
3. **Broken structure:** a missing parent, duplicate IDs, or a geometry-less vertex must be refused or treated as 0 per the spec, never
   cause an HTTP 500 or traceback. (Task 2 tests.)
4. **Stale patch:** if the source bytes changed since measurement (hash mismatch, or an `expected_old` mismatch), the patch is refused and
   nothing is written. (Task 7 test.)
5. **Rounding causes overlap:** a fractional target can round to a whole unit that overlaps a neighbour. The layout-safety check must block
   publication, and the receipt must show the exact target, the serialized value and the measured value separately. (Task 8 test.)

---

## File Structure

| File | Responsibility |
|---|---|
| `services/engine/vendor/drawio/viewer-static.min.js` | pinned viewer (moved from `scripts/spikes/vendor/`, now committed) |
| `services/engine/vendor/fonts/LiberationSans-{Regular,Bold}.ttf` | bundled font files |
| `services/engine/vendor/MANIFEST.json` | file → SHA-256, source, licence |
| `services/engine/src/drawio.js` | render + measure + PNG/SVG of one page in a fresh context |
| `services/engine/src/server.js` (modify) | `POST /drawio/render` |
| `services/engine/src/engine.js` (modify) | `renderDrawio()` using the shared browser; render concurrency cap |
| `services/engine/test/drawio.test.js` | engine-side tests |
| `src/open_apprentice/drawio/__init__.py` | empty |
| `src/open_apprentice/drawio/parse.py` | hardened reader: `load_drawio`, `DrawioFile`, `Page`, `Cell`, `DrawioRefused` |
| `src/open_apprentice/drawio/classify.py` | cell statuses, editing-rectangle and limit refusals |
| `src/open_apprentice/drawio/render.py` | engine client; measurements as Fractions |
| `src/open_apprentice/drawio/mapping.py` | proposed/confirmed label→node mapping sidecar |
| `src/open_apprentice/drawio/scene.py` | teaching scene + offsets from classification, render, mapping |
| `src/open_apprentice/drawio/patch.py` | whole-unit serialization, byte-span patching |
| `src/open_apprentice/drawio/publish.py` | re-parse, re-render, separate checks, receipt, immutable publish |
| `src/open_apprentice/cli.py` (modify) | `oa drawio check`, `oa staging-check` |
| `scripts/drawio/drift_measure.mjs`, `scripts/drawio/drift_report.py` | authoring-Mac drift report (draw.io CLI) |
| `tests/unit/drawio/…`, `tests/integration/drawio/…` | tests per task |
| `pyproject.toml` (modify) | add `open_apprentice.drawio` to the "never import the evaluator" contract |

---

### Task 1: Vendored viewer and font, recorded hashes

**Files:**
- Create: `services/engine/vendor/drawio/viewer-static.min.js` (moved), `services/engine/vendor/fonts/LiberationSans-Regular.ttf`,
  `services/engine/vendor/fonts/LiberationSans-Bold.ttf`, `services/engine/vendor/MANIFEST.json`, `services/engine/test/vendor.test.js`
- Modify: `.gitignore` (drop `scripts/spikes/vendor/*.js`), `scripts/spikes/vendor/README.md` (point at the new path),
  `scripts/spikes/drawio_roundtrip.mjs` usage line, `THIRD_PARTY_NOTICES.md`

**Interfaces:**
- Produces: `services/engine/vendor/MANIFEST.json` = `{"files": {"<relative path>": {"sha256": str, "bytes": int, "source": str, "licence": str}}}`, read by Task 4 for the render profile.

- [ ] **Step 1: Write the failing test** (`services/engine/test/vendor.test.js`)

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const root = new URL("../vendor/", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("MANIFEST.json", root)));

test("every vendored file matches its recorded hash", () => {
  for (const [rel, meta] of Object.entries(manifest.files)) {
    const buf = readFileSync(new URL(rel, root));
    assert.equal(createHash("sha256").update(buf).digest("hex"), meta.sha256, rel);
    assert.equal(buf.length, meta.bytes, rel);
  }
});

test("the viewer is the spike-pinned build", () => {
  assert.equal(manifest.files["drawio/viewer-static.min.js"].sha256,
    "bc7586cb62eec98018c13b78619078d3a7179cc7bfc711c566dda19527520a30");
});

test("both font weights are bundled", () => {
  for (const w of ["Regular", "Bold"]) assert.ok(manifest.files[`fonts/LiberationSans-${w}.ttf`], w);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test services/engine/test/vendor.test.js`
Expected: FAIL, `ENOENT … vendor/MANIFEST.json`.

- [ ] **Step 3: Move the viewer and fetch the font**

```bash
mkdir -p services/engine/vendor/drawio services/engine/vendor/fonts
git mv -f scripts/spikes/vendor/viewer-static.min.js services/engine/vendor/drawio/ 2>/dev/null || mv scripts/spikes/vendor/viewer-static.min.js services/engine/vendor/drawio/
shasum -a 256 services/engine/vendor/drawio/viewer-static.min.js   # must print bc7586cb…a30
gh release view 2.1.5 -R liberationfonts/liberation-fonts --json assets --jq '.assets[].name'
# pick liberation-fonts-ttf-2.1.5.tar.gz from that list, then:
gh release download 2.1.5 -R liberationfonts/liberation-fonts -p 'liberation-fonts-ttf-2.1.5.tar.gz' -D "$TMPDIR/lib"
mkdir -p "$TMPDIR/lib/x" && tar -xzf "$TMPDIR/lib/liberation-fonts-ttf-2.1.5.tar.gz" -C "$TMPDIR/lib/x"
cp "$TMPDIR"/lib/x/liberation-fonts-ttf-2.1.5/LiberationSans-{Regular,Bold}.ttf services/engine/vendor/fonts/
shasum -a 256 services/engine/vendor/fonts/*.ttf; wc -c services/engine/vendor/fonts/*.ttf
```

If the release has no TTF tarball under that name, stop and record a ruling with the asset that does exist. Do not substitute a
different font family.

- [ ] **Step 4: Write `services/engine/vendor/MANIFEST.json`** with the printed hashes and byte counts:

```json
{
  "files": {
    "drawio/viewer-static.min.js": {"sha256": "bc7586cb62eec98018c13b78619078d3a7179cc7bfc711c566dda19527520a30", "bytes": 4360162,
      "source": "https://raw.githubusercontent.com/jgraph/drawio/v32.4.1/src/main/webapp/js/viewer-static.min.js", "licence": "Apache-2.0"},
    "fonts/LiberationSans-Regular.ttf": {"sha256": "<printed>", "bytes": 0, "source": "liberationfonts/liberation-fonts release 2.1.5", "licence": "OFL-1.1"},
    "fonts/LiberationSans-Bold.ttf": {"sha256": "<printed>", "bytes": 0, "source": "liberationfonts/liberation-fonts release 2.1.5", "licence": "OFL-1.1"}
  }
}
```

Replace `<printed>` and `0` with the real values. Remove the `scripts/spikes/vendor/*.js` line from `.gitignore`. Add both components
to `THIRD_PARTY_NOTICES.md` (name, version, licence, source URL). Point `scripts/spikes/vendor/README.md` at the new location.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `node --test services/engine/test/vendor.test.js`
Expected: PASS 3/3.

- [ ] **Step 6: Commit**

```bash
git add services/engine/vendor services/engine/test/vendor.test.js .gitignore scripts/spikes THIRD_PARTY_NOTICES.md
git commit -m "chore(engine): vendor the pinned draw.io viewer and Liberation Sans with recorded hashes"
```

---

### Task 2: Hardened `.drawio` reader

**Files:**
- Create: `src/open_apprentice/drawio/__init__.py` (empty), `src/open_apprentice/drawio/parse.py`, `tests/unit/drawio/__init__.py`, `tests/unit/drawio/test_parse.py`, `tests/unit/drawio/fixtures.py`
- Modify: `pyproject.toml` (add `"open_apprentice.drawio",` to `source_modules` of "New learning-core packages never import the evaluator")

**Interfaces:**
- Produces:
  - `class DrawioRefused(ValueError)` (the message is the user-facing reason)
  - `@dataclass(frozen=True) class Cell: id: str; parent: str; vertex: bool; edge: bool; style: dict[str, str]; value: str; geometry: dict[str, str]; geometry_span: Optional[tuple[int, int]]; wrapper: bool`
  - `@dataclass(frozen=True) class Page: index: int; id: str; name: str; compressed: bool; xml: bytes; content_span: tuple[int, int]; model: dict[str, str]; cells: tuple[Cell, ...]`
  - `@dataclass(frozen=True) class DrawioFile: raw: bytes; doc_hash: str; pages: tuple[Page, ...]`
  - `def load_drawio(raw: bytes) -> DrawioFile`
  - `def page_document(page: Page) -> str` (a one-page uncompressed `<mxfile>` for the engine)
  - `def compress_page_xml(xml: bytes) -> str` (draw.io's encoding; used by tests and fixtures)
  - `geometry_span` is relative to `page.xml`. `content_span` is the byte span in `raw` of the inline `<mxGraphModel>…</mxGraphModel>` (uncompressed) or of the base64 text (compressed).

- [ ] **Step 1: Write the fixture builder** (`tests/unit/drawio/fixtures.py`)

```python
"""Small hand-written draw.io pages for unit and round-trip tests. Real draw.io output shape: mxfile > diagram > mxGraphModel > root."""

from __future__ import annotations

from open_apprentice.drawio.parse import compress_page_xml

LABEL = "text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align={align};verticalAlign=middle;rounded=0;"
NODE = "rounded=0;whiteSpace=wrap;html=1;"


def node(cid: str, x: int, y: int, w: int = 120, h: int = 50, value: str = "Node") -> str:
    return (
        f'<mxCell id="{cid}" value="{value}" style="{NODE}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def label(cid: str, x: int | None, y: int | None, value: str = "note", align: str = "center", w: int = 80, style: str | None = None) -> str:
    xy = (f' x="{x}"' if x is not None else "") + (f' y="{y}"' if y is not None else "")
    st = style if style is not None else LABEL.format(align=align)
    return (
        f'<mxCell id="{cid}" value="{value}" style="{st}" vertex="1" parent="1">'
        f'<mxGeometry{xy} width="{w}" height="20" as="geometry"/></mxCell>'
    )


def model(cells: list[str], w: int = 600, h: int = 400, extra: str = "") -> str:
    return (
        f'<mxGraphModel grid="1" page="1" pageScale="1" pageWidth="{w}" pageHeight="{h}"{extra}><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) + "</root></mxGraphModel>"
    )


def drawio(*pages: str, compressed: tuple[bool, ...] = ()) -> bytes:
    out = []
    for i, m in enumerate(pages):
        body = compress_page_xml(m.encode()) if (compressed[i] if i < len(compressed) else False) else m
        out.append(f'<diagram id="p{i}" name="Page-{i + 1}">{body}</diagram>')
    return ('<mxfile host="test">' + "".join(out) + "</mxfile>").encode()
```

- [ ] **Step 2: Write the failing tests** (`tests/unit/drawio/test_parse.py`)

```python
import pytest

from open_apprentice.drawio.parse import DrawioRefused, compress_page_xml, load_drawio
from tests.unit.drawio.fixtures import drawio, label, model, node

CORPUS = "tests/fixtures/drawio_corpus/dev"


def test_reads_uncompressed_page_cells_and_geometry_span():
    f = load_drawio(drawio(model([node("n1", 40, 40), label("l1", 50, 100)])))
    page = f.pages[0]
    cells = {c.id: c for c in page.cells}
    assert cells["l1"].style["text"] == "" and cells["l1"].geometry["x"] == "50"
    s, e = cells["l1"].geometry_span
    assert page.xml[s:e].startswith(b"<mxGeometry") and page.xml[s:e].endswith(b">")
    assert f.raw[page.content_span[0] : page.content_span[1]] == page.xml


def test_reads_compressed_page_identically():
    m = model([node("n1", 40, 40), label("l1", 50, 100)])
    a = load_drawio(drawio(m)).pages[0]
    b = load_drawio(drawio(m, compressed=(True,))).pages[0]
    assert b.compressed and [c.id for c in a.cells] == [c.id for c in b.cells]


def test_real_corpus_files_load():
    for name in ("d1", "d2", "d3"):
        f = load_drawio(open(f"{CORPUS}/{name}.drawio", "rb").read())
        assert f.pages and all(p.model["pageScale"] == "1" for p in f.pages)


def test_missing_coordinates_are_absent_not_invented():
    c = {c.id: c for c in load_drawio(drawio(model([label("l1", None, None)]))).pages[0].cells}["l1"]
    assert "x" not in c.geometry and "y" not in c.geometry


def test_wrapper_cells_take_the_wrapper_id_and_are_marked():
    m = model(['<UserObject id="u1" label="hi"><mxCell style="text;" vertex="1" parent="1"><mxGeometry x="1" y="2" width="3" height="4" as="geometry"/></mxCell></UserObject>'])
    c = {c.id: c for c in load_drawio(drawio(m)).pages[0].cells}["u1"]
    assert c.wrapper and c.value == "hi"


@pytest.mark.parametrize(
    "raw, reason",
    [
        (b'<!DOCTYPE x [<!ENTITY a "b">]><mxfile/>', "DOCTYPE"),
        (drawio(model([node("n1", 0, 0), node("n1", 10, 10)])), "duplicate cell id"),
        (drawio(model(['<mxCell id="z" vertex="1" parent="nope"><mxGeometry as="geometry"/></mxCell>'])), "unknown parent"),
        (b"\xff\xfe<mxfile/>", "UTF-8"),
        (b"<mxfile>" + b"x" * (2 * 1024 * 1024) + b"</mxfile>", "2 MB"),
        (drawio(model([label("l1", 0, 0, value="&lt;img src=x onerror=alert(1)&gt;")])), "label content"),
        (drawio(model([label("l1", 0, 0, value="&lt;script&gt;x&lt;/script&gt;")])), "label content"),
    ],
)
def test_refusals_carry_a_reason(raw, reason):
    with pytest.raises(DrawioRefused, match=reason):
        load_drawio(raw)


def test_decompression_bomb_is_refused():
    bomb = compress_page_xml(b"<mxGraphModel><root>" + b" " * (5 * 1024 * 1024) + b"</root></mxGraphModel>")
    with pytest.raises(DrawioRefused, match="4 MB"):
        load_drawio(f'<mxfile><diagram id="p" name="P">{bomb}</diagram></mxfile>'.encode())


def test_simple_formatting_html_is_allowed():
    load_drawio(drawio(model([label("l1", 0, 0, value="&lt;b&gt;bold&lt;/b&gt;&lt;br&gt;x")])))
```

- [ ] **Step 3: Run them to verify they fail**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio/test_parse.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'open_apprentice.drawio'`.

- [ ] **Step 4: Implement `src/open_apprentice/drawio/parse.py`**

```python
"""Hardened .drawio reader (spec 6). Every refusal is a DrawioRefused whose message is shown to the user. Nothing here renders,
fetches or evaluates anything: it only reads bytes with expat and returns page models plus exact byte spans for the patcher."""

from __future__ import annotations

import base64
import hashlib
import urllib.parse
import xml.parsers.expat as expat
import zlib
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional

MAX_UPLOAD = 2 * 1024 * 1024
MAX_DECODED = 4 * 1024 * 1024
MAX_DEPTH = 32
MAX_CELLS = 2000
MAX_VALUE = 4000
HTML_TAGS = frozenset({"b", "i", "u", "br", "span", "div", "font", "p", "strong", "em", "sub", "sup"})
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
    geometry_span: Optional[tuple[int, int]]
    wrapper: bool


@dataclass(frozen=True)
class Page:
    index: int
    id: str
    name: str
    compressed: bool
    xml: bytes
    content_span: tuple[int, int]
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

    def refuse_doctype(*_: object) -> None:
        raise DrawioRefused("DOCTYPE and entity declarations are not accepted")

    p.StartDoctypeDeclHandler = refuse_doctype
    p.EntityDeclHandler = refuse_doctype
    p.ExternalEntityRefHandler = lambda *_: 0
    return p


def _tag_end(raw: bytes, start: int) -> int:
    return raw.index(b">", start) + 1


def _decode(text: str) -> bytes:
    try:
        data = base64.b64decode("".join(text.split()), validate=True)
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
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    quoted = urllib.parse.quote(xml.decode("utf-8"), safe="~()*!.'").encode("ascii")
    return base64.b64encode(c.compress(quoted) + c.flush()).decode("ascii")


def _diagrams(raw: bytes) -> list[tuple[str, str, bool, int, int]]:
    """(id, name, compressed, start, end) of each diagram's content in the file."""
    found: list[tuple[str, str, bool, int, int]] = []
    state: dict[str, object] = {"depth": 0, "diagram": None}
    p = _parser()

    def start(name: str, attrs: dict[str, str]) -> None:
        state["depth"] = int(state["depth"]) + 1  # type: ignore[call-overload]
        if int(state["depth"]) > MAX_DEPTH:  # type: ignore[call-overload]
            raise DrawioRefused("the document nests too deeply")
        if name == "diagram":
            state["diagram"] = {"id": attrs.get("id", ""), "name": attrs.get("name", ""), "text": [], "model": None,
                                "text_start": _tag_end(raw, p.CurrentByteIndex)}  # fmt: skip
        elif name == "mxGraphModel" and state["diagram"] is not None and state["diagram"]["model"] is None:  # type: ignore[index]
            state["diagram"]["model"] = p.CurrentByteIndex  # type: ignore[index]

    def end(name: str) -> None:
        state["depth"] = int(state["depth"]) - 1  # type: ignore[call-overload]
        d = state["diagram"]
        if d is None:
            return
        if name == "mxGraphModel" and d["model"] is not None and "model_end" not in d:  # type: ignore[index, operator]
            d["model_end"] = _tag_end(raw, p.CurrentByteIndex)  # type: ignore[index]
        if name == "diagram":
            if d["model"] is not None:  # type: ignore[index]
                found.append((d["id"], d["name"], False, d["model"], d["model_end"]))  # type: ignore[index]
            else:
                found.append((d["id"], d["name"], True, d["text_start"], p.CurrentByteIndex))  # type: ignore[index]
            state["diagram"] = None

    p.StartElementHandler = start
    p.EndElementHandler = end
    try:
        p.Parse(raw, True)
    except expat.ExpatError as e:
        raise DrawioRefused(f"the file is not well-formed XML ({e})") from e
    if not found:
        raise DrawioRefused("the file has no pages")
    return found


def _cells(xml: bytes) -> tuple[dict[str, str], tuple[Cell, ...]]:
    model: dict[str, str] = {}
    cells: list[dict] = []
    stack: list[dict] = []  # open mxCell / wrapper records
    wrapper: Optional[dict] = None
    depth = 0
    p = _parser()

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal wrapper, depth
        depth += 1
        if depth > MAX_DEPTH:
            raise DrawioRefused("the page nests too deeply")
        if name == "mxGraphModel" and not model:
            model.update(attrs)
        elif name in ("UserObject", "object"):
            wrapper = {"id": attrs.get("id", ""), "value": attrs.get("label", "")}
        elif name == "mxCell":
            rec = {"attrs": dict(attrs), "geometry": {}, "span": None, "wrapper": wrapper}
            cells.append(rec)
            stack.append(rec)
            if len(cells) > MAX_CELLS:
                raise DrawioRefused(f"the page has more than {MAX_CELLS} cells")
        elif name == "mxGeometry" and stack and attrs.get("as") == "geometry" and stack[-1]["span"] is None:
            s = p.CurrentByteIndex
            stack[-1]["geometry"] = dict(attrs)
            stack[-1]["span"] = (s, _tag_end(xml, s))

    def end(name: str) -> None:
        nonlocal wrapper, depth
        depth -= 1
        if name == "mxCell" and stack:
            stack.pop()
        elif name in ("UserObject", "object"):
            wrapper = None

    p.StartElementHandler = start
    p.EndElementHandler = end
    try:
        p.Parse(xml, True)
    except expat.ExpatError as e:
        raise DrawioRefused(f"a page is not well-formed XML ({e})") from e
    out: list[Cell] = []
    seen: set[str] = set()
    for rec in cells:
        a, w = rec["attrs"], rec["wrapper"]
        cid = w["id"] if w else a.get("id", "")
        value = w["value"] if w else a.get("value", "")
        if not cid:
            raise DrawioRefused("a cell has no id")
        if cid in seen:
            raise DrawioRefused(f"duplicate cell id {cid!r}")
        if len(value) > MAX_VALUE:
            raise DrawioRefused(f"cell {cid!r} has a label longer than {MAX_VALUE} characters")
        seen.add(cid)
        style = parse_style(a.get("style", ""))
        if style.get("html") == "1" and "<" in value:
            _check_label_html(value)
        out.append(Cell(cid, a.get("parent", ""), a.get("vertex") == "1", a.get("edge") == "1", style, value,
                        rec["geometry"], rec["span"], w is not None))  # fmt: skip
    for c in out:
        if c.parent and c.parent not in seen:
            raise DrawioRefused(f"cell {c.id!r} has an unknown parent {c.parent!r}")
    return model, tuple(out)


def load_drawio(raw: bytes) -> DrawioFile:
    if len(raw) > MAX_UPLOAD:
        raise DrawioRefused(f"the file is {len(raw)} bytes; the limit is 2 MB")
    try:
        head = raw.decode("utf-8")[:200].lower()
    except UnicodeDecodeError as e:
        raise DrawioRefused("the file is not UTF-8") from e
    if "encoding=" in head.split("?>")[0] and "utf-8" not in head.split("?>")[0]:
        raise DrawioRefused("the file declares a non-UTF-8 encoding")
    pages = []
    for i, (pid, name, compressed, s, e) in enumerate(_diagrams(raw)):
        xml = _decode(raw[s:e].decode("ascii", errors="strict")) if compressed else raw[s:e]
        model, cells = _cells(xml)
        pages.append(Page(i, pid, name, compressed, xml, (s, e), model, cells))
    return DrawioFile(raw, hashlib.sha256(raw).hexdigest(), tuple(pages))


def page_document(page: Page) -> str:
    return f'<mxfile><diagram id="{page.id}" name="page">{page.xml.decode("utf-8")}</diagram></mxfile>'
```

Note on the compressed-page refusal message: it says "4 MB", so the test's `match="4 MB"` holds. If `_LabelHtml` sees an `onerror`
attribute it raises "unsupported label content", which matches `match="label content"`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio/test_parse.py -q && uv run lint-imports`
Expected: all pass; `Contracts: 2 kept, 0 broken` (the second contract now lists `open_apprentice.drawio`).

- [ ] **Step 6: Commit**

```bash
git add src/open_apprentice/drawio tests/unit/drawio pyproject.toml
git commit -m "feat(drawio): hardened reader with byte spans, compressed pages and refusal reasons"
```

---

### Task 3: Cell statuses and page-level refusals

**Files:**
- Create: `src/open_apprentice/drawio/classify.py`, `tests/unit/drawio/test_classify.py`

**Interfaces:**
- Consumes: `Page`, `Cell`, `DrawioRefused` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class Classified: page: Page; movable: tuple[str, ...]; fixed: tuple[str, ...]; edges: tuple[str, ...]; reasons: dict[str, str]; width: Fraction; height: Fraction; absolute: dict[str, tuple[Fraction, Fraction, Fraction, Fraction]]`
  - `def classify(page: Page) -> Classified`
  - `MAX_OBJECTS = 32`, `MAX_MOVABLE = 16`
  - `absolute` holds the geometry box (x, y, w, h) of every object in document coordinates (group children offset by their containers).
    A missing x/y counts as 0.

- [ ] **Step 1: Write the failing tests** (`tests/unit/drawio/test_classify.py`)

```python
import pytest

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from tests.unit.drawio.fixtures import LABEL, drawio, label, model, node


def page(cells, **kw):
    return load_drawio(drawio(model(cells, **kw))).pages[0]


def test_supported_label_is_movable_and_node_is_fixed():
    c = classify(page([node("n1", 40, 40), label("l1", 50, 100)]))
    assert c.movable == ("l1",) and c.fixed == ("n1",)


@pytest.mark.parametrize(
    "cell, reason",
    [
        (label("l1", 50, 100, style=LABEL.format(align="center") + "rotation=30;"), "rotated"),
        ('<UserObject id="l1" label="x"><mxCell style="text;" vertex="1" parent="1"><mxGeometry x="1" y="1" width="9" height="9" as="geometry"/></mxCell></UserObject>', "wrapper"),
        ('<mxCell id="l1" value="x" style="text;" vertex="1" parent="1"><mxGeometry x="0.5" y="0.5" relative="1" as="geometry"/></mxCell>', "relative"),
    ],
)
def test_unsupported_labels_become_obstacles_with_reasons(cell, reason):
    c = classify(page([node("n1", 40, 40), cell]))
    assert "l1" in c.fixed and reason in c.reasons["l1"]


def test_group_children_are_obstacles_in_document_coordinates_and_container_is_not_counted():
    g = '<mxCell id="g" style="group;" vertex="1" parent="1"><mxGeometry x="100" y="100" width="200" height="100" as="geometry"/></mxCell>'
    child = '<mxCell id="k" value="c" style="rounded=0;" vertex="1" parent="g"><mxGeometry x="10" y="20" width="30" height="40" as="geometry"/></mxCell>'
    c = classify(page([g, child]))
    assert c.fixed == ("k",) and c.absolute["k"] == (110, 120, 30, 40)


def test_missing_coordinates_count_as_zero():
    assert classify(page([label("l1", None, None)])).absolute["l1"][:2] == (0, 0)


@pytest.mark.parametrize(
    "kw, cells, reason",
    [
        ({"extra": ""}, [node("n1", -10, 0)], "outside the page"),
        ({"w": 100}, [node("n1", 50, 0)], "outside the page"),
        ({}, [node(f"n{i}", (i % 6) * 90, (i // 6) * 60, 80, 50) for i in range(33)], "32 objects"),
        ({}, [label(f"l{i}", (i % 6) * 90, (i // 6) * 30) for i in range(17)], "16 movable labels"),
        ({}, [label("l1", 0, 0, style=LABEL.format(align="left") + "fontFamily=Comic Sans MS;")], "font"),
    ],
)
def test_page_refusals(kw, cells, reason):
    with pytest.raises(DrawioRefused, match=reason):
        classify(page(cells, **kw))


def test_page_scale_and_page_zero_are_refused():
    raw = drawio(model([node("n1", 0, 0)]).replace('pageScale="1"', 'pageScale="2"'))
    with pytest.raises(DrawioRefused, match="pageScale"):
        classify(load_drawio(raw).pages[0])
    raw = drawio(model([node("n1", 0, 0)]).replace('page="1"', 'page="0"'))
    with pytest.raises(DrawioRefused, match="page view"):
        classify(load_drawio(raw).pages[0])


def test_corpus_pages_classify():
    for name in ("d1", "d2", "d3"):
        for p in load_drawio(open(f"tests/fixtures/drawio_corpus/dev/{name}.drawio", "rb").read()).pages:
            c = classify(p)
            assert c.movable and c.fixed
```

- [ ] **Step 2: Run them to verify they fail**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio/test_classify.py -q`
Expected: FAIL, `ModuleNotFoundError … classify`.

- [ ] **Step 3: Implement `src/open_apprentice/drawio/classify.py`**

```python
"""Cell statuses for one page (spec 6 table) and the release-1 page limitations, each refused with a reason."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from open_apprentice.drawio.parse import Cell, DrawioRefused, Page

MAX_OBJECTS = 32
MAX_MOVABLE = 16
FONTS = frozenset({"", "Helvetica"})


@dataclass(frozen=True)
class Classified:
    page: Page
    movable: tuple[str, ...]
    fixed: tuple[str, ...]
    edges: tuple[str, ...]
    reasons: dict[str, str]
    width: Fraction
    height: Fraction
    absolute: dict[str, tuple[Fraction, Fraction, Fraction, Fraction]]


def _num(v: str | None) -> Fraction:
    try:
        return Fraction(v) if v not in (None, "") else Fraction(0)
    except ValueError as e:
        raise DrawioRefused(f"a geometry value {v!r} is not a number") from e


def _label_problem(c: Cell, layers: set[str]) -> str:
    if c.wrapper:
        return "labels inside a UserObject/object wrapper are not moved in release 1"
    if c.parent not in layers:
        return "labels inside a group or container are not moved in release 1"
    if c.geometry.get("relative") == "1":
        return "labels with relative geometry are not moved in release 1"
    if _num(c.style.get("rotation")) != 0:
        return "rotated labels are not moved in release 1"
    if not c.value.strip():
        return "empty labels cannot be measured"
    return ""


def classify(page: Page) -> Classified:
    m = page.model
    if m.get("pageScale", "1") not in ("1", "1.0"):
        raise DrawioRefused(f"pageScale={m.get('pageScale')} is not supported in release 1 (only 1)")
    if m.get("page", "1") == "0":
        raise DrawioRefused("the page view is switched off (page=0); release 1 needs a page to define the editing area")
    width, height = _num(m.get("pageWidth", "850")), _num(m.get("pageHeight", "1100"))
    by_id = {c.id: c for c in page.cells}
    roots = {c.id for c in page.cells if not c.parent}
    layers = {c.id for c in page.cells if c.parent in roots}
    movable, fixed, edges, reasons = [], [], [], {}
    absolute: dict[str, tuple[Fraction, Fraction, Fraction, Fraction]] = {}
    for c in page.cells:
        if c.edge:
            edges.append(c.id)
            continue
        if not c.vertex:
            continue
        font = c.style.get("fontFamily", "")
        if font not in FONTS:
            raise DrawioRefused(f"cell {c.id!r} uses the font {font!r}; release 1 bundles only Helvetica (Liberation Sans)")
        if c.geometry.get("relative") == "1":
            reasons[c.id] = "labels with relative geometry are not moved in release 1"
            fixed.append(c.id)  # measured from its rendered state, not its geometry
            continue
        x, y = _num(c.geometry.get("x")), _num(c.geometry.get("y"))
        p = by_id.get(c.parent)
        while p is not None and p.id not in layers and p.id not in roots:
            x, y = x + _num(p.geometry.get("x")), y + _num(p.geometry.get("y"))
            p = by_id.get(p.parent)
        absolute[c.id] = (x, y, _num(c.geometry.get("width")), _num(c.geometry.get("height")))
        if "group" in c.style:
            continue  # a container is not double-counted; its children are the obstacles
        if "text" in c.style:
            problem = _label_problem(c, layers)
            if not problem:
                movable.append(c.id)
                continue
            reasons[c.id] = problem
        fixed.append(c.id)
    for cid, (x, y, w, h) in absolute.items():
        if cid in movable or cid in fixed:
            if x < 0 or y < 0 or x + w > width or y + h > height:
                raise DrawioRefused(f"cell {cid!r} lies outside the page (0, 0, {width}, {height}); release 1 edits only inside it")
    if len(movable) + len(fixed) > MAX_OBJECTS:
        raise DrawioRefused(f"the page has {len(movable) + len(fixed)} objects; release 1 supports up to 32 objects")
    if len(movable) > MAX_MOVABLE:
        raise DrawioRefused(f"the page has {len(movable)} movable labels; release 1 supports up to 16 movable labels")
    return Classified(page, tuple(movable), tuple(fixed), tuple(edges), reasons, width, height, absolute)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/drawio/classify.py tests/unit/drawio/test_classify.py
git commit -m "feat(drawio): cell statuses, editing rectangle and release-1 limits"
```

---

### Task 4: Engine route `POST /drawio/render`

**Files:**
- Create: `services/engine/src/drawio.js`, `services/engine/test/drawio.test.js`
- Modify: `services/engine/src/engine.js` (method `renderDrawio`, render cap), `services/engine/src/server.js` (route with its own body limit)

**Interfaces:**
- Consumes: `services/engine/vendor/MANIFEST.json` (Task 1).
- Produces:
  - HTTP `POST /drawio/render` with body `{ xml: string, want_png?: boolean (default true), want_svg?: boolean (default false) }`. The
    response is:

```json
{
  "translate": {"x": 0, "y": 0},
  "labels": {"<cell id>": {"box": {"x": 0, "y": 0, "w": 0, "h": 0}, "lines": 1, "rects": 1}},
  "nodes": {"<cell id>": {"state": {"x": 0, "y": 0, "w": 0, "h": 0}, "element": {"x": 0, "y": 0, "w": 0, "h": 0} | null, "stroke": 1}},
  "missing": ["<cell id>", "..."],
  "profile": {"viewer_sha256": "…", "font": "Liberation Sans 2.1.5 as Helvetica", "font_sha256": {"Regular": "…", "Bold": "…"}, "chromium": "…"},
  "png": "<base64>" | null,
  "svg": "<string>" | null
}
```

  - All boxes are in document coordinates (floats, unrounded).
  - `labels` covers every `text;` vertex with a rendered text node. `nodes` covers every other vertex that has a state. `missing` lists
    vertices with no state or no measurable text.
  - Errors: `400 {error:{code:"INVALID_ARGUMENT"|"RENDER_FAILED"}}`, `429 LIMIT` (more than 2 concurrent renders), `400 TIMEOUT` (more
    than 15 s).
  - `Engine.renderDrawio(xml, { wantPng, wantSvg })`.

- [ ] **Step 1: Write the failing tests** (`services/engine/test/drawio.test.js`)

```js
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { Engine } from "../src/engine.js";
import { buildServer } from "../src/server.js";

const page = (cells, w = 600, h = 400) =>
  `<mxfile><diagram id="p" name="p"><mxGraphModel page="1" pageScale="1" pageWidth="${w}" pageHeight="${h}"><root><mxCell id="0"/><mxCell id="1" parent="0"/>${cells}</root></mxGraphModel></diagram></mxfile>`;
const node = (id, x, y, w = 100, h = 50) =>
  `<mxCell id="${id}" value="N" style="rounded=0;whiteSpace=wrap;html=1;" vertex="1" parent="1"><mxGeometry x="${x}" y="${y}" width="${w}" height="${h}" as="geometry"/></mxCell>`;
const label = (id, x, y, value = "note", align = "left", w = 80) =>
  `<mxCell id="${id}" value="${value}" style="text;html=1;align=${align};verticalAlign=middle;strokeColor=none;fillColor=none;" vertex="1" parent="1"><mxGeometry x="${x}" y="${y}" width="${w}" height="20" as="geometry"/></mxCell>`;

let engine, app;
before(async () => { engine = new Engine(); await engine.start(); app = buildServer(engine); });
after(async () => { await app.close(); await engine.close(); });

const render = async (xml, extra = {}) => {
  const r = await app.inject({ method: "POST", url: "/drawio/render", payload: { xml, ...extra } });
  return { status: r.statusCode, body: r.json() };
};

test("nodes map back to their geometry and labels measure their glyphs, not the container", async () => {
  const { status, body } = await render(page(node("n1", 40, 40) + label("l1", 200, 100)));
  assert.equal(status, 200);
  const s = body.nodes.n1.state;
  assert.deepEqual([s.x, s.y, s.w, s.h], [40, 40, 100, 50]);
  const b = body.labels.l1.box;
  assert.ok(b.x >= 200 && b.x < 206 && b.w > 10 && b.w < 80 && b.h < 20, JSON.stringify(b));
  assert.equal(body.labels.l1.lines, 1);
  assert.match(body.profile.viewer_sha256, /^bc7586cb/);
  assert.ok(body.png && Buffer.from(body.png, "base64").subarray(1, 4).toString() === "PNG");
});

test("content far from the origin still measures in document coordinates (nonzero viewer translate)", async () => {
  const { body } = await render(page(node("n1", 400, 300), 900, 700));
  const s = body.nodes.n1.state;
  assert.deepEqual([s.x, s.y], [400, 300]);
});

test("Helvetica resolves to the bundled Liberation Sans on every host", async () => {
  const a = await engine.textWidthForTest("Helvetica", "Hamburgefonstiv 0123");
  const b = await engine.textWidthForTest("OA Liberation Probe", "Hamburgefonstiv 0123");
  assert.ok(Math.abs(a - b) < 0.01, `${a} vs ${b}`);
});

test("a label that wraps reports more than one line", async () => {
  const { body } = await render(page(label("l1", 10, 10, "a long label that cannot fit in thirty units", "left", 30).replace("html=1;", "html=1;whiteSpace=wrap;")));
  assert.ok(body.labels.l1.lines > 1);
});

test("an empty-looking label is reported missing, not measured as zero", async () => {
  const { body } = await render(page(label("l1", 10, 10, "&amp;nbsp;")));
  assert.ok(body.missing.includes("l1"));
});

test("no network request leaves the render context", async () => {
  const img = `<mxCell id="i" style="shape=image;image=https://example.com/x.png;" vertex="1" parent="1"><mxGeometry x="10" y="10" width="20" height="20" as="geometry"/></mxCell>`;
  const { status, body } = await render(page(img));
  assert.equal(status, 200);
  assert.ok(body.blocked_requests.includes("https://example.com/x.png"), JSON.stringify(body.blocked_requests));
});

test("oversized and non-string input is refused", async () => {
  assert.equal((await render(123)).status, 400);
  assert.equal((await render("x".repeat(5 * 1024 * 1024))).status, 400);
});
```

The network test proves that requests are *attempted and aborted*. The response includes `blocked_requests` for auditability.

- [ ] **Step 2: Run them to verify they fail**

Run: `node --test services/engine/test/drawio.test.js`
Expected: FAIL (404 on `/drawio/render`, and `engine.textWidthForTest is not a function`).

- [ ] **Step 3: Implement `services/engine/src/drawio.js`**

```js
// Render and measure one draw.io page with the pinned viewer in a fresh, network-blocked context (spec 6).
// Measurement primitives follow the round-trip spike: labels = union of client rects of one Range per non-empty text node,
// plus visible background/border/padding; fixed shapes = draw.io cell-state bounds cross-checked with the rendered element.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const VENDOR = new URL("../vendor/", import.meta.url);
const MANIFEST = JSON.parse(readFileSync(new URL("MANIFEST.json", VENDOR)));
const read = (rel) => {
  const buf = readFileSync(new URL(rel, VENDOR));
  const got = createHash("sha256").update(buf).digest("hex");
  if (got !== MANIFEST.files[rel].sha256) throw new Error(`vendored ${rel} hash mismatch`);
  return buf;
};
const VIEWER = read("drawio/viewer-static.min.js").toString("utf8");
const REGULAR = read("fonts/LiberationSans-Regular.ttf").toString("base64");
const BOLD = read("fonts/LiberationSans-Bold.ttf").toString("base64");
export const FONT_CSS = ["Helvetica", "OA Liberation Probe"].map((fam) =>
  `@font-face{font-family:"${fam}";src:url(data:font/ttf;base64,${REGULAR}) format("truetype");font-weight:400}` +
  `@font-face{font-family:"${fam}";src:url(data:font/ttf;base64,${BOLD}) format("truetype");font-weight:700}`).join("");
export const PROFILE_BASE = {
  viewer_sha256: MANIFEST.files["drawio/viewer-static.min.js"].sha256,
  font: "Liberation Sans 2.1.5 as Helvetica",
  font_sha256: { Regular: MANIFEST.files["fonts/LiberationSans-Regular.ttf"].sha256, Bold: MANIFEST.files["fonts/LiberationSans-Bold.ttf"].sha256 },
};
export const MAX_XML = 4 * 1024 * 1024;
export const RENDER_TIMEOUT_MS = 15000;

export async function openFontPage(browser) {
  const context = await browser.newContext({ javaScriptEnabled: true });
  const blocked = [];
  await context.route("**/*", (route) => { blocked.push(route.request().url()); return route.abort(); });
  const page = await context.newPage();
  await page.setContent('<!doctype html><html><body style="margin:0"><div id="c"></div></body></html>');
  await page.addStyleTag({ content: FONT_CSS });
  await page.evaluate(async () => {
    await document.fonts.load('12px "Helvetica"'); await document.fonts.load('bold 12px "Helvetica"');
    await document.fonts.load('12px "OA Liberation Probe"'); await document.fonts.ready;
  });
  return { context, page, blocked };
}

export async function renderPage(browser, xml, { wantPng = true, wantSvg = false } = {}) {
  const { context, page, blocked } = await openFontPage(browser);
  try {
    await page.addScriptTag({ content: VIEWER });
    const out = await page.evaluate(async (xmlText) => {
      const doc = mxUtils.parseXml(xmlText);
      const container = document.getElementById("c");
      const v = new GraphViewer(container, doc.documentElement, { highlight: "none", nav: false, resize: false, center: false });
      const graph = v.graph;
      graph.view.setScale(1);
      await document.fonts.ready;
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      const svg = container.querySelector("svg");
      const inv = svg.getScreenCTM().inverse();
      const toDoc = (cx, cy) => {
        const p = svg.createSVGPoint(); p.x = cx; p.y = cy;
        const q = p.matrixTransform(inv);
        return { x: q.x / graph.view.scale - graph.view.translate.x, y: q.y / graph.view.scale - graph.view.translate.y };
      };
      const box = (l, t, r, b) => { const a = toDoc(l, t), c = toDoc(r, b); return { x: a.x, y: a.y, w: c.x - a.x, h: c.y - a.y }; };
      const res = { translate: { x: graph.view.translate.x, y: graph.view.translate.y }, labels: {}, nodes: {}, missing: [] };
      for (const cell of Object.values(graph.model.cells)) {
        if (!cell.vertex) continue;
        const st = graph.view.getState(cell);
        if (!st) { res.missing.push(cell.id); continue; }
        if ((cell.style || "").startsWith("text;")) {
          const rects = [];
          if (st.text && st.text.node) {
            const walker = document.createTreeWalker(st.text.node, NodeFilter.SHOW_TEXT);
            for (let n = walker.nextNode(); n; n = walker.nextNode()) {
              if (!n.textContent.replace(/ /g, " ").trim()) continue;
              const range = document.createRange(); range.selectNodeContents(n);
              rects.push(...[...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0));
            }
          }
          if (!rects.length) { res.missing.push(cell.id); continue; }
          let l = Math.min(...rects.map((r) => r.left)), t = Math.min(...rects.map((r) => r.top));
          let r = Math.max(...rects.map((q) => q.right)), b = Math.max(...rects.map((q) => q.bottom));
          // visible background/border/padding of the label's own HTML box extends the measured box
          const div = st.text.node.querySelector("div div") || st.text.node.querySelector("div");
          if (div) {
            const cs = getComputedStyle(div);
            const visible = (cs.backgroundColor && cs.backgroundColor !== "rgba(0, 0, 0, 0)" && cs.backgroundColor !== "transparent") || parseFloat(cs.borderTopWidth) > 0;
            if (visible) { const d = div.getBoundingClientRect(); l = Math.min(l, d.left); t = Math.min(t, d.top); r = Math.max(r, d.right); b = Math.max(b, d.bottom); }
          }
          const lines = new Set(rects.map((q) => Math.round(q.top))).size;
          res.labels[cell.id] = { box: box(l, t, r, b), lines, rects: rects.length };
        } else {
          const s = graph.view.scale, tr = graph.view.translate;
          const state = { x: st.x / s - tr.x, y: st.y / s - tr.y, w: st.width / s, h: st.height / s };
          let element = null;
          const shapeNode = st.shape && st.shape.node;
          if (shapeNode) { const q = shapeNode.getBoundingClientRect(); if (q.width > 0 || q.height > 0) element = box(q.left, q.top, q.right, q.bottom); }
          res.nodes[cell.id] = { state, element, stroke: Number(st.style.strokeWidth || 1) };
        }
      }
      return res;
    }, xml);
    out.png = wantPng ? (await page.locator("#c svg").screenshot({ type: "png" })).toString("base64") : null;
    out.svg = wantSvg ? await page.evaluate(() => new XMLSerializer().serializeToString(document.querySelector("#c svg"))) : null;
    out.blocked_requests = blocked;
    return out;
  } finally {
    await context.close().catch(() => {});
  }
}
```

- [ ] **Step 4: Wire `engine.js` and `server.js`**

In `engine.js`, add `import { MAX_XML, PROFILE_BASE, RENDER_TIMEOUT_MS, openFontPage, renderPage } from "./drawio.js";` and
`const MAX_RENDERS = 2;`. Add a private field `#renders = 0;`. Then add the methods:

```js
  async renderDrawio(xml, { wantPng = true, wantSvg = false } = {}) {
    if (typeof xml !== "string" || xml.length > MAX_XML || !xml.startsWith("<mxfile")) {
      throw Object.assign(new Error("invalid draw.io page"), { code: "INVALID_ARGUMENT" });
    }
    if (this.#renders >= MAX_RENDERS) throw Object.assign(new Error("render limit"), { code: "LIMIT" });
    this.#renders += 1;
    let timer;
    try {
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(Object.assign(new Error("render timed out"), { code: "TIMEOUT" })), RENDER_TIMEOUT_MS);
      });
      const out = await Promise.race([renderPage(this.#browser, xml, { wantPng, wantSvg }), timeout]);
      return { ...out, profile: { ...PROFILE_BASE, chromium: this.#browser.version() } };
    } catch (e) {
      if (e.code) throw e;
      throw Object.assign(new Error(String(e.message).split("\n")[0].slice(0, 200)), { code: "RENDER_FAILED" });
    } finally {
      clearTimeout(timer);
      this.#renders -= 1;
    }
  }

  async textWidthForTest(family, text) {
    const { context, page } = await openFontPage(this.#browser);
    try {
      return await page.evaluate(([f, t]) => {
        const c = document.createElement("canvas").getContext("2d"); c.font = `12px "${f}"`; return c.measureText(t).width;
      }, [family, text]);
    } finally { await context.close(); }
  }
```

In `server.js`, after the `/sessions` routes:

```js
  // Product route: renders an already-validated page (the API refuses hostile files before calling this); the context is fresh and network-blocked.
  app.post("/drawio/render", { bodyLimit: 8 * 1024 * 1024 }, async (req, reply) => {
    const { xml, want_png, want_svg } = req.body ?? {};
    try { return await engine.renderDrawio(xml, { wantPng: want_png !== false, wantSvg: want_svg === true }); } catch (e) { return fail(reply, e); }
  });
```

Also extend `fail`: `e.code === "TIMEOUT"` stays 400 per the interface above (this matches the existing 400 default).

- [ ] **Step 5: Run the engine tests to verify they pass**

Run: `npm test -w services/engine`
Expected: all engine tests pass, including the 7 new ones. If the "wraps" test reports 1 line because the viewer does not wrap without
`whiteSpace=wrap`, keep the style as written in the test (it adds `whiteSpace=wrap`).

- [ ] **Step 6: Commit**

```bash
git add services/engine/src services/engine/test/drawio.test.js
git commit -m "feat(engine): /drawio/render — pinned viewer, bundled font, glyph-run label boxes, PNG/SVG, network blocked"
```

---

### Task 5: Engine client, measurements as rationals, teaching scene

**Files:**
- Create: `src/open_apprentice/drawio/render.py`, `src/open_apprentice/drawio/scene.py`, `tests/unit/drawio/test_scene.py`, `tests/integration/drawio/__init__.py`, `tests/integration/drawio/conftest.py`, `tests/integration/drawio/test_render_scene.py`

**Interfaces:**
- Consumes: `Page`, `page_document` (Task 2); `Classified`, `classify` (Task 3); the `/drawio/render` response (Task 4); `Mapping` (Task 6; the scene builder takes a plain `dict[str, tuple[str, str]]`, cell → (node_id, role), so Task 5 does not depend on Task 6's module).
- Produces:
  - `render.py`: `@dataclass(frozen=True) class Box: x: Fraction; y: Fraction; w: Fraction; h: Fraction`;
    `@dataclass(frozen=True) class Rendered: labels: dict[str, tuple[Box, int]]; nodes: dict[str, tuple[Box, Optional[Box], Fraction]]; missing: tuple[str, ...]; profile: dict; png: Optional[bytes]; svg: Optional[str]`;
    `def q64(v: float | int | str) -> Fraction`;
    `def parse_render(body: dict) -> Rendered`;
    `def render_page(page: Page, engine_url: str, *, png: bool = True, svg: bool = False, timeout: float = 30.0) -> Rendered`.
    Engine HTTP errors raise `DrawioRefused` with the engine's message.
  - `scene.py`: `@dataclass(frozen=True) class DrawioScene: scene: dict; offsets: dict[str, tuple[Fraction, Fraction]]; movable: tuple[str, ...]; demoted: dict[str, str]`;
    `def build_scene(c: Classified, r: Rendered, mapping: dict[str, tuple[str, str]]) -> DrawioScene`.
  - Scene objects follow the teaching format: `{"id","kind","role","attached","x","y","w","h"}`. `kind` is "node" for fixed shapes,
    "label" for movable mapped labels, and "obstacle" for unsupported or demoted labels. The canvas is `{"w": pageWidth, "h": pageHeight}`.

- [ ] **Step 1: Write the failing pure tests** (`tests/unit/drawio/test_scene.py`). These build a `Rendered` by hand, so no engine is needed:

```python
from fractions import Fraction as F

import pytest

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.render import parse_render, q64
from open_apprentice.drawio.scene import build_scene
from tests.unit.drawio.fixtures import drawio, label, model, node


def setup(label_box=(52, 103, 30, 14), lines=1, node_state=(40, 40, 100, 50), element=(40, 40, 100, 50)):
    c = classify(load_drawio(drawio(model([node("n1", 40, 40, 100, 50), label("l1", 50, 100)]))).pages[0])
    box = lambda b: dict(zip("xywh", b))
    r = parse_render({"labels": {"l1": {"box": box(label_box), "lines": lines, "rects": 1}},
                      "nodes": {"n1": {"state": box(node_state), "element": box(element), "stroke": 1}},
                      "missing": [], "profile": {}, "png": None, "svg": None})  # fmt: skip
    return c, r


def test_quantum_is_one_sixty_fourth():
    assert q64(10.0078125) == F(641, 64) and q64("3.3").denominator in (1, 2, 4, 8, 16, 32, 64)


def test_scene_uses_measured_boxes_and_stores_offsets():
    c, r = setup()
    s = build_scene(c, r, {"l1": ("n1", "note")})
    lab = next(o for o in s.scene["objects"] if o["id"] == "l1")
    assert (lab["kind"], lab["role"], lab["attached"]) == ("label", "note", "n1")
    assert (lab["x"], lab["y"], lab["w"], lab["h"]) == (52, 103, 30, 14)
    assert s.offsets["l1"] == (2, 3) and s.scene["canvas"] == {"w": 600, "h": 400}


def test_wrapped_label_is_demoted_to_obstacle_with_reason():
    c, r = setup(lines=2)
    s = build_scene(c, r, {"l1": ("n1", "note")})
    assert s.movable == () and "more than one line" in s.demoted["l1"]
    assert next(o for o in s.scene["objects"] if o["id"] == "l1")["kind"] == "obstacle"


def test_node_mismatch_above_half_unit_blocks():
    c, r = setup(element=(42, 40, 100, 50))  # 2 units off; tolerance is 0.5 + stroke/2 = 1
    with pytest.raises(DrawioRefused, match="disagrees"):
        build_scene(c, r, {"l1": ("n1", "note")})


def test_unmapped_movable_label_is_an_error():
    c, r = setup()
    with pytest.raises(ValueError, match="mapping"):
        build_scene(c, r, {})


def test_measured_box_outside_page_is_refused():
    c, r = setup(label_box=(590, 103, 30, 14))
    with pytest.raises(DrawioRefused, match="outside the page"):
        build_scene(c, r, {"l1": ("n1", "note")})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio/test_scene.py -q`
Expected: FAIL, `ModuleNotFoundError … render`.

- [ ] **Step 3: Implement `render.py` and `scene.py`**

```python
# src/open_apprentice/drawio/render.py
"""Client for the engine's /drawio/render route. Measurements arrive as floats and are kept as exact 1/64 rationals (spec 6 quantum)."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

import httpx

from open_apprentice.drawio.parse import DrawioRefused, Page, page_document


@dataclass(frozen=True)
class Box:
    x: Fraction
    y: Fraction
    w: Fraction
    h: Fraction


@dataclass(frozen=True)
class Rendered:
    labels: dict[str, tuple[Box, int]]
    nodes: dict[str, tuple[Box, Optional[Box], Fraction]]
    missing: tuple[str, ...]
    profile: dict
    png: Optional[bytes]
    svg: Optional[str]


def q64(v: float | int | str) -> Fraction:
    return Fraction(round(Fraction(v) * 64), 64)


def _box(d: dict) -> Box:
    return Box(q64(d["x"]), q64(d["y"]), q64(d["w"]), q64(d["h"]))


def parse_render(body: dict) -> Rendered:
    return Rendered(
        labels={k: (_box(v["box"]), int(v["lines"])) for k, v in body["labels"].items()},
        nodes={k: (_box(v["state"]), _box(v["element"]) if v.get("element") else None, q64(v.get("stroke", 1)))
               for k, v in body["nodes"].items()},  # fmt: skip
        missing=tuple(body.get("missing", ())),
        profile=dict(body.get("profile", {})),
        png=base64.b64decode(body["png"]) if body.get("png") else None,
        svg=body.get("svg"),
    )


def render_page(page: Page, engine_url: str, *, png: bool = True, svg: bool = False, timeout: float = 30.0) -> Rendered:
    try:
        r = httpx.post(f"{engine_url}/drawio/render", json={"xml": page_document(page), "want_png": png, "want_svg": svg}, timeout=timeout)
    except httpx.HTTPError as e:
        raise DrawioRefused(f"the renderer is unavailable ({type(e).__name__})") from e
    body = r.json()
    if r.status_code != 200:
        raise DrawioRefused(f"the page could not be rendered: {body.get('error', {}).get('message', r.status_code)}")
    return parse_render(body)
```

```python
# src/open_apprentice/drawio/scene.py
"""Teaching scene from one classified, rendered page and a confirmed mapping. A label's scene box is its measured box; the offset
d = box − geometry is stored so a target box can be turned back into geometry (spec 6 arithmetic)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from open_apprentice.drawio.classify import Classified
from open_apprentice.drawio.parse import DrawioRefused
from open_apprentice.drawio.render import Box, Rendered

NODE_TOLERANCE = Fraction(1, 2)


@dataclass(frozen=True)
class DrawioScene:
    scene: dict
    offsets: dict[str, tuple[Fraction, Fraction]]
    movable: tuple[str, ...]
    demoted: dict[str, str]


def _obj(cid: str, kind: str, b: Box, role: str = "", attached: str = "") -> dict:
    return {"id": cid, "kind": kind, "role": role, "attached": attached, "x": b.x, "y": b.y, "w": b.w, "h": b.h}


def build_scene(c: Classified, r: Rendered, mapping: dict[str, tuple[str, str]]) -> DrawioScene:
    objects, offsets, movable, demoted = [], {}, [], {}
    for cid in c.fixed:
        if cid in r.nodes:
            state, element, stroke = r.nodes[cid]
            if element is not None:
                err = max(abs(state.x - element.x), abs(state.y - element.y),
                          abs(state.x + state.w - element.x - element.w), abs(state.y + state.h - element.y - element.h))  # fmt: skip
                if err > NODE_TOLERANCE + stroke / 2:
                    raise DrawioRefused(f"cell {cid!r}: its rendered shape disagrees with its geometry by {float(err):.2f} units")
            objects.append(_obj(cid, "node" if cid not in c.reasons else "obstacle", state))
        elif cid in r.labels:
            objects.append(_obj(cid, "obstacle", r.labels[cid][0]))
        else:
            raise DrawioRefused(f"cell {cid!r} could not be measured, so labels cannot be placed safely")
    for cid in c.movable:
        if cid not in r.labels:
            raise DrawioRefused(f"label {cid!r} could not be measured")
        box, lines = r.labels[cid]
        if lines > 1:
            demoted[cid] = "renders on more than one line with the bundled font"
            objects.append(_obj(cid, "obstacle", box))
            continue
        if cid not in mapping:
            raise ValueError(f"label {cid!r} has no confirmed mapping")
        node_id, role = mapping[cid]
        gx, gy = c.absolute[cid][:2]
        offsets[cid] = (box.x - gx, box.y - gy)
        movable.append(cid)
        objects.append(_obj(cid, "label", box, role, node_id))
    for o in objects:
        if o["x"] < 0 or o["y"] < 0 or o["x"] + o["w"] > c.width or o["y"] + o["h"] > c.height:
            raise DrawioRefused(f"cell {o['id']!r} renders outside the page (0, 0, {c.width}, {c.height})")
    return DrawioScene({"objects": objects, "canvas": {"w": c.width, "h": c.height}}, offsets, tuple(movable), demoted)
```

- [ ] **Step 4: Write the engine-backed integration test**

`tests/integration/drawio/conftest.py` starts the real engine on a free port. It is skipped unless `OA_ENGINE_TESTS=1`:

```python
import os
import socket
import subprocess
import time

import httpx
import pytest


@pytest.fixture(scope="session")
def engine_url():
    if os.environ.get("OA_ENGINE_TESTS") != "1":
        pytest.skip("engine tests need OA_ENGINE_TESTS=1")
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    proc = subprocess.Popen(["node", "services/engine/src/server.js"], env={**os.environ, "PORT": str(port), "HOST": "127.0.0.1"})
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{url}/health/live", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield url
    proc.terminate()
    proc.wait(10)
```

`tests/integration/drawio/test_render_scene.py`:

```python
from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import load_drawio
from open_apprentice.drawio.render import render_page
from open_apprentice.drawio.scene import build_scene


def test_corpus_page_becomes_a_scene(engine_url):
    f = load_drawio(open("tests/fixtures/drawio_corpus/dev/d1.drawio", "rb").read())
    c = classify(f.pages[0])
    r = render_page(f.pages[0], engine_url)
    first_node = next(cid for cid in c.fixed if cid in r.nodes)
    s = build_scene(c, r, {cid: (first_node, "note") for cid in c.movable})
    assert {o["kind"] for o in s.scene["objects"]} >= {"node", "label"}
    assert r.png and r.profile["viewer_sha256"].startswith("bc7586cb")
    for cid in s.movable:
        dx, dy = s.offsets[cid]
        assert abs(dx) < 120 and abs(dy) < 20
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio -q && OA_ENGINE_TESTS=1 PYTHONPATH=src:. .venv/bin/python -m pytest tests/integration/drawio -q`
Expected: PASS. The integration run needs the sandbox disabled, because it launches Chromium.

- [ ] **Step 6: Commit**

```bash
git add src/open_apprentice/drawio/render.py src/open_apprentice/drawio/scene.py tests/unit/drawio/test_scene.py tests/integration/drawio
git commit -m "feat(drawio): engine client with 1/64 measurements; teaching scene with offsets and demotions"
```

---

### Task 6: Mapping sidecar

**Files:**
- Create: `src/open_apprentice/drawio/mapping.py`, `tests/unit/drawio/test_mapping.py`

**Interfaces:**
- Consumes: `Classified` (Task 3), `Rendered`, `Box` (Task 5).
- Produces:
  - `@dataclass(frozen=True) class Mapping: doc_hash: str; page_id: str; labels: dict[str, dict[str, str]]; proposed: frozenset[str]; confirmed_by_event: Optional[str]`
  - `def propose(c: Classified, r: Rendered, doc_hash: str) -> Mapping` (nearest node by box gap distance, ties by node id; role "note"; every entry proposed)
  - `def edit(m: Mapping, cell_id: str, *, node_id: Optional[str] = None, role: Optional[str] = None, nodes: frozenset[str]) -> Mapping`
    (the role is lower-cased and stripped; the node must be in `nodes`; the cell leaves `proposed`; `confirmed_by_event` resets to None)
  - `def confirm(m: Mapping, event_id: str) -> Mapping`
  - `def to_json(m: Mapping) -> dict`, `def from_json(d: dict) -> Mapping`
  - `def digest(m: Mapping) -> str` (sha256 over doc_hash, page_id and labels; a change means a new `intent_revision` in Plan 4)
  - `def as_scene_mapping(m: Mapping, doc_hash: str, page_id: str, movable: tuple[str, ...]) -> dict[str, tuple[str, str]]`
    (raises `DrawioRefused` if the mapping is bound to another document or page, is unconfirmed, or misses a movable label)

- [ ] **Step 1: Write the failing tests** (`tests/unit/drawio/test_mapping.py`)

```python
import pytest

from open_apprentice.drawio import mapping as mp
from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.render import parse_render
from tests.unit.drawio.fixtures import drawio, label, model, node


def setup():
    f = load_drawio(drawio(model([node("a", 40, 40), node("b", 300, 40), label("l1", 180, 50), label("l2", 300, 100)])))
    c = classify(f.pages[0])
    box = lambda x, y, w, h: {"x": x, "y": y, "w": w, "h": h}
    r = parse_render({"labels": {"l1": {"box": box(182, 53, 20, 14), "lines": 1}, "l2": {"box": box(302, 103, 20, 14), "lines": 1}},
                      "nodes": {"a": {"state": box(40, 40, 120, 50)}, "b": {"state": box(300, 40, 120, 50)}}})  # fmt: skip
    return f, c, r


def test_proposes_nearest_node_by_box_gap_with_role_note():
    f, c, r = setup()
    m = mp.propose(c, r, f.doc_hash)
    assert m.labels == {"l1": {"node_id": "a", "role": "note"}, "l2": {"node_id": "b", "role": "note"}}
    assert m.proposed == {"l1", "l2"} and m.confirmed_by_event is None


def test_edit_lowercases_role_and_validates_node():
    f, c, r = setup()
    m = mp.edit(mp.propose(c, r, f.doc_hash), "l1", node_id="b", role=" Warning ", nodes=frozenset({"a", "b"}))
    assert m.labels["l1"] == {"node_id": "b", "role": "warning"} and "l1" not in m.proposed
    with pytest.raises(ValueError):
        mp.edit(m, "l1", node_id="zzz", nodes=frozenset({"a", "b"}))


def test_digest_changes_with_mapping_and_round_trips():
    f, c, r = setup()
    m = mp.confirm(mp.propose(c, r, f.doc_hash), "e7")
    assert mp.from_json(mp.to_json(m)) == m
    m2 = mp.edit(m, "l1", role="warning", nodes=frozenset({"a", "b"}))
    assert mp.digest(m2) != mp.digest(m) and m2.confirmed_by_event is None


def test_scene_mapping_requires_confirmation_and_the_same_document():
    f, c, r = setup()
    m = mp.propose(c, r, f.doc_hash)
    with pytest.raises(DrawioRefused, match="confirmed"):
        mp.as_scene_mapping(m, f.doc_hash, f.pages[0].id, c.movable)
    m = mp.confirm(m, "e1")
    with pytest.raises(DrawioRefused, match="another document"):
        mp.as_scene_mapping(m, "0" * 64, f.pages[0].id, c.movable)
    assert mp.as_scene_mapping(m, f.doc_hash, f.pages[0].id, c.movable)["l1"] == ("a", "note")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio/test_mapping.py -q`
Expected: FAIL, `ImportError … mapping`.

- [ ] **Step 3: Implement `src/open_apprentice/drawio/mapping.py`**

```python
"""Label → node mapping sidecar, bound to one document hash and page (spec 6). The system only proposes; a teacher event confirms."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Optional

from open_apprentice.drawio.classify import Classified
from open_apprentice.drawio.parse import DrawioRefused
from open_apprentice.drawio.render import Box, Rendered


@dataclass(frozen=True)
class Mapping:
    doc_hash: str
    page_id: str
    labels: dict[str, dict[str, str]]
    proposed: frozenset[str]
    confirmed_by_event: Optional[str]


def _gap(a: Box, b: Box) -> Fraction:
    dx = max(Fraction(0), a.x - (b.x + b.w), b.x - (a.x + a.w))
    dy = max(Fraction(0), a.y - (b.y + b.h), b.y - (a.y + a.h))
    return dx * dx + dy * dy


def propose(c: Classified, r: Rendered, doc_hash: str) -> Mapping:
    nodes = sorted(cid for cid in c.fixed if cid in r.nodes and cid not in c.reasons)
    labels = {}
    for cid in c.movable:
        if cid in r.labels and nodes:
            box = r.labels[cid][0]
            best = min(nodes, key=lambda n: (_gap(box, r.nodes[n][0]), n))
            labels[cid] = {"node_id": best, "role": "note"}
    return Mapping(doc_hash, c.page.id, labels, frozenset(labels), None)


def edit(m: Mapping, cell_id: str, *, node_id: Optional[str] = None, role: Optional[str] = None, nodes: frozenset[str]) -> Mapping:
    if cell_id not in m.labels:
        raise ValueError(f"{cell_id!r} is not a mapped label")
    entry = dict(m.labels[cell_id])
    if node_id is not None:
        if node_id not in nodes:
            raise ValueError(f"{node_id!r} is not a node on this page")
        entry["node_id"] = node_id
    if role is not None:
        entry["role"] = role.strip().lower()
    return replace(m, labels={**m.labels, cell_id: entry}, proposed=m.proposed - {cell_id}, confirmed_by_event=None)


def confirm(m: Mapping, event_id: str) -> Mapping:
    return replace(m, proposed=frozenset(), confirmed_by_event=event_id)


def to_json(m: Mapping) -> dict:
    return {"doc_hash": m.doc_hash, "page_id": m.page_id, "labels": m.labels, "proposed": sorted(m.proposed),
            "confirmed_by_event": m.confirmed_by_event}  # fmt: skip


def from_json(d: dict) -> Mapping:
    return Mapping(d["doc_hash"], d["page_id"], {k: dict(v) for k, v in d["labels"].items()}, frozenset(d["proposed"]), d["confirmed_by_event"])


def digest(m: Mapping) -> str:
    body = json.dumps({"doc_hash": m.doc_hash, "page_id": m.page_id, "labels": m.labels}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def as_scene_mapping(m: Mapping, doc_hash: str, page_id: str, movable: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    if (m.doc_hash, m.page_id) != (doc_hash, page_id):
        raise DrawioRefused("this mapping belongs to another document or page")
    if m.confirmed_by_event is None:
        raise DrawioRefused("the label mapping has not been confirmed")
    missing = [cid for cid in movable if cid not in m.labels]
    if missing:
        raise DrawioRefused(f"labels without a mapping: {missing}")
    return {cid: (v["node_id"], v["role"]) for cid, v in m.labels.items()}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/drawio/mapping.py tests/unit/drawio/test_mapping.py
git commit -m "feat(drawio): proposed/confirmed label mapping sidecar bound to the document hash"
```

---

### Task 7: Patcher

**Files:**
- Create: `src/open_apprentice/drawio/patch.py`, `tests/unit/drawio/test_patch.py`

**Interfaces:**
- Consumes: `DrawioFile`, `Page`, `load_drawio`, `DrawioRefused` (Task 2); `Classified.absolute` (Task 3); `DrawioScene.offsets` (Task 5).
- Produces:
  - `@dataclass(frozen=True) class Edit: cell_id: str; exact: tuple[Fraction, Fraction]; serialized: tuple[int, int]; expected_old: tuple[Optional[str], Optional[str]]`
  - `def round_half_up(v: Fraction) -> int`
  - `def plan_edits(page: Page, offsets: dict[str, tuple[Fraction, Fraction]], target_boxes: dict[str, tuple[Fraction, Fraction]]) -> list[Edit]`
    (target geometry = target_box − d; `expected_old` = the current raw `x`/`y` attribute strings, or None when absent)
  - `def apply_edits(f: DrawioFile, page_index: int, edits: list[Edit], source_hash: str) -> bytes`

- [ ] **Step 1: Write the failing tests** (`tests/unit/drawio/test_patch.py`)

```python
from fractions import Fraction as F

import pytest

from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.patch import Edit, apply_edits, plan_edits, round_half_up
from tests.unit.drawio.fixtures import drawio, label, model, node

M = model([node("n1", 40, 40), label("l1", 50, 100), label("l2", None, None)])


def test_round_half_up_matches_the_renderer():
    assert [round_half_up(F(v)) for v in ("0.5", "1.5", "37.25", "37.5", "37.75", "-0.5")] == [1, 2, 37, 38, 38, 0]


def test_plan_subtracts_the_offset_and_keeps_exact_serialized_and_old_separate():
    page = load_drawio(drawio(M)).pages[0]
    (e,) = plan_edits(page, {"l1": (F(2), F(3))}, {"l1": (F(201, 2), F(140))})
    assert e.exact == (F(197, 2), F(137)) and e.serialized == (99, 137) and e.expected_old == ("50", "100")


def test_uncompressed_patch_changes_only_the_geometry_tag():
    f = load_drawio(drawio(M))
    out = apply_edits(f, 0, [Edit("l1", (F(99), F(137)), (99, 137), ("50", "100"))], f.doc_hash)
    a, b = f.raw.split(b'x="50" y="100"'), out.split(b'x="99" y="137"')
    assert a == b  # every byte outside the edited attributes is identical


def test_missing_coordinates_are_inserted():
    f = load_drawio(drawio(M))
    out = apply_edits(f, 0, [Edit("l2", (F(5), F(6)), (5, 6), (None, None))], f.doc_hash)
    cell = {c.id: c for c in load_drawio(out).pages[0].cells}["l2"]
    assert (cell.geometry["x"], cell.geometry["y"]) == ("5", "6")


def test_compressed_page_is_written_uncompressed_and_other_pages_keep_their_bytes():
    other = model([node("z", 1, 1)])
    f = load_drawio(drawio(M, other, compressed=(True, True)))
    out = apply_edits(f, 0, [Edit("l1", (F(99), F(137)), (99, 137), ("50", "100"))], f.doc_hash)
    g = load_drawio(out)
    assert not g.pages[0].compressed and g.pages[1].compressed
    assert out[g.pages[1].content_span[0] : g.pages[1].content_span[1]] == f.raw[f.pages[1].content_span[0] : f.pages[1].content_span[1]]
    assert {c.id: c for c in g.pages[0].cells}["l1"].geometry["x"] == "99"


def test_stale_source_is_refused():
    f = load_drawio(drawio(M))
    with pytest.raises(DrawioRefused, match="changed"):
        apply_edits(f, 0, [Edit("l1", (F(9), F(9)), (9, 9), ("50", "100"))], "0" * 64)
    with pytest.raises(DrawioRefused, match="expected"):
        apply_edits(f, 0, [Edit("l1", (F(9), F(9)), (9, 9), ("51", "100"))], f.doc_hash)


def test_edits_apply_from_the_end_backwards():
    f = load_drawio(drawio(M))
    out = apply_edits(f, 0, [Edit("l1", (F(1), F(2)), (1, 2), ("50", "100")), Edit("l2", (F(3), F(4)), (3, 4), (None, None))], f.doc_hash)
    cells = {c.id: c for c in load_drawio(out).pages[0].cells}
    assert (cells["l1"].geometry["x"], cells["l2"].geometry["y"]) == ("1", "4")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio/test_patch.py -q`
Expected: FAIL, `ImportError … patch`.

- [ ] **Step 3: Implement `src/open_apprentice/drawio/patch.py`**

```python
"""Write label targets into <mxGeometry> x/y by byte-span replacement (spec 6). Coordinates are serialized in whole document units,
half rounding up, because draw.io renders HTML labels at whole units (round-trip spike). The exact target, the serialized value and
the old raw value are kept separately. The input is never modified: the result is new bytes."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from open_apprentice.drawio.parse import MAX_UPLOAD, DrawioFile, DrawioRefused, Page


@dataclass(frozen=True)
class Edit:
    cell_id: str
    exact: tuple[Fraction, Fraction]
    serialized: tuple[int, int]
    expected_old: tuple[Optional[str], Optional[str]]


def round_half_up(v: Fraction) -> int:
    return math.floor(v + Fraction(1, 2))


def plan_edits(page: Page, offsets: dict[str, tuple[Fraction, Fraction]], target_boxes: dict[str, tuple[Fraction, Fraction]]) -> list[Edit]:
    cells = {c.id: c for c in page.cells}
    out = []
    for cid, (bx, by) in sorted(target_boxes.items()):
        dx, dy = offsets[cid]
        ex, ey = bx - dx, by - dy
        g = cells[cid].geometry
        out.append(Edit(cid, (ex, ey), (round_half_up(ex), round_half_up(ey)), (g.get("x"), g.get("y"))))
    return out


def _set_attr(tag: str, key: str, value: int) -> str:
    pat = re.compile(rf'(\s{key}=")[^"]*(")')
    if pat.search(tag):
        return pat.sub(lambda m: f"{m.group(1)}{value}{m.group(2)}", tag, count=1)
    return tag.replace("<mxGeometry", f'<mxGeometry {key}="{value}"', 1)


def _patch_xml(page: Page, edits: list[Edit]) -> tuple[bytes, list[tuple[int, int, bytes]]]:
    """The page XML with edits applied, plus the (start, end, new tag) replacements relative to page.xml."""
    cells = {c.id: c for c in page.cells}
    reps = []
    for e in edits:
        c = cells.get(e.cell_id)
        if c is None or c.geometry_span is None:
            raise DrawioRefused(f"cell {e.cell_id!r} has no geometry to edit")
        if (c.geometry.get("x"), c.geometry.get("y")) != e.expected_old:
            raise DrawioRefused(f"cell {e.cell_id!r} is not where expected {e.expected_old}; the document changed")
        s, t = c.geometry_span
        tag = page.xml[s:t].decode("utf-8")
        tag = _set_attr(_set_attr(tag, "x", e.serialized[0]), "y", e.serialized[1])
        reps.append((s, t, tag.encode("utf-8")))
    xml = page.xml
    for s, t, new in sorted(reps, reverse=True):
        xml = xml[:s] + new + xml[t:]
    return xml, reps


def apply_edits(f: DrawioFile, page_index: int, edits: list[Edit], source_hash: str) -> bytes:
    if f.doc_hash != source_hash:
        raise DrawioRefused("the document changed since it was measured; measure it again")
    page = f.pages[page_index]
    new_xml, reps = _patch_xml(page, edits)
    s0, e0 = page.content_span
    if page.compressed:
        out = f.raw[:s0] + new_xml + f.raw[e0:]  # the edited page is written uncompressed; other pages keep their bytes
    else:
        out = f.raw
        for s, t, new in sorted(reps, reverse=True):
            out = out[: s0 + s] + new + out[s0 + t :]
    if len(out) > MAX_UPLOAD:
        raise DrawioRefused("the edited file would exceed the 2 MB upload limit")
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/drawio/patch.py tests/unit/drawio/test_patch.py
git commit -m "feat(drawio): whole-unit byte-span patcher with expected-old checks and compressed-page rewrite"
```

---

### Task 8: Publication checks and receipt

**Files:**
- Create: `src/open_apprentice/drawio/publish.py`, `tests/unit/drawio/test_publish.py`

**Interfaces:**
- Consumes: Tasks 2–7. Store `create(key, data) -> bool` (`open_apprentice.storage.store`).
- Produces:
  - `@dataclass(frozen=True) class Receipt: published: bool; key: Optional[str]; conformance: dict; preservation: dict; layout: dict; intent: Optional[dict]; profile: dict; notes: tuple[str, ...]`
  - `def publish(store: Store, key: str, f: DrawioFile, page_index: int, edits: list[Edit], targets: dict[str, tuple[Fraction, Fraction]], before: DrawioScene, render: Callable[[Page], Rendered], intent: Optional[dict] = None, drift: Optional[str] = None) -> Receipt`
  - `CONFORMANCE_TOLERANCE = Fraction(1, 2)` (spec 3.6), to which each label's rounding error is added.
  - The checks are reported separately. `published` is True only when conformance, preservation and layout all pass and
    `store.create` succeeded. Intent is passed through untouched and never gates or merges.

- [ ] **Step 1: Write the failing tests** (`tests/unit/drawio/test_publish.py`). They use a fake `render` that offsets measured boxes from
  the geometry the way a real render does (label box = geometry + (2, 3)), so no engine is needed:

```python
from fractions import Fraction as F

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import load_drawio
from open_apprentice.drawio.patch import plan_edits
from open_apprentice.drawio.publish import publish
from open_apprentice.drawio.render import parse_render
from open_apprentice.drawio.scene import build_scene
from open_apprentice.storage.store import LocalStore
from tests.unit.drawio.fixtures import drawio, label, model, node

M = model([node("n1", 40, 40, 100, 50), node("n2", 300, 40, 100, 50), label("l1", 50, 100)])


def fake_render(page, *, shift=(2, 3), size=(30, 14)):
    c = classify(page)
    labels, nodes = {}, {}
    for cid in c.movable + c.fixed:
        x, y, w, h = (float(v) for v in c.absolute[cid])
        if cid in c.movable:
            labels[cid] = {"box": {"x": x + shift[0], "y": y + shift[1], "w": size[0], "h": size[1]}, "lines": 1}
        else:
            nodes[cid] = {"state": {"x": x, "y": y, "w": w, "h": h}, "element": None}
    return parse_render({"labels": labels, "nodes": nodes, "profile": {"viewer_sha256": "test"}})


def prepare(targets):
    f = load_drawio(drawio(M))
    page = f.pages[0]
    before = build_scene(classify(page), fake_render(page), {"l1": ("n1", "note")})
    return f, before, plan_edits(page, before.offsets, targets)


def test_valid_move_publishes_a_new_artifact_and_reports_axes_separately(tmp_path):
    targets = {"l1": (F(150), F(58))}
    f, before, edits = prepare(targets)
    store = LocalStore(tmp_path)
    r = publish(store, "out/a.drawio", f, 0, edits, targets, before, fake_render)
    assert r.published and store.get("out/a.drawio") is not None
    assert r.conformance["ok"] and r.preservation["ok"] and r.layout["ok"] and r.intent is None
    row = r.conformance["labels"]["l1"]
    assert (row["exact"], row["serialized"], row["measured"]) == (["148", "55"], [148, 55], ["150", "58"])
    assert "connector crossings are not checked" in " ".join(r.notes)
    assert "not measured" in " ".join(r.notes)


def test_rounding_into_a_neighbour_blocks_publication(tmp_path):
    targets = {"l1": (F(541, 2), F(58))}  # box right edge 270.5 + 30 = 300.5 → rounds into n2 at x=300
    f, before, edits = prepare(targets)
    store = LocalStore(tmp_path)
    r = publish(store, "out/b.drawio", f, 0, edits, targets, before, fake_render)
    assert not r.published and not r.layout["ok"] and store.get("out/b.drawio") is None
    assert r.conformance["labels"]["l1"]["exact"] != [str(v) for v in r.conformance["labels"]["l1"]["serialized"]]


def test_renderer_disagreement_fails_conformance_only(tmp_path):
    targets = {"l1": (F(150), F(58))}
    f, before, edits = prepare(targets)
    r = publish(LocalStore(tmp_path), "out/c.drawio", f, 0, edits, targets, before, lambda p: fake_render(p, shift=(4, 3)))
    assert not r.published and not r.conformance["ok"] and r.preservation["ok"]


def test_existing_key_is_never_overwritten(tmp_path):
    targets = {"l1": (F(150), F(58))}
    f, before, edits = prepare(targets)
    store = LocalStore(tmp_path)
    store.create("out/d.drawio", b"other")
    r = publish(store, "out/d.drawio", f, 0, edits, targets, before, fake_render)
    assert not r.published and store.get("out/d.drawio").data == b"other"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio/test_publish.py -q`
Expected: FAIL, `ImportError … publish`.

- [ ] **Step 3: Implement `src/open_apprentice/drawio/publish.py`**

```python
"""Publish a patched .drawio only if it parses, renders and passes every output check (spec 6). Conformance, preservation and
layout safety are separate axes; intent is passed through from the caller and never merged into them."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Optional

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioFile, DrawioRefused, Page, load_drawio
from open_apprentice.drawio.patch import Edit, apply_edits
from open_apprentice.drawio.render import Box, Rendered
from open_apprentice.drawio.scene import DrawioScene
from open_apprentice.storage.store import Store

CONFORMANCE_TOLERANCE = Fraction(1, 2)
NOTES = ("connector crossings are not checked",)


@dataclass(frozen=True)
class Receipt:
    published: bool
    key: Optional[str]
    conformance: dict
    preservation: dict
    layout: dict
    intent: Optional[dict]
    profile: dict
    notes: tuple[str, ...]


def _overlap(a: Box, b: Box) -> bool:
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h  # touching is allowed


def _preservation(before: Page, after: Page, edited: set[str]) -> dict:
    diffs = []
    if before.model != after.model:
        diffs.append("page settings changed")
    if [c.id for c in before.cells] != [c.id for c in after.cells]:
        diffs.append("cells added, removed or reordered")
    for a, b in zip(before.cells, after.cells):
        same = (a.parent, a.vertex, a.edge, a.style, a.value, a.wrapper) == (b.parent, b.vertex, b.edge, b.style, b.value, b.wrapper)
        ga = {k: v for k, v in a.geometry.items() if not (a.id in edited and k in ("x", "y"))}
        gb = {k: v for k, v in b.geometry.items() if not (a.id in edited and k in ("x", "y"))}
        if not same or ga != gb:
            diffs.append(f"cell {a.id!r} changed beyond its x/y")
    return {"ok": not diffs, "differences": diffs}


def publish(store: Store, key: str, f: DrawioFile, page_index: int, edits: list[Edit], targets: dict[str, tuple[Fraction, Fraction]],
            before: DrawioScene, render: Callable[[Page], Rendered], intent: Optional[dict] = None,
            drift: Optional[str] = None) -> Receipt:  # fmt: skip
    new = apply_edits(f, page_index, edits, f.doc_hash)
    g = load_drawio(new)
    others_ok = all(
        new[q.content_span[0] : q.content_span[1]] == f.raw[p.content_span[0] : p.content_span[1]]
        for p, q in zip(f.pages, g.pages) if p.index != page_index
    )  # fmt: skip
    page = g.pages[page_index]
    c = classify(page)
    r = render(page)
    profile = dict(r.profile)
    notes = NOTES + (
        f"measured under profile {profile.get('viewer_sha256', '?')[:12]}/{profile.get('font', '?')}; "
        + (drift or "drift against other font environments was not measured"),
    )
    old = {o["id"]: o for o in before.scene["objects"]}
    rows, conf_ok = {}, True
    for e in edits:
        if e.cell_id not in r.labels:
            raise DrawioRefused(f"label {e.cell_id!r} could not be measured after the edit")
        m, lines = r.labels[e.cell_id]
        tx, ty = targets[e.cell_id]
        rounding = max(abs(e.serialized[0] - e.exact[0]), abs(e.serialized[1] - e.exact[1]))
        err = max(abs(m.x - tx), abs(m.y - ty))
        size = max(abs(m.w - old[e.cell_id]["w"]), abs(m.h - old[e.cell_id]["h"]))
        ok = err <= CONFORMANCE_TOLERANCE + rounding and size <= CONFORMANCE_TOLERANCE and lines == 1
        conf_ok &= ok
        rows[e.cell_id] = {"exact": [str(v) for v in e.exact], "serialized": list(e.serialized), "measured": [str(m.x), str(m.y)],
                           "error": str(err), "tolerance": str(CONFORMANCE_TOLERANCE + rounding), "size_change": str(size),
                           "lines": lines, "ok": ok}  # fmt: skip
    pres = _preservation(f.pages[page_index], page, {e.cell_id for e in edits})
    if not others_ok:
        pres = {"ok": False, "differences": pres["differences"] + ["another page's bytes changed"]}
    finals = {cid: r.labels[cid][0] for cid in c.movable if cid in r.labels}
    finals.update({cid: r.nodes[cid][0] for cid in c.fixed if cid in r.nodes})
    finals.update({cid: r.labels[cid][0] for cid in c.fixed if cid in r.labels})
    outside = [cid for cid, b in finals.items() if b.x < 0 or b.y < 0 or b.x + b.w > c.width or b.y + b.h > c.height]
    overlaps = sorted({tuple(sorted((e.cell_id, o))) for e in edits for o, b in finals.items()
                       if o != e.cell_id and e.cell_id in finals and _overlap(finals[e.cell_id], b)})  # fmt: skip
    layout = {"ok": not outside and not overlaps, "outside": outside, "overlaps": [list(p) for p in overlaps]}
    passed = conf_ok and pres["ok"] and layout["ok"]
    published = passed and store.create(key, new)
    return Receipt(published, key if published else None, {"ok": conf_ok, "labels": rows}, pres, layout, intent, profile, notes)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/drawio/publish.py tests/unit/drawio/test_publish.py
git commit -m "feat(drawio): publication checks with separate conformance, preservation and layout axes"
```

---

### Task 9: Round-trip matrix against the real engine

**Files:**
- Create: `tests/integration/drawio/test_roundtrip_matrix.py`

**Interfaces:**
- Consumes: everything above plus the `engine_url` fixture (Task 5).

- [ ] **Step 1: Write the matrix test.** Each spec 6 matrix row is one test. Every row patches, publishes and re-measures through the real
  engine:

```python
from fractions import Fraction as F

import pytest

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.patch import plan_edits
from open_apprentice.drawio.publish import publish
from open_apprentice.drawio.render import render_page
from open_apprentice.drawio.scene import build_scene
from open_apprentice.storage.store import LocalStore
from tests.unit.drawio.fixtures import LABEL, drawio, label, model, node


def run(engine_url, tmp_path, raw, cell, dx, dy, page_index=0):
    f = load_drawio(raw)
    page = f.pages[page_index]
    c = classify(page)
    r = render_page(page, engine_url)
    nodes = [n for n in c.fixed if n in r.nodes]
    s = build_scene(c, r, {m: (nodes[0], "note") for m in c.movable})
    o = next(o for o in s.scene["objects"] if o["id"] == cell)
    targets = {cell: (o["x"] + dx, o["y"] + dy)}
    edits = plan_edits(page, s.offsets, targets)
    rec = publish(LocalStore(tmp_path), f"out/{cell}.drawio", f, page_index, edits, targets, s, lambda p: render_page(p, engine_url))
    return f, rec, LocalStore(tmp_path).get(f"out/{cell}.drawio")


@pytest.mark.parametrize("align", ["left", "center", "right"])
def test_aligned_html_labels(engine_url, tmp_path, align):
    raw = drawio(model([node("n1", 40, 40), label("l1", 200, 200, align=align)]))
    _, rec, out = run(engine_url, tmp_path, raw, "l1", F(20), F(-10))
    assert rec.published, rec


def test_plain_text_label(engine_url, tmp_path):
    raw = drawio(model([node("n1", 40, 40), label("l1", 200, 200, style="text;align=left;verticalAlign=middle;")]))
    assert run(engine_url, tmp_path, raw, "l1", F(15), F(5))[1].published


def test_nonzero_viewer_translate(engine_url, tmp_path):
    raw = drawio(model([node("n1", 500, 400), label("l1", 600, 520)], w=900, h=700))
    assert run(engine_url, tmp_path, raw, "l1", F(10), F(10))[1].published


def test_fractional_target_requires_rounding(engine_url, tmp_path):
    raw = drawio(model([node("n1", 40, 40), label("l1", 200, 200)]))
    _, rec, _ = run(engine_url, tmp_path, raw, "l1", F(75, 2), F(-12))
    row = rec.conformance["labels"]["l1"]
    assert rec.published and row["exact"] != [str(v) for v in row["serialized"]]


def test_missing_coordinates_inserted(engine_url, tmp_path):
    raw = drawio(model([node("n1", 300, 200), label("l1", None, None)]))
    _, rec, out = run(engine_url, tmp_path, raw, "l1", F(30), F(40))
    geo = {c.id: c for c in load_drawio(out.data).pages[0].cells}["l1"].geometry
    assert rec.published and "x" in geo and "y" in geo


def test_compressed_page(engine_url, tmp_path):
    raw = drawio(model([node("n1", 40, 40), label("l1", 200, 200)]), compressed=(True,))
    _, rec, out = run(engine_url, tmp_path, raw, "l1", F(10), F(10))
    assert rec.published and not load_drawio(out.data).pages[0].compressed


def test_multi_page_untouched_bytes(engine_url, tmp_path):
    raw = drawio(model([node("z", 10, 10)]), model([node("n1", 40, 40), label("l1", 200, 200)]))
    f, rec, out = run(engine_url, tmp_path, raw, "l1", F(10), F(10), page_index=1)
    s, e = f.pages[0].content_span
    assert rec.published and out.data[s:e] == f.raw[s:e]


def test_real_corpus_file_round_trip(engine_url, tmp_path):
    raw = open("tests/fixtures/drawio_corpus/dev/d2.drawio", "rb").read()
    f = load_drawio(raw)
    cell = classify(f.pages[0]).movable[0]
    assert run(engine_url, tmp_path, raw, cell, F(0), F(4))[1].published


def test_refuses_unmeasurable_label(engine_url):
    raw = drawio(model([node("n1", 40, 40), label("l1", 200, 200, value="&amp;nbsp;")]))
    page = load_drawio(raw).pages[0]
    with pytest.raises(DrawioRefused, match="measured"):
        build_scene(classify(page), render_page(page, engine_url), {"l1": ("n1", "note")})


def test_refuses_out_of_rectangle_content():
    with pytest.raises(DrawioRefused, match="outside the page"):
        classify(load_drawio(drawio(model([node("n1", 560, 40)]))).pages[0])
```

Note: `label(..., value="&amp;nbsp;")` stores `&nbsp;` literally in the value, so the viewer renders a non-breaking space with no
measurable glyph run. The parser lets it through, because `classify` only refuses an empty value after `strip()`, and `&nbsp;` is not
empty text. The font-substitution row is covered by the engine test "Helvetica resolves to the bundled Liberation Sans" (Task 4).

- [ ] **Step 2: Run the matrix**

Run: `OA_ENGINE_TESTS=1 PYTHONPATH=src:. .venv/bin/python -m pytest tests/integration/drawio -q`
Expected: PASS. Any failure is a real adapter defect: debug it with superpowers:systematic-debugging, and do not loosen a tolerance. If a
row fails because the viewer behaves differently from the spike (for example, plain-text label inset), record a ruling with the measured
numbers.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/drawio/test_roundtrip_matrix.py
git commit -m "test(drawio): spec 6 round-trip matrix against the real engine"
```

---

### Task 10: CLI checks, drift report, staging integration (run gated on approval)

**Files:**
- Create: `scripts/drawio/drift_measure.mjs`, `scripts/drawio/drift_report.py`, `tests/unit/drawio/test_cli.py`
- Modify: `src/open_apprentice/cli.py` (commands `drawio-check`, `staging-check`), `docs/deploy_staging_proposal.md`, `docs/implementation_audit.md`

**Interfaces:**
- Produces:
  - `oa drawio-check FILE [--page N]` prints JSON `{doc_hash, page, movable, fixed, reasons, demoted, profile, refused?}` and exits 0, or
    exits 2 with the refusal reason.
  - `oa staging-check --file FILE` runs three checks:
    1. render and measure (as `drawio-check`);
    2. a GCS conditional-update race using `GcsStore` when `OA_STORE=gcs`, otherwise `LocalStore` (two writers, exactly one
       `PreconditionFailed`);
    3. write-then-read survival (`--phase write` stores a marker; `--phase read` verifies it after a restart).

    It prints one JSON line per check and exits non-zero on any failure.

- [ ] **Step 1: Write the failing CLI test** (`tests/unit/drawio/test_cli.py`). It uses typer's `CliRunner` with a refused file (no engine
  needed) and the local-store race:

```python
import json

from typer.testing import CliRunner

from open_apprentice.cli import app
from tests.unit.drawio.fixtures import drawio, model, node


def test_drawio_check_reports_refusal_reason(tmp_path):
    p = tmp_path / "bad.drawio"
    p.write_bytes(drawio(model([node("n1", -5, 0)])))
    r = CliRunner().invoke(app, ["drawio-check", str(p)])
    assert r.exit_code == 2 and "outside the page" in r.output


def test_staging_check_store_race_on_local_store(tmp_path, monkeypatch):
    monkeypatch.setenv("OA_STORE", "local")
    monkeypatch.setenv("OA_STORE_DIR", str(tmp_path))
    r = CliRunner().invoke(app, ["staging-check", "--only", "race"])
    line = json.loads(r.output.strip().splitlines()[-1])
    assert r.exit_code == 0 and line == {"check": "race", "ok": True, "winners": 1, "precondition_failures": 1}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio/test_cli.py -q`
Expected: FAIL, `No such command 'drawio-check'`.

- [ ] **Step 3: Implement the commands in `src/open_apprentice/cli.py`**, following the existing `@app.command` style:

```python
@app.command("drawio-check")
def drawio_check(file: Path, page: int = 0) -> None:
    """Parse, classify, render and measure one page of a .drawio file; print what is movable and why anything is not."""
    from open_apprentice.drawio.classify import classify
    from open_apprentice.drawio.parse import DrawioRefused, load_drawio
    from open_apprentice.drawio.render import render_page

    try:
        f = load_drawio(file.read_bytes())
        c = classify(f.pages[page])
        r = render_page(f.pages[page], load_settings().engine_url, png=False)
    except DrawioRefused as e:
        typer.echo(json.dumps({"refused": str(e)}))
        raise typer.Exit(2)
    demoted = {cid: "renders on more than one line" for cid in c.movable if r.labels.get(cid, (None, 1))[1] > 1}
    typer.echo(json.dumps({"doc_hash": f.doc_hash, "page": f.pages[page].id, "movable": list(c.movable), "fixed": list(c.fixed),
                           "reasons": c.reasons, "demoted": demoted, "missing": list(r.missing), "profile": r.profile}))  # fmt: skip


@app.command("staging-check")
def staging_check(file: Optional[Path] = None, only: str = "all", phase: str = "write") -> None:
    """Staging integration (spec 10): render/measure, a conditional-update race, and restart survival. Runs against whatever
    OA_STORE points at; it creates no cloud resources."""
    from open_apprentice.storage.store import PreconditionFailed

    store = _store_from_env()
    failed = False
    if only in ("all", "race"):
        key = f"staging/race-{uuid.uuid4().hex}"
        g = store.put(key, b"0", if_generation=None)
        results = []
        for v in (b"a", b"b"):
            try:
                store.put(key, v, if_generation=g)
                results.append("ok")
            except PreconditionFailed:
                results.append("precondition")
        ok = results.count("ok") == 1 and results.count("precondition") == 1
        typer.echo(json.dumps({"check": "race", "ok": ok, "winners": results.count("ok"), "precondition_failures": results.count("precondition")}))
        failed |= not ok
    if only in ("all", "survival"):
        if phase == "write":
            store.put("staging/marker", b"alive", if_generation=None) if store.get("staging/marker") is None else None
            typer.echo(json.dumps({"check": "survival", "phase": "write", "ok": True}))
        else:
            ok = (b := store.get("staging/marker")) is not None and b.data == b"alive"
            typer.echo(json.dumps({"check": "survival", "phase": "read", "ok": ok}))
            failed |= not ok
    if only in ("all", "render") and file is not None:
        drawio_check(file)
    if failed:
        raise typer.Exit(1)
```

`_store_from_env()` returns `GcsStore(google.cloud.storage.Client().bucket(os.environ["OA_BUCKET"]))` when `OA_STORE=gcs`, and otherwise
`LocalStore(os.environ.get("OA_STORE_DIR", ".oa-store"))`. Reuse an existing helper if `cli.py` or `storage/` already has one (check
with `grep -rn "OA_STORE" src`). Add the imports (`json`, `uuid`, `Path`, `Optional`) only if they are missing.

- [ ] **Step 4: Write the drift report scripts (authoring Mac only, not run in CI)**

`scripts/drawio/drift_measure.mjs` takes an SVG exported by the draw.io CLI and prints the label boxes. It renders the SVG in Chromium
with **no** font override (real Helvetica), measures each `foreignObject` text run with the same Range primitive, and keys each box by
its text content (corpus label texts are unique).

`scripts/drawio/drift_report.py` does the following for each `tests/fixtures/drawio_corpus/dev/*.drawio`:
1. Run `drawio -x -f svg --embed-svg-fonts false -o $TMPDIR/<name>.svg <file>`.
2. Run the measure script.
3. Render the same page through `/drawio/render` (profile font).
4. Match labels by text and report the maximum box difference per file.

It writes `docs/corpus/drift_report.md` with a table (file, labels, max Δ) and the profile hashes. It exits non-zero with a clear message
if the `drawio` CLI is absent. Run it once on the Mac and commit the report.

- [ ] **Step 5: Update `docs/deploy_staging_proposal.md`** to match the real interfaces:
  - **Check 1:** `oa staging-check --file tests/fixtures/drawio_corpus/dev/d1.drawio --only render`, run inside the staging image.
  - **Check 2:** `--only race` with `OA_STORE=gcs`.
  - **Check 4:** `--only survival --phase write`, then `gcloud run services update … --update-env-vars OA_RESTART=<n>` to force a new
    revision, then `--phase read`.
  - **Check 3 (Cloud Tasks dispatch)** moves to Plan 4, which builds the worker endpoint.
  - Add one resource row, a Cloud Run **job** `oa-staging-check` using the same image (command `oa staging-check`), and its create and
    delete commands in "Commands" and "Teardown".
  - The cost estimate is unchanged in kind: jobs bill per execution second.

- [ ] **Step 6: Run the tests, lint and import contracts**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/drawio -q && .venv/bin/ruff check src tests scripts && .venv/bin/black --check src tests scripts && uv run lint-imports && npm run lint`
Expected: PASS; contracts kept, 0 broken.

- [ ] **Step 7: Commit, then stop for approval**

```bash
git add src/open_apprentice/cli.py scripts/drawio tests/unit/drawio/test_cli.py docs/deploy_staging_proposal.md docs/corpus/drift_report.md docs/implementation_audit.md
git commit -m "feat(drawio): drawio-check and staging-check commands, drift report, staging proposal matched to real interfaces"
```

Do **not** run anything against GCP. Report to the owner that staging is ready to run and needs their approval of the updated proposal.

---

## Final verification (before the whole-branch review)

- `OA_ENGINE_TESTS=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q tests` (sandbox disabled) — all pass.
- The same suite on 3.12: `OA_ENGINE_TESTS=1 PYTHONPATH=src:. /private/tmp/claude-501/venv312/bin/python -m pytest -q tests`.
- `npm test` (engine), `npm run lint`, `.venv/bin/ruff check src tests scripts`, `.venv/bin/black --check src tests scripts`,
  `uv run lint-imports` — the exact CI steps.
- `docker build -f docker/demo.Dockerfile .` succeeds, and the image contains `services/engine/vendor/` (the hash test runs at engine
  start because `drawio.js` verifies on import).
