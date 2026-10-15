# Real-file corpus: provenance

Six technical diagrams authored by Claude (Claude Code) in the **draw.io web editor at app.diagrams.net**, with the owner's approval
(2026-10-15) to draw them there and save them through the browser. They are internally authored editor
files, **not** independent user files. Positions and texts were chosen by Claude; the editor supplied cell ids, default styles and
serialization (label widths were set by hand to one line, not by the editor's autosize).

## Design (written before drawing)

| Id | Title | Page (w×h) | Content | Variation it covers |
|---|---|---|---|---|
| A | Checkout service | 800×400 landscape | 6 boxes, 6 labels (1 warning) | baseline, roomy |
| B | Data pipeline | 640×300 landscape | 7 boxes in tight rows, 6 labels (1 warning) | crowding: right-hand spots blocked |
| C | Training workflow | 500×700 portrait | 5 boxes stacked, 5 labels (1 warning) | portrait aspect, vertical neighbours |
| D | Edge network | 600×360 | 6 boxes, some near the right page edge, 6 labels (2 warnings) | off-page right-hand spots |
| E | Microservices | 900×500, **two pages** | page 1: 7 boxes, 7 labels (1 warning); page 2: small legend | multi-page file |
| F | Analytics stack | 700×450 | 6 boxes, 6 labels incl. one long single-line label (1 warning) | **saved compressed**, long label |

Labels are draw.io "Text" shapes (Formatted Text on, the default), placed below or beside their box as a person would; roles are
assigned later through the mapping step, not encoded in the file.

## Development / final split

Assigned before drawing by a seeded shuffle: `random.Random(20261015).shuffle(["A","B","C","D","E","F"])` →
`['C','A','E','D','F','B']`. First three are development, last three are final:

- **Development:** C, A, E → `tests/fixtures/drawio_corpus/dev/{d1,d2,d3}.drawio` (d1 = C, d2 = A, d3 = E)
- **Final (frozen):** D, F, B → `benchmarks/final/drawio/{f1,f2,f3}.drawio` (f1 = D, f2 = F, f3 = B), git-ignored; not opened by any
  development code or by Claude until the Plan 5 frozen run.

## How they were made (2026-10-15)

The Claude in Chrome extension was not connected, so the editor was driven in the project's own Playwright Chromium (headless),
by `scripts/corpus/author_drawio.mjs` (kept as the reproducible record of every GUI step). Only GUI operations were used:
- boxes: click the **Rectangle** item of the General palette; labels: click the **Text** item (Formatted Text on, the default);
- position and size: **Edit > Edit Geometry** dialog (Cmd+Shift+M), Left/Top/Width/Height; labels widened to one line
  (draw.io's default Text box is 60 wide and wraps "rate limited" onto two lines; a person would drag it wider);
- text: Enter, select all, type, click outside the page;
- connectors: hover the source box and drag from its **right-hand blue arrow** onto the target box;
- page size: **File > Page Setup** (Custom); second page of E: the **+** page button; compression for F: **File > Properties >
  Compressed**; saving: **File > Save as**, Type XML File (.drawio), Where **Download**.
The editor generated the cell ids, the default styles (e.g. `text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;
align=center;verticalAlign=middle;rounded=0;rotation=0;`) and the serialization (`host="app.diagrams.net"`).
The saved files were downloaded into the session scratchpad (not the owner's Downloads folder) and copied into place.

Every file was checked against its design with `scripts/corpus/verify_corpus.py` (each box and label at its designed geometry and
text, every designed connector present with source and target, page size, page count, compression): **6/6 OK**.

## Files and hashes (SHA-256)

| File | Design | Notes |
|---|---|---|
| `tests/fixtures/drawio_corpus/dev/d1.drawio` | C Training workflow | `12ecbe44beba03dff297bf49a905578cb16cd163ba1926353312243cf81190ef` |
| `tests/fixtures/drawio_corpus/dev/d2.drawio` | A Checkout service | `51792b575c7fd19e8418269c8925382fcb76b352c7c92a8d135e4d751bb7b2bc` |
| `tests/fixtures/drawio_corpus/dev/d3.drawio` | E Microservices (2 pages) | `6a27aeec4c1927ce5bbec8e53ce1594ca2fcc1737b58b844887883b8fd1205ee` |
| `benchmarks/final/drawio/f1.drawio` (git-ignored, frozen) | D Edge network | `cf538204a77dbda9077827c0dceba850748ab032e53d42e3e9fba3c3e0215d40` |
| `benchmarks/final/drawio/f2.drawio` (git-ignored, frozen) | F Analytics stack (compressed) | `6d405ac75d76a21512383e7a97ee86debb03b757d720fa9b9fff6abf3625e17b` |
| `benchmarks/final/drawio/f3.drawio` (git-ignored, frozen) | B Data pipeline | `23b305bc21766e2f314b8e5478bb6238c0b2fc60d4d0aa2bb1289916afde843a` |

The final three were verified once (above) at authoring time and then frozen; no development code reads them before Plan 5.

## Known limits of this corpus
- Authored by the same agent that builds the importer (Claude), from a written design; not user files and not from another tool.
- One editor (draw.io web); no Inkscape/Figma/Lucid exports.
- Label roles (note/warning) are not in the files; the word "warning:" in some label texts is content, roles come from mapping.
