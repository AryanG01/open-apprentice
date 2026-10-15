# Plan 1: Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the native round trip on a real draw.io file, author the real-file corpus, and build the event-sourced learning core (store, event log, teacher protocol, constraint derivation, pure step policy with batch questions and preview, attempt accounting, local executor, simulator teacher, isolation) so that a complete teaching episode runs offline against a scripted provider and a simulated teacher, and replays with no duplicate effects.

**Architecture:** Every session is an append-only chain of immutable events committed by compare-and-set on one manifest. A pure `step(events, config) -> Action` decides the next action; a local executor performs actions (model proposals, teacher requests, version storage) and appends result events. The teacher is reached only through a typed protocol; in evaluation it is a separate process holding the hidden specification.

**Tech Stack:** Python 3.12 (project venv 3.13 locally; CI on 3.12), pytest, pytest-asyncio, existing `concepts/rules.py` + `rule_text.py` + `hypotheses.py`, Node + Playwright (already in `node_modules`) for the spike, draw.io desktop 32.4.1 CLI (installed at `/opt/homebrew/bin/drawio`).

**Spec:** `docs/superpowers/specs/2026-10-15-teach-correct-reuse-design.md` (read sections 2–4 and 7 before starting). Roadmap: `docs/superpowers/plans/2026-10-15-roadmap.md`.

## Global Constraints

- Python `requires-python >=3.12,<3.14`; black line length 100; ruff clean; type hints on every function.
- No `eval`/`exec`/dynamic code loading. Model programs run only through `concepts/rules.py:evaluate_rule`.
- New packages `open_apprentice.teaching`, `open_apprentice.storage`, `open_apprentice.documents`, `open_apprentice.skills` must never import `open_apprentice.evaluation` (enforced by import-linter, Task 11).
- Tolerance: answers match by maximum coordinate error ≤ `Fraction(1, 2)`; `ChooseOutput` alternatives pairwise differ by > `Fraction(1)` in at least one corresponding coordinate.
- Budgets per initial learning cycle: ≤ 3 `ChooseOutput` interactions (any response), ≤ 1 `RequestDemonstration`, ≤ 1 `ConfirmPreview(learning_preview)` of ≤ 3 items, ≤ 8 provider attempts (retries count).
- Allowances per cycle: one initial proposal round, ≤ 1 contrastive round, ≤ 1 contradiction revision.
- Coordinates and outputs are exact `Fraction`s; JSON serialization of a Fraction is the string `"n/d"` (or an int when the denominator is 1), matching `hypotheses.neutral`.
- Provider failure with no retries left is outcome `error`, never `abstain`.
- Paid live calls are NOT part of this plan. All tests use scripted providers. Any live call needs a separate manifest approved by the owner.
- Run the FULL local suite before every push: `OA_ENGINE_TESTS=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q tests` (needs the sandbox disabled for Chromium). Never chain `git commit` after tests with `;` — use `&&`.

## Review Focus

1. **A teacher response arrives for a request that is no longer outstanding** (old tab, duplicate delivery): it must be rejected and create no constraint. Test in Task 4 (`test_response_to_answered_request_is_rejected`).
2. **Replay after a crash between writing an event and committing the manifest**: the orphan event must stay invisible and the next append must succeed. Test in Task 3 (`test_orphan_event_is_invisible_and_append_continues`).
3. **A candidate program raises at runtime on one batch scene but not others**: it must be rejected with reason `runtime`, never crash the step. Test in Task 6 (`test_runtime_failure_rejects_candidate_without_crashing`).
4. **All candidates produce identical output on every batch scene but are distinct ASTs**: step must not ask a question, must keep both, and must preview (search outcome `completed_no_disagreement` on the searched set). Test in Task 6 (`test_indistinguishable_candidates_go_to_preview_and_both_survive`).
5. **The simulator receives two alternatives that both match the truth within tolerance**: protocol error, not an arbitrary choice. Test in Task 9 (`test_ambiguous_match_is_protocol_error`).

---

## File Structure

| Path | Responsibility |
|---|---|
| `scripts/spikes/drawio_roundtrip.mjs` | Spike: render a `.drawio` page in locked Chromium with the local viewer, measure labels in document coordinates (kept as evidence) |
| `scripts/spikes/drawio_patch.py` | Spike: structural geometry patch for one label cell (kept as evidence) |
| `docs/spikes/2026-10-16-drawio-roundtrip.md` | Spike findings and gate verdict |
| `docs/corpus/drawio_provenance.md` | Real-file corpus provenance (6 files; 3 frozen) |
| `tests/fixtures/drawio_corpus/dev/*.drawio` | The three development diagrams |
| `benchmarks/final/drawio/*.drawio` | The three frozen diagrams (git-ignored) |
| `src/open_apprentice/storage/store.py` | `Store` protocol, `Blob`, `PreconditionFailed`, `LocalStore` (atomic create, generation CAS) |
| `src/open_apprentice/teaching/__init__.py` | package marker |
| `src/open_apprentice/teaching/codec.py` | JSON codec for Fractions and canonical hashing |
| `src/open_apprentice/teaching/events.py` | `Event`, event types, `SessionLog` (commit chain, replay) |
| `src/open_apprentice/teaching/teacher.py` | Request/response types, validation (`ProtocolError`), `Teacher` protocol, `SubprocessTeacher` client |
| `src/open_apprentice/teaching/constraints.py` | Derive active `Constraint`s from committed events |
| `src/open_apprentice/teaching/step.py` | Pure step policy, actions, budgets, candidate filtering, question selection, commit predicate |
| `src/open_apprentice/teaching/accounting.py` | Attempt records and exposure ledger (reserve → dispatch → settle / unknown) |
| `src/open_apprentice/teaching/executor.py` | Local executor: perform actions, append results, idempotent claims |
| `src/open_apprentice/teaching/isolation.py` | Import audit hook for learner processes |
| `src/open_apprentice/evaluation/teacher_sim.py` | Simulator teacher process (JSON lines) holding the hidden spec |
| `docs/implementation_audit.md` | Current-state audit mapping spec requirements to code |
| `tests/unit/teaching/test_*.py` | Unit tests per module |

---

### Task 0: Round-trip spike (spec gate 2.3, part 1)

**Files:**
- Create: `scripts/spikes/drawio_roundtrip.mjs`, `scripts/spikes/drawio_patch.py`, `scripts/spikes/vendor/README.md`, `docs/spikes/2026-10-16-drawio-roundtrip.md`
- Create (local, git-ignored): `scripts/spikes/vendor/viewer-static.min.js`

**Interfaces:**
- Consumes: draw.io CLI at `/opt/homebrew/bin/drawio` (32.4.1); `node_modules/playwright`.
- Produces: a written verdict (pass/fail per gate criterion) that Plan 3 depends on; nothing imported by later Plan 1 tasks.

This is a time-boxed investigation (≤ 1 day). The scripts are kept as evidence, not product code.

- [ ] **Step 1: Obtain the pinned viewer and record its hash.** The installed app bundle ships `app.min.js` but not `viewer-static.min.js` (checked 15 Oct). Ask the owner for approval to download `src/main/webapp/js/viewer-static.min.js` from the `jgraph/drawio` GitHub repository at tag `v32.4.1` (Apache-2.0). After approval:

```bash
mkdir -p scripts/spikes/vendor
curl -fsSL -o scripts/spikes/vendor/viewer-static.min.js \
  https://raw.githubusercontent.com/jgraph/drawio/v32.4.1/src/main/webapp/js/viewer-static.min.js
shasum -a 256 scripts/spikes/vendor/viewer-static.min.js
printf 'scripts/spikes/vendor/*.js\n' >> .gitignore
```

Write `scripts/spikes/vendor/README.md` with the URL, tag, licence (Apache-2.0) and the SHA-256 printed above. If the download is refused or the file is missing at that tag, record that and use `app.min.js` extracted from `/Applications/draw.io.app/Contents/Resources/app.asar` (`npx @electron/asar extract-file`) as the fallback viewer; record which was used.

- [ ] **Step 2: Write a tiny test diagram for the spike** at `scripts/spikes/fixtures/spike.drawio` (uncompressed, one page `pageScale="1"`, three rectangle nodes, three separate `text;html=1` label cells with absolute geometry, one edge). Use this exact content:

```xml
<mxfile host="Electron" version="32.4.1">
  <diagram id="p1" name="Page-1">
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1" pageScale="1" pageWidth="600" pageHeight="300" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="n1" value="API" style="rounded=0;whiteSpace=wrap;html=1;" vertex="1" parent="1"><mxGeometry x="40" y="40" width="100" height="50" as="geometry"/></mxCell>
        <mxCell id="n2" value="Queue" style="rounded=0;whiteSpace=wrap;html=1;" vertex="1" parent="1"><mxGeometry x="240" y="40" width="100" height="50" as="geometry"/></mxCell>
        <mxCell id="n3" value="Worker" style="rounded=0;whiteSpace=wrap;html=1;" vertex="1" parent="1"><mxGeometry x="440" y="40" width="100" height="50" as="geometry"/></mxCell>
        <mxCell id="e1" style="edgeStyle=orthogonalEdgeStyle;html=1;" edge="1" parent="1" source="n1" target="n2"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="l1" value="rate limited" style="text;html=1;align=left;verticalAlign=middle;" vertex="1" parent="1"><mxGeometry x="40" y="100" width="90" height="20" as="geometry"/></mxCell>
        <mxCell id="l2" value="retries" style="text;html=1;align=center;verticalAlign=middle;" vertex="1" parent="1"><mxGeometry x="240" y="100" width="60" height="20" as="geometry"/></mxCell>
        <mxCell id="l3" value="drains nightly" style="text;html=1;align=right;verticalAlign=middle;" vertex="1" parent="1"><mxGeometry x="440" y="100" width="100" height="20" as="geometry"/></mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

- [ ] **Step 3: Write the render-and-measure script** `scripts/spikes/drawio_roundtrip.mjs`:

```javascript
// Spike: render one .drawio page with the locally served viewer in a network-blocked Chromium and measure labels.
// Usage: node scripts/spikes/drawio_roundtrip.mjs <file.drawio> <viewer.js> > out.json
import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const [file, viewerPath] = process.argv.slice(2);
const xml = readFileSync(file, "utf8");
const viewer = readFileSync(viewerPath, "utf8");
const browser = await chromium.launch();
const context = await browser.newContext({ javaScriptEnabled: true });
await context.route("**/*", (route) => route.abort()); // network blocked: everything must be inline
const page = await context.newPage();
await page.setContent(`<!doctype html><html><body style="margin:0"><div id="c"></div></body></html>`);
await page.addScriptTag({ content: viewer });
const result = await page.evaluate(async (xmlText) => {
  const doc = mxUtils.parseXml(xmlText);
  const container = document.getElementById("c");
  const v = new GraphViewer(container, doc.documentElement, { highlight: "none", nav: false, resize: false, center: false });
  const graph = v.graph;
  graph.view.setScale(1);
  await document.fonts.ready;
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const svg = container.querySelector("svg");
  const toDoc = (cx, cy) => {
    const p = svg.createSVGPoint(); p.x = cx; p.y = cy;
    const q = p.matrixTransform(svg.getScreenCTM().inverse());       // screen -> view (svg user units)
    const s = graph.view.scale, t = graph.view.translate;            // view -> document
    return { x: q.x / s - t.x, y: q.y / s - t.y };
  };
  const out = { translate: { x: graph.view.translate.x, y: graph.view.translate.y }, scale: graph.view.scale, labels: {}, nodes: {} };
  for (const cell of Object.values(graph.model.cells)) {
    const st = graph.view.getState(cell);
    if (!st || !cell.vertex) continue;
    const g = cell.geometry;
    const isText = (cell.style || "").startsWith("text;");
    if (isText && st.text && st.text.node) {
      const range = document.createRange();
      range.selectNodeContents(st.text.node);
      const rects = [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0);
      const xs = rects.flatMap((r) => [r.left, r.right]), ys = rects.flatMap((r) => [r.top, r.bottom]);
      const a = toDoc(Math.min(...xs), Math.min(...ys)), b = toDoc(Math.max(...xs), Math.max(...ys));
      out.labels[cell.id] = { geometry: { x: g.x, y: g.y, w: g.width, h: g.height }, box: { x: a.x, y: a.y, w: b.x - a.x, h: b.y - a.y }, lines: rects.length };
    } else {
      out.nodes[cell.id] = { geometry: { x: g.x, y: g.y, w: g.width, h: g.height }, state: { x: st.x / st.view.scale - st.view.translate.x, y: st.y / st.view.scale - st.view.translate.y, w: st.width / st.view.scale, h: st.height / st.view.scale } };
    }
  }
  return out;
}, xml);
console.log(JSON.stringify(result, null, 1));
await browser.close();
```

- [ ] **Step 4: Run it and inspect.**

Run: `node scripts/spikes/drawio_roundtrip.mjs scripts/spikes/fixtures/spike.drawio scripts/spikes/vendor/viewer-static.min.js > $TMPDIR/before.json && cat $TMPDIR/before.json` (sandbox disabled: Chromium).
Expected: `labels` has `l1`, `l2`, `l3`, each `lines: 1`; `nodes.n1.state` equals its geometry within 0.5. If the viewer throws because `GraphViewer` is undefined, record the actual global names exported by the bundle (`Object.keys(window).filter(k => /graph|mx/i.test(k))`) in the spike doc and adapt the constructor call; do not proceed past Step 4 until labels are located by cell ID.

- [ ] **Step 5: Write the structural patch script** `scripts/spikes/drawio_patch.py`:

```python
"""Spike: move one label cell by (dx, dy) by editing its <mxGeometry x/y> structurally, bytes elsewhere unchanged.
Usage: python scripts/spikes/drawio_patch.py IN.drawio OUT.drawio CELL_ID DX DY"""

import sys
import xml.parsers.expat
from fractions import Fraction


def geometry_span(raw: bytes, cell_id: str) -> tuple[int, int, dict[str, str]]:
    """Byte span [start, end) of the <mxGeometry ...> start tag inside the mxCell with this id, plus its attributes."""
    stack: list[str] = []
    found: list[tuple[int, int, dict[str, str]]] = []
    p = xml.parsers.expat.ParserCreate()

    def start(name: str, attrs: dict[str, str]) -> None:
        if name == "mxGeometry" and stack and stack[-1] == cell_id and attrs.get("as") == "geometry":
            s = p.CurrentByteIndex
            e = raw.index(b">", s) + 1
            found.append((s, e, attrs))
        stack.append(attrs.get("id", "") if name == "mxCell" else (stack[-1] if stack else ""))

    p.StartElementHandler = start
    p.EndElementHandler = lambda name: stack.pop()
    p.Parse(raw, True)
    if len(found) != 1:
        raise SystemExit(f"expected one geometry for {cell_id}, found {len(found)}")
    return found[0]


def fmt(v: Fraction) -> str:
    q = round(v * 64) / Fraction(64)  # nearest 1/64; Python round() uses ties-to-even
    return str(int(q)) if q.denominator == 1 else f"{float(q):.6f}".rstrip("0").rstrip(".")


def main() -> None:
    src, dst, cell, dx, dy = sys.argv[1:6]
    raw = open(src, "rb").read()
    s, e, attrs = geometry_span(raw, cell)
    tag = raw[s:e].decode("utf-8")
    for key, delta in (("x", Fraction(dx)), ("y", Fraction(dy))):
        old = Fraction(attrs.get(key, "0"))
        new = fmt(old + delta)
        if key in attrs:
            tag = tag.replace(f' {key}="{attrs[key]}"', f' {key}="{new}"', 1)
        else:
            tag = tag.replace("<mxGeometry", f'<mxGeometry {key}="{new}"', 1)
    out = raw[:s] + tag.encode("utf-8") + raw[e:]
    assert out[:s] == raw[:s] and out[s + len(tag.encode()):] == raw[e:]
    open(dst, "wb").write(out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Patch, re-render, compare measured displacement.**

```bash
python scripts/spikes/drawio_patch.py scripts/spikes/fixtures/spike.drawio $TMPDIR/moved.drawio l2 37.5 -12
node scripts/spikes/drawio_roundtrip.mjs $TMPDIR/moved.drawio scripts/spikes/vendor/viewer-static.min.js > $TMPDIR/after.json
python3 -c "
import json,os;T=os.environ['TMPDIR'];b=json.load(open(T+'/before.json'))['labels'];a=json.load(open(T+'/after.json'))['labels']
for k in b: print(k, round(a[k]['box']['x']-b[k]['box']['x'],3), round(a[k]['box']['y']-b[k]['box']['y'],3), round(a[k]['box']['w']-b[k]['box']['w'],3))"
```
Expected: `l2 37.5 -12.0 0.0` within 0.5; `l1` and `l3` `0.0 0.0 0.0`.

- [ ] **Step 7: Re-open check through the real draw.io.**

Run: `drawio -x -f svg -o $TMPDIR/moved.svg $TMPDIR/moved.drawio && grep -o 'data-cell-id="l2".\{0,300\}' $TMPDIR/moved.svg | head -c 400`
Expected: the export succeeds and the `l2` group's rendered text position reflects the move (its `<text x=...>` or foreignObject `margin-left`/`padding-top` changed by the patched amount relative to the unpatched export of `spike.drawio`). Also run the unpatched export and diff the two SVGs: only the `l2` group may differ.

- [ ] **Step 8: Write the verdict** `docs/spikes/2026-10-16-drawio-roundtrip.md` with: viewer source and hash; per gate criterion (1 cell→label mapping, 2 document-coordinate measurement, 3 measured displacement equals requested, 4 re-open preserves edit) PASS/FAIL with the actual numbers; any global-name or API surprises; the measurement primitive actually used; whether the Xvfb CLI fallback is needed. If any criterion fails, stop and report to the owner before Task 2 onward depend on nothing here — Tasks 2–11 may proceed, but Plan 3 is blocked until the gate passes.

- [ ] **Step 9: Commit**

```bash
git add scripts/spikes/drawio_roundtrip.mjs scripts/spikes/drawio_patch.py scripts/spikes/fixtures/spike.drawio scripts/spikes/vendor/README.md docs/spikes/2026-10-16-drawio-roundtrip.md .gitignore
git commit -m "spike: draw.io render, measure, patch and re-open round trip (gate 2.3 part 1)"
```

---

### Task 1: Real-file corpus authored in draw.io

**Files:**
- Create: `tests/fixtures/drawio_corpus/dev/{d1,d2,d3}.drawio`, `docs/corpus/drawio_provenance.md`
- Create (git-ignored): `benchmarks/final/drawio/{f1,f2,f3}.drawio`

**Interfaces:**
- Produces: three development files used by Plan 3 tests; three frozen final files used only by Plan 5.

Authored by Claude in the real draw.io editor (app.diagrams.net) through browser automation (Claude in Chrome). Downloading the saved files needs the owner's per-session approval in chat; ask before the first download.

- [ ] **Step 1: Plan six diagrams** (write the table into `docs/corpus/drawio_provenance.md` first). Each: 4–10 rectangle nodes, 3–10 separate text label cells (draw.io "Text" shape), at least one "warning" label, page view on, `pageScale` 1. Vary: canvas aspect (landscape/portrait), crowding (some labels whose right-hand spot is blocked or off the page), node sizes, label lengths (short/long single-line), one compressed-on-save file, one two-page file. Assign IDs d1–d3 (development) and f1–f3 (final) by a coin flip recorded in the doc, before drawing anything.

- [ ] **Step 2: Author each diagram in app.diagrams.net.** For each: new blank diagram; set page size in the right panel; draw nodes with the Rectangle shape; add labels with the Text shape (keep "Formatted Text" on, the default); type label text; leave labels below or beside their nodes as a person would; File → Save as → Device, name `<id>.drawio`. Record per file: date, editor (app.diagrams.net, version from Help → About), steps taken, any settings changed (e.g. compression). If browser automation cannot perform an operation (file download dialog, a menu), ask the owner for exactly that step.

- [ ] **Step 3: Move files into place and hash them.**

```bash
mkdir -p tests/fixtures/drawio_corpus/dev benchmarks/final/drawio
mv ~/Downloads/d1.drawio ~/Downloads/d2.drawio ~/Downloads/d3.drawio tests/fixtures/drawio_corpus/dev/
mv ~/Downloads/f1.drawio ~/Downloads/f2.drawio ~/Downloads/f3.drawio benchmarks/final/drawio/
shasum -a 256 tests/fixtures/drawio_corpus/dev/*.drawio benchmarks/final/drawio/*.drawio
git check-ignore benchmarks/final/drawio/f1.drawio
```
Expected: six hashes; `git check-ignore` prints the path (it is ignored). Paste all six hashes into the provenance doc. From this moment the three `f*` files are not opened by any code or by Claude until Plan 5's frozen run.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/drawio_corpus/dev docs/corpus/drawio_provenance.md
git commit -m "data: real-file corpus authored in draw.io (3 development files; 3 frozen final files hashed, not committed)"
```

---

### Task 2: Store with atomic create and generation compare-and-set

**Files:**
- Create: `src/open_apprentice/storage/store.py`
- Test: `tests/unit/teaching/test_store.py` (create `tests/unit/teaching/__init__.py` empty)

**Interfaces:**
- Produces:
  - `class PreconditionFailed(Exception)`
  - `@dataclass(frozen=True) class Blob: data: bytes; generation: int`
  - `class Store(Protocol)`: `get(key: str) -> Blob | None`; `create(key: str, data: bytes) -> bool` (False if it exists); `put(key: str, data: bytes, if_generation: int | None) -> int` (None means "must not exist"; returns the new generation; raises `PreconditionFailed`)
  - `class LocalStore(Store)`: `__init__(self, root: pathlib.Path)`

- [ ] **Step 1: Write the failing tests**

```python
import threading

import pytest

from open_apprentice.storage.store import LocalStore, PreconditionFailed


def test_create_is_atomic_and_never_overwrites(tmp_path):
    s = LocalStore(tmp_path)
    assert s.create("a/b.json", b"1") is True
    assert s.create("a/b.json", b"2") is False
    assert s.get("a/b.json").data == b"1"


def test_put_requires_matching_generation(tmp_path):
    s = LocalStore(tmp_path)
    g1 = s.put("m.json", b"v1", if_generation=None)
    with pytest.raises(PreconditionFailed):
        s.put("m.json", b"x", if_generation=None)
    g2 = s.put("m.json", b"v2", if_generation=g1)
    assert g2 > g1 and s.get("m.json").data == b"v2"
    with pytest.raises(PreconditionFailed):
        s.put("m.json", b"stale", if_generation=g1)


def test_concurrent_cas_exactly_one_winner(tmp_path):
    s = LocalStore(tmp_path)
    g = s.put("m.json", b"0", if_generation=None)
    wins: list[int] = []

    def worker(i: int) -> None:
        try:
            s.put("m.json", str(i).encode(), if_generation=g)
            wins.append(i)
        except PreconditionFailed:
            pass

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(wins) == 1


def test_missing_key_is_none(tmp_path):
    assert LocalStore(tmp_path).get("nope") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'open_apprentice.storage.store'`

- [ ] **Step 3: Implement**

```python
"""Object store with the two primitives the event log needs: atomic create of immutable objects and compare-and-set
on a generation number (the GCS `ifGenerationMatch` semantics). `LocalStore` is the development backend; the GCS backend
(Plan 2) implements the same protocol."""

from __future__ import annotations

import fcntl
import os
import pathlib
from dataclasses import dataclass
from typing import Optional, Protocol


class PreconditionFailed(Exception):
    """The object's current generation did not match the caller's expectation."""


@dataclass(frozen=True)
class Blob:
    data: bytes
    generation: int


class Store(Protocol):
    def get(self, key: str) -> Optional[Blob]: ...

    def create(self, key: str, data: bytes) -> bool: ...

    def put(self, key: str, data: bytes, if_generation: Optional[int]) -> int: ...


class LocalStore:
    """Files under `root`. A generation lives in `<file>.gen`; a per-key lock file serialises compare-and-set."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> pathlib.Path:
        if key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"bad key {key!r}")
        return self.root / key

    def get(self, key: str) -> Optional[Blob]:
        p = self._path(key)
        if not p.exists():
            return None
        gen_file = p.with_name(p.name + ".gen")
        gen = int(gen_file.read_text()) if gen_file.exists() else 1
        return Blob(p.read_bytes(), gen)

    def create(self, key: str, data: bytes) -> bool:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            return False
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        return True

    def put(self, key: str, data: bytes, if_generation: Optional[int]) -> int:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        lock = p.with_name(p.name + ".lock")
        with open(lock, "a+") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            current = self.get(key)
            if (current is None) != (if_generation is None) or (
                current is not None and current.generation != if_generation
            ):
                raise PreconditionFailed(f"{key}: expected {if_generation}, found {current and current.generation}")
            new_gen = 1 if current is None else current.generation + 1
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, p)
            p.with_name(p.name + ".gen").write_text(str(new_gen))
            return new_gen
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_store.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/storage/store.py tests/unit/teaching/__init__.py tests/unit/teaching/test_store.py
git commit -m "feat(storage): LocalStore with atomic create and generation compare-and-set"
```

---

### Task 3: Codec and the session event log

**Files:**
- Create: `src/open_apprentice/teaching/__init__.py` (empty), `src/open_apprentice/teaching/codec.py`, `src/open_apprentice/teaching/events.py`
- Test: `tests/unit/teaching/test_events.py`

**Interfaces:**
- Consumes: `Store`, `LocalStore`, `PreconditionFailed` (Task 2).
- Produces:
  - `codec.dumps(obj) -> bytes` (canonical JSON, sorted keys, Fractions as `"n/d"` or int), `codec.loads(b: bytes) -> Any`, `codec.digest(obj) -> str` (sha256 hex of `dumps`), `codec.frac(v) -> Fraction` (parse int or `"n/d"`)
  - `@dataclass(frozen=True) class Event: event_id: str; prev_event_id: str | None; seq: int; type: str; origin: str; payload: dict; caused_by: str | None = None`
  - `INTENT_TYPES: frozenset[str]` (types that raise `intent_revision`)
  - `class Conflict(Exception)` (manifest moved since read)
  - `class SessionLog`: `__init__(self, store: Store, sid: str)`; `create(self, owner: str) -> dict`; `manifest(self) -> tuple[dict, int]`; `append(self, type: str, origin: str, payload: dict, caused_by: str | None = None, expected_revision: int | None = None) -> Event`; `events(self) -> list[Event]`

Origins: `"human" | "simulator" | "model" | "system" | "measurement"`.

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction

import pytest

from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching import codec
from open_apprentice.teaching.events import Conflict, SessionLog


def test_codec_round_trips_fractions_canonically():
    obj = {"b": Fraction(3, 2), "a": [Fraction(4), 1]}
    assert codec.dumps(obj) == b'{"a":[4,1],"b":"3/2"}'
    assert codec.frac(codec.loads(codec.dumps(obj))["b"]) == Fraction(3, 2)
    assert codec.digest(obj) == codec.digest({"a": [4, 1], "b": "3/2"})


def test_append_and_replay_in_order(tmp_path):
    log = SessionLog(LocalStore(tmp_path), "s1")
    log.create(owner="o1")
    log.append("SceneRegistered", "system", {"scene_id": "a"})
    log.append("DemonstrationRecorded", "human", {"scene_id": "a"})
    evs = log.events()
    assert [e.type for e in evs] == ["SceneRegistered", "DemonstrationRecorded"]
    assert [e.seq for e in evs] == [1, 2] and evs[1].prev_event_id == evs[0].event_id
    m, _ = log.manifest()
    assert m["intent_revision"] == 2 and m["manifest_revision"] == 2  # both are intent-bearing types


def test_stale_expected_revision_conflicts(tmp_path):
    log = SessionLog(LocalStore(tmp_path), "s1")
    log.create(owner="o1")
    log.append("SceneRegistered", "system", {"scene_id": "a"})
    with pytest.raises(Conflict):
        log.append("SceneRegistered", "system", {"scene_id": "b"}, expected_revision=0)


def test_orphan_event_is_invisible_and_append_continues(tmp_path):
    store = LocalStore(tmp_path)
    log = SessionLog(store, "s1")
    log.create(owner="o1")
    log.append("SceneRegistered", "system", {"scene_id": "a"})
    # simulate a crash: an event object written but the manifest never updated
    store.create("sessions/s1/events/orphan.json", codec.dumps({"event_id": "orphan", "prev_event_id": None, "seq": 2,
                                                                 "type": "X", "origin": "system", "payload": {}, "caused_by": None}))
    assert [e.type for e in log.events()] == ["SceneRegistered"]
    log.append("DemonstrationRecorded", "human", {"scene_id": "a"})
    assert [e.type for e in log.events()] == ["SceneRegistered", "DemonstrationRecorded"]


def test_concurrent_writers_cannot_expose_conflicting_histories(tmp_path):
    store = LocalStore(tmp_path)
    SessionLog(store, "s1").create(owner="o1")
    a, b = SessionLog(store, "s1"), SessionLog(store, "s1")
    _, rev = a.manifest()
    a.append("SceneRegistered", "system", {"scene_id": "a"}, expected_revision=rev)
    with pytest.raises(Conflict):
        b.append("SceneRegistered", "system", {"scene_id": "b"}, expected_revision=rev)
    assert [e.payload["scene_id"] for e in a.events()] == ["a"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'open_apprentice.teaching'`

- [ ] **Step 3: Implement `codec.py`**

```python
"""Canonical JSON for event payloads: sorted keys, no spaces, exact Fractions as "n/d" (int when whole)."""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from typing import Any


def _enc(o: Any) -> Any:
    if isinstance(o, Fraction):
        return int(o) if o.denominator == 1 else f"{o.numerator}/{o.denominator}"
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(f"not serialisable: {type(o).__name__}")


def _norm(o: Any) -> Any:
    if isinstance(o, Fraction):
        return _enc(o)
    if isinstance(o, dict):
        return {str(k): _norm(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_norm(v) for v in o]
    return o


def dumps(obj: Any) -> bytes:
    return json.dumps(_norm(obj), sort_keys=True, separators=(",", ":"), default=_enc).encode("utf-8")


def loads(b: bytes) -> Any:
    return json.loads(b.decode("utf-8"))


def digest(obj: Any) -> str:
    return hashlib.sha256(dumps(obj)).hexdigest()


def frac(v: Any) -> Fraction:
    if isinstance(v, Fraction):
        return v
    if isinstance(v, int):
        return Fraction(v)
    if isinstance(v, str):
        return Fraction(v)
    raise TypeError(f"not a rational: {v!r}")
```

- [ ] **Step 4: Implement `events.py`**

```python
"""Append-only session event log. An event is an immutable object written first; it becomes part of history only when
the session manifest's head pointer is moved to it by compare-and-set. Replay walks head -> prev, never lists objects."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Optional

from open_apprentice.storage.store import PreconditionFailed, Store
from open_apprentice.teaching import codec

INTENT_TYPES = frozenset(
    {
        "SceneRegistered",
        "MappingRecorded",
        "DemonstrationRecorded",
        "ResponseRecorded",
        "ScopeAuthorized",
        "VersionActivated",
    }
)


class Conflict(Exception):
    """The manifest moved since the caller read it; re-read events, re-step, retry."""


@dataclass(frozen=True)
class Event:
    event_id: str
    prev_event_id: Optional[str]
    seq: int
    type: str
    origin: str
    payload: dict
    caused_by: Optional[str] = None


class SessionLog:
    def __init__(self, store: Store, sid: str) -> None:
        self.store, self.sid = store, sid
        self._mkey = f"sessions/{sid}/manifest.json"

    def create(self, owner: str) -> dict:
        m = {"sid": self.sid, "owner": owner, "manifest_revision": 0, "intent_revision": 0,
             "head_event_id": None, "head_seq": 0, "status": "open"}
        self.store.put(self._mkey, codec.dumps(m), if_generation=None)
        return m

    def manifest(self) -> tuple[dict, int]:
        b = self.store.get(self._mkey)
        if b is None:
            raise KeyError(f"no session {self.sid}")
        return codec.loads(b.data), b.generation

    def append(self, type: str, origin: str, payload: dict, caused_by: Optional[str] = None,
               expected_revision: Optional[int] = None) -> Event:
        b = self.store.get(self._mkey)
        if b is None:
            raise KeyError(f"no session {self.sid}")
        m = codec.loads(b.data)
        if expected_revision is not None and m["manifest_revision"] != expected_revision:
            raise Conflict(f"manifest at {m['manifest_revision']}, caller expected {expected_revision}")
        ev = Event(uuid.uuid4().hex, m["head_event_id"], m["head_seq"] + 1, type, origin, payload, caused_by)
        if not self.store.create(f"sessions/{self.sid}/events/{ev.event_id}.json", codec.dumps(asdict(ev))):
            raise RuntimeError("event id collision")
        m2 = dict(m, head_event_id=ev.event_id, head_seq=ev.seq, manifest_revision=m["manifest_revision"] + 1,
                  intent_revision=m["intent_revision"] + (1 if type in INTENT_TYPES else 0))
        try:
            self.store.put(self._mkey, codec.dumps(m2), if_generation=b.generation)
        except PreconditionFailed as e:
            raise Conflict(str(e)) from e  # the written event stays unreachable
        return ev

    def events(self) -> list[Event]:
        m, _ = self.manifest()
        out: list[Event] = []
        eid = m["head_event_id"]
        while eid is not None:
            b = self.store.get(f"sessions/{self.sid}/events/{eid}.json")
            if b is None:
                raise RuntimeError(f"committed event {eid} missing")
            d = codec.loads(b.data)
            out.append(Event(**d))
            eid = d["prev_event_id"]
        return list(reversed(out))
```

- [ ] **Step 5: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_events.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/open_apprentice/teaching/__init__.py src/open_apprentice/teaching/codec.py src/open_apprentice/teaching/events.py tests/unit/teaching/test_events.py
git commit -m "feat(teaching): canonical codec and compare-and-set event log with chain replay"
```

---

### Task 4: Teacher protocol types and validation

**Files:**
- Create: `src/open_apprentice/teaching/teacher.py`
- Test: `tests/unit/teaching/test_teacher.py`

**Interfaces:**
- Consumes: `codec` (Task 3).
- Produces:
  - `Output = dict[str, tuple[Fraction, Fraction]]` (label id → top-left)
  - `TOL = Fraction(1, 2)`, `SEPARATION = Fraction(1)`
  - `class ProtocolError(Exception)`
  - `@dataclass(frozen=True) class ChooseOutput: request_id: str; scene_id: str; scene_hash: str; alternatives: tuple[tuple[str, Output], ...]`
  - `@dataclass(frozen=True) class ConfirmPreview: request_id: str; purpose: str; items: tuple[tuple[str, str, str, Output], ...]` (item_id, scene_id, scene_hash, output); purposes `{"learning_preview": 3, "affected_examples": 6, "revision_preview": 3}` max items
  - `@dataclass(frozen=True) class RequestDemonstration: request_id: str; scene_id: str; scene_hash: str`
  - `@dataclass(frozen=True) class Response: request_id: str; kind: str; selected: str | None = None; per_item: tuple[tuple[str, str], ...] = (); output: Output | None = None; source: str = "human"`
    - kinds: `choose|none|unsure|cancel` (ChooseOutput), `items` (ConfirmPreview; per_item values `approve|reject|unsure`), `demonstrate|decline` (RequestDemonstration)
  - `max_error(a: Output, b: Output) -> Fraction | None` (None if label sets differ)
  - `validate_request(req, registered: dict[str, str]) -> None` (registered: scene_id → scene_hash)
  - `validate_response(req, resp) -> None`
  - `class Teacher(Protocol): def ask(self, req) -> Response`
  - `request_to_json(req) -> dict`, `response_from_json(d: dict) -> Response`, `request_from_json(d: dict)`, `response_to_json(r: Response) -> dict`

(`ConfirmCorrectionScope` is added in Plan 2.)

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction as F

import pytest

from open_apprentice.teaching.teacher import (
    ChooseOutput, ConfirmPreview, ProtocolError, RequestDemonstration, Response,
    max_error, request_from_json, request_to_json, validate_request, validate_response,
)

REG = {"s1": "h1"}


def test_max_error():
    assert max_error({"l": (F(0), F(0))}, {"l": (F(1, 4), F(-1, 2))}) == F(1, 2)
    assert max_error({"l": (F(0), F(0))}, {"m": (F(0), F(0))}) is None


def test_choose_requires_2_to_4_separated_alternatives():
    a = ("A", {"l": (F(0), F(0))})
    b = ("B", {"l": (F(3, 4), F(0))})  # only 0.75 apart: both could match a truth at 0.375
    with pytest.raises(ProtocolError):
        validate_request(ChooseOutput("q1", "s1", "h1", (a, b)), REG)
    c = ("C", {"l": (F(2), F(0))})
    validate_request(ChooseOutput("q1", "s1", "h1", (a, c)), REG)
    with pytest.raises(ProtocolError):
        validate_request(ChooseOutput("q1", "s1", "h1", (a,)), REG)


def test_unregistered_or_mismatched_scene_is_protocol_error():
    a, c = ("A", {"l": (F(0), F(0))}), ("C", {"l": (F(2), F(0))})
    with pytest.raises(ProtocolError):
        validate_request(ChooseOutput("q1", "s9", "h1", (a, c)), REG)
    with pytest.raises(ProtocolError):
        validate_request(RequestDemonstration("q2", "s1", "WRONG"), REG)


def test_preview_item_limits_and_per_item_response():
    out = {"l": (F(0), F(0))}
    items = tuple((f"i{k}", "s1", "h1", out) for k in range(4))
    with pytest.raises(ProtocolError):
        validate_request(ConfirmPreview("p1", "learning_preview", items), REG)
    req = ConfirmPreview("p1", "learning_preview", items[:2])
    validate_request(req, REG)
    validate_response(req, Response("p1", "items", per_item=(("i0", "approve"), ("i1", "unsure"))))
    with pytest.raises(ProtocolError):
        validate_response(req, Response("p1", "items", per_item=(("i0", "approve"),)))


def test_choose_response_must_name_a_shown_alternative():
    a, c = ("A", {"l": (F(0), F(0))}), ("C", {"l": (F(2), F(0))})
    req = ChooseOutput("q1", "s1", "h1", (a, c))
    validate_response(req, Response("q1", "choose", selected="C"))
    validate_response(req, Response("q1", "none"))
    with pytest.raises(ProtocolError):
        validate_response(req, Response("q1", "choose", selected="Z"))


def test_json_round_trip():
    req = ChooseOutput("q1", "s1", "h1", (("A", {"l": (F(1, 3), F(0))}), ("C", {"l": (F(2), F(0))})))
    assert request_from_json(request_to_json(req)) == req
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_teacher.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `teacher.py`**

```python
"""The only route by which intent information reaches a learner. Four request types (ConfirmCorrectionScope arrives in
Plan 2). Validation runs before the teacher sees a request; a malformed request is a protocol error, never an abstention."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional, Protocol, Union

from open_apprentice.teaching import codec

Output = dict[str, tuple[Fraction, Fraction]]
TOL = Fraction(1, 2)
SEPARATION = Fraction(1)
PREVIEW_PURPOSES = {"learning_preview": 3, "affected_examples": 6, "revision_preview": 3}


class ProtocolError(Exception):
    pass


@dataclass(frozen=True)
class ChooseOutput:
    request_id: str
    scene_id: str
    scene_hash: str
    alternatives: tuple[tuple[str, Output], ...]


@dataclass(frozen=True)
class ConfirmPreview:
    request_id: str
    purpose: str
    items: tuple[tuple[str, str, str, Output], ...]


@dataclass(frozen=True)
class RequestDemonstration:
    request_id: str
    scene_id: str
    scene_hash: str


Request = Union[ChooseOutput, ConfirmPreview, RequestDemonstration]


@dataclass(frozen=True)
class Response:
    request_id: str
    kind: str
    selected: Optional[str] = None
    per_item: tuple[tuple[str, str], ...] = ()
    output: Optional[Output] = None
    source: str = "human"


class Teacher(Protocol):
    def ask(self, req: Request) -> Response: ...


def max_error(a: Output, b: Output) -> Optional[Fraction]:
    if set(a) != set(b):
        return None
    return max((max(abs(a[k][0] - b[k][0]), abs(a[k][1] - b[k][1])) for k in a), default=Fraction(0))


def _scene_ok(scene_id: str, scene_hash: str, registered: dict[str, str]) -> None:
    if registered.get(scene_id) != scene_hash:
        raise ProtocolError(f"scene {scene_id} not registered in this session or its content does not match")


def validate_request(req: Request, registered: dict[str, str]) -> None:
    if isinstance(req, ChooseOutput):
        _scene_ok(req.scene_id, req.scene_hash, registered)
        if not 2 <= len(req.alternatives) <= 4:
            raise ProtocolError("ChooseOutput needs 2-4 alternatives")
        if len({a for a, _ in req.alternatives}) != len(req.alternatives):
            raise ProtocolError("duplicate alternative ids")
        outs = [o for _, o in req.alternatives]
        for i in range(len(outs)):
            for j in range(i + 1, len(outs)):
                e = max_error(outs[i], outs[j])
                if e is None:
                    raise ProtocolError("alternatives cover different labels")
                if e <= SEPARATION:
                    raise ProtocolError("alternatives are not separated by more than twice the tolerance")
    elif isinstance(req, ConfirmPreview):
        if req.purpose not in PREVIEW_PURPOSES:
            raise ProtocolError(f"unknown preview purpose {req.purpose}")
        if not 1 <= len(req.items) <= PREVIEW_PURPOSES[req.purpose]:
            raise ProtocolError(f"{req.purpose} takes 1-{PREVIEW_PURPOSES[req.purpose]} items")
        if len({i for i, *_ in req.items}) != len(req.items):
            raise ProtocolError("duplicate preview item ids")
        for _, sid, sh, _ in req.items:
            _scene_ok(sid, sh, registered)
    elif isinstance(req, RequestDemonstration):
        _scene_ok(req.scene_id, req.scene_hash, registered)
    else:
        raise ProtocolError(f"unknown request type {type(req).__name__}")


def validate_response(req: Request, resp: Response) -> None:
    if resp.request_id != req.request_id:
        raise ProtocolError("response is for a different request")
    if isinstance(req, ChooseOutput):
        if resp.kind not in ("choose", "none", "unsure", "cancel"):
            raise ProtocolError(f"bad ChooseOutput response {resp.kind}")
        if resp.kind == "choose" and resp.selected not in {a for a, _ in req.alternatives}:
            raise ProtocolError("choice names an alternative that was not shown")
    elif isinstance(req, ConfirmPreview):
        if resp.kind != "items" or {i for i, _ in resp.per_item} != {i for i, *_ in req.items}:
            raise ProtocolError("preview needs exactly one verdict per item")
        if any(v not in ("approve", "reject", "unsure") for _, v in resp.per_item):
            raise ProtocolError("preview verdicts are approve/reject/unsure")
    elif isinstance(req, RequestDemonstration):
        if resp.kind not in ("demonstrate", "decline") or (resp.kind == "demonstrate" and not resp.output):
            raise ProtocolError("demonstration response needs an output or a decline")


def _out_json(o: Output) -> dict:
    return {k: [codec._enc(x) if isinstance(x, Fraction) else x, codec._enc(y) if isinstance(y, Fraction) else y]
            for k, (x, y) in o.items()}


def _out_parse(d: dict) -> Output:
    return {k: (codec.frac(v[0]), codec.frac(v[1])) for k, v in d.items()}


def request_to_json(req: Request) -> dict:
    if isinstance(req, ChooseOutput):
        return {"type": "ChooseOutput", "request_id": req.request_id, "scene_id": req.scene_id,
                "scene_hash": req.scene_hash, "alternatives": [[a, _out_json(o)] for a, o in req.alternatives]}
    if isinstance(req, ConfirmPreview):
        return {"type": "ConfirmPreview", "request_id": req.request_id, "purpose": req.purpose,
                "items": [[i, s, h, _out_json(o)] for i, s, h, o in req.items]}
    return {"type": "RequestDemonstration", "request_id": req.request_id, "scene_id": req.scene_id,
            "scene_hash": req.scene_hash}


def request_from_json(d: dict) -> Request:
    if d["type"] == "ChooseOutput":
        return ChooseOutput(d["request_id"], d["scene_id"], d["scene_hash"],
                            tuple((a, _out_parse(o)) for a, o in d["alternatives"]))
    if d["type"] == "ConfirmPreview":
        return ConfirmPreview(d["request_id"], d["purpose"],
                              tuple((i, s, h, _out_parse(o)) for i, s, h, o in d["items"]))
    if d["type"] == "RequestDemonstration":
        return RequestDemonstration(d["request_id"], d["scene_id"], d["scene_hash"])
    raise ProtocolError(f"unknown request type {d['type']}")


def response_to_json(r: Response) -> dict:
    return {"request_id": r.request_id, "kind": r.kind, "selected": r.selected,
            "per_item": [list(p) for p in r.per_item],
            "output": _out_json(r.output) if r.output else None, "source": r.source}


def response_from_json(d: dict) -> Response:
    return Response(d["request_id"], d["kind"], d.get("selected"), tuple(tuple(p) for p in d.get("per_item", [])),
                    _out_parse(d["output"]) if d.get("output") else None, d.get("source", "human"))


class SubprocessTeacher:
    """Talks to a teacher process over JSON lines (one request per line, one response per line)."""

    def __init__(self, argv: list[str]) -> None:
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def ask(self, req: Request) -> Response:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(request_to_json(req)) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise ProtocolError("teacher process closed")
        d = json.loads(line)
        if "protocol_error" in d:
            raise ProtocolError(d["protocol_error"])
        return response_from_json(d)

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=10)
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_teacher.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/teaching/teacher.py tests/unit/teaching/test_teacher.py
git commit -m "feat(teaching): typed teacher protocol with separation and per-item preview validation"
```

---

### Task 5: Constraint derivation from committed events

**Files:**
- Create: `src/open_apprentice/teaching/constraints.py`
- Test: `tests/unit/teaching/test_constraints.py`

**Interfaces:**
- Consumes: `Event` (Task 3); `request_from_json`, `response_from_json`, `Output` (Task 4); `hypotheses.Constraint` (existing: `Constraint(kind, scene, expected=None, excluded=(), source="")`); `label_teaching.to_state` (existing: scene → `{id: {x,y,w,h}}`).
- Produces:
  - `scene_from_payload(d: dict) -> dict` (decodes a registered scene, Fractions restored)
  - `apply_output(scene: dict, out: Output) -> dict` (scene with labels moved)
  - `@dataclass class Evidence: scenes: dict[str, dict]; scene_hashes: dict[str, str]; positives: list[Constraint]; negatives: list[Constraint]; approved: dict[str, Output]; rejected: dict[str, list[Output]]; batch: list[str]`
  - `derive(events: list[Event]) -> Evidence`

Event payloads used (exact keys):
- `SceneRegistered{scene_id, scene_hash, scene, role: "demo"|"batch"|"probe"}`
- `DemonstrationRecorded{scene_id, output}` (initial demonstration = full approval of that document)
- `RequestIssued{request}` (JSON from `request_to_json`), `ResponseRecorded{response}` (JSON from `response_to_json`)

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction as F

from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import derive
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.teacher import ChooseOutput, ConfirmPreview, Response, request_to_json, response_to_json

SCENE = {"objects": [
    {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
    {"id": "l0", "kind": "label", "role": "note", "attached": "n0", "x": 0, "y": 60, "w": 40, "h": 20}],
    "canvas": {"w": 600, "h": 400}}


def ev(i, t, payload):
    return Event(f"e{i}", f"e{i-1}" if i > 1 else None, i, t, "system", payload)


def reg(i, sid, role):
    return ev(i, "SceneRegistered", {"scene_id": sid, "scene_hash": codec.digest(SCENE), "scene": codec.loads(codec.dumps(SCENE)), "role": role})


def out(x, y):
    return {"l0": (F(x), F(y))}


def test_demonstration_is_full_positive():
    evs = [reg(1, "d", "demo"), ev(2, "DemonstrationRecorded", {"scene_id": "d", "output": {"l0": [112, 15]}})]
    e = derive(evs)
    assert len(e.positives) == 1 and e.positives[0].expected["l0"]["x"] == 112 and e.positives[0].expected["n0"]["x"] == 0


def test_choose_adds_positive_none_excludes_all_shown_unsure_adds_nothing():
    h = codec.digest(SCENE)
    q = ChooseOutput("q1", "b", h, (("A", out(112, 15)), ("B", out(30, 62))))
    base = [reg(1, "b", "batch"), ev(2, "RequestIssued", {"request": request_to_json(q)})]
    chose = derive(base + [ev(3, "ResponseRecorded", {"response": response_to_json(Response("q1", "choose", selected="A"))})])
    assert len(chose.positives) == 1 and not chose.negatives
    none = derive(base + [ev(3, "ResponseRecorded", {"response": response_to_json(Response("q1", "none"))})])
    assert not none.positives and len(none.negatives) == 1 and len(none.negatives[0].excluded) == 2
    unsure = derive(base + [ev(3, "ResponseRecorded", {"response": response_to_json(Response("q1", "unsure"))})])
    assert not unsure.positives and not unsure.negatives


def test_preview_rejection_excludes_only_that_item():
    h = codec.digest(SCENE)
    p = ConfirmPreview("p1", "learning_preview", (("i1", "b", h, out(112, 15)), ("i2", "c", h, out(112, 15))))
    evs = [reg(1, "b", "batch"), reg(2, "c", "batch"), ev(3, "RequestIssued", {"request": request_to_json(p)}),
           ev(4, "ResponseRecorded", {"response": response_to_json(Response("p1", "items", per_item=(("i1", "approve"), ("i2", "reject"))))})]
    e = derive(evs)
    assert set(e.approved) == {"b"} and set(e.rejected) == {"c"} and len(e.positives) == 1 and len(e.negatives) == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_constraints.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `constraints.py`**

```python
"""Intent constraints are DERIVED from committed human/simulator events; they are never stored separately. Mechanical
feedback never creates intent constraints. Semantics: spec section 3.5."""

from __future__ import annotations

from dataclasses import dataclass, field

from open_apprentice.concepts.hypotheses import Constraint
from open_apprentice.concepts.label_teaching import to_state
from open_apprentice.teaching import codec
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.teacher import (
    ChooseOutput, ConfirmPreview, Output, RequestDemonstration, request_from_json, response_from_json,
)


def scene_from_payload(d: dict) -> dict:
    objs = [{**o, **{f: codec.frac(o[f]) for f in ("x", "y", "w", "h")}} for o in d["objects"]]
    return {"objects": objs, "canvas": {k: codec.frac(v) for k, v in d["canvas"].items()}}


def apply_output(scene: dict, out: Output) -> dict:
    objs = [dict(o, x=out[o["id"]][0], y=out[o["id"]][1]) if o["id"] in out else dict(o) for o in scene["objects"]]
    return {"objects": objs, "canvas": scene["canvas"]}


def _parse_out(d: dict) -> Output:
    return {k: (codec.frac(v[0]), codec.frac(v[1])) for k, v in d.items()}


@dataclass
class Evidence:
    scenes: dict[str, dict] = field(default_factory=dict)
    scene_hashes: dict[str, str] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    positives: list[Constraint] = field(default_factory=list)
    negatives: list[Constraint] = field(default_factory=list)
    approved: dict[str, Output] = field(default_factory=dict)
    rejected: dict[str, list[Output]] = field(default_factory=dict)

    @property
    def batch(self) -> list[str]:
        return [s for s, r in self.roles.items() if r == "batch"]


def derive(events: list[Event]) -> Evidence:
    e = Evidence()
    requests: dict[str, object] = {}
    for ev in events:
        p = ev.payload
        if ev.type == "SceneRegistered":
            e.scenes[p["scene_id"]] = scene_from_payload(p["scene"])
            e.scene_hashes[p["scene_id"]] = p["scene_hash"]
            e.roles[p["scene_id"]] = p["role"]
        elif ev.type == "DemonstrationRecorded":
            sc = e.scenes[p["scene_id"]]
            out = _parse_out(p["output"])
            e.positives.append(Constraint("positive", sc, to_state(apply_output(sc, out)), source="demonstration"))
            e.approved[p["scene_id"]] = out
        elif ev.type == "RequestIssued":
            req = request_from_json(p["request"])
            requests[req.request_id] = req
        elif ev.type == "ResponseRecorded":
            r = response_from_json(p["response"])
            req = requests.get(r.request_id)
            if isinstance(req, ChooseOutput):
                sc = e.scenes[req.scene_id]
                if r.kind == "choose":
                    out = dict(req.alternatives)[r.selected]
                    e.positives.append(Constraint("positive", sc, to_state(apply_output(sc, out)), source="answer"))
                    e.approved[req.scene_id] = out
                elif r.kind == "none":
                    excl = tuple(to_state(apply_output(sc, o)) for _, o in req.alternatives)
                    e.negatives.append(Constraint("excludes", sc, excluded=excl, source="neither"))
                    e.rejected.setdefault(req.scene_id, []).extend(o for _, o in req.alternatives)
            elif isinstance(req, ConfirmPreview):
                verdicts = dict(r.per_item)
                for item_id, sid, _, out in req.items:
                    sc = e.scenes[sid]
                    if verdicts[item_id] == "approve":
                        e.positives.append(Constraint("positive", sc, to_state(apply_output(sc, out)), source="preview"))
                        e.approved[sid] = out
                    elif verdicts[item_id] == "reject":
                        e.negatives.append(Constraint("excludes", sc, excluded=(to_state(apply_output(sc, out)),), source="preview_reject"))
                        e.rejected.setdefault(sid, []).append(out)
            elif isinstance(req, RequestDemonstration) and r.kind == "demonstrate" and r.output:
                sc = e.scenes[req.scene_id]
                e.positives.append(Constraint("positive", sc, to_state(apply_output(sc, r.output)), source="requested_demonstration"))
                e.approved[req.scene_id] = r.output
    return e
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_constraints.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/teaching/constraints.py tests/unit/teaching/test_constraints.py
git commit -m "feat(teaching): derive intent constraints from committed teacher events (per-item preview, none excludes shown)"
```

---

### Task 6: Pure step policy

**Files:**
- Create: `src/open_apprentice/teaching/step.py`
- Test: `tests/unit/teaching/test_step.py`

**Interfaces:**
- Consumes: `Event` (Task 3), `derive`, `Evidence`, `apply_output` (Task 5), `ChooseOutput`, `ConfirmPreview`, `SEPARATION`, `max_error`, `request_to_json` (Task 4), `codec` (Task 3), existing `concepts.rules.evaluate_rule`, `RuleError`, `concepts.hypotheses.fits`, `concepts.label_teaching.magic_condition`.
- Produces:
  - `@dataclass(frozen=True) class StepConfig: max_choose: int = 3; max_previews: int = 1; max_preview_items: int = 3; max_attempts: int = 8; max_evaluations: int = 5_000_000`
  - Actions (frozen dataclasses, each with `action_id: str`): `WaitForResult(action_id)`, `RequestModelProposal(action_id, round_kind: str, feedback: tuple[str, ...])` with `round_kind ∈ {"initial","contrastive","revision"}`, `AskTeacher(action_id, request)`, `PresentPreview(action_id, request, program_hash)`, `CommitVersion(action_id, program_hash, rule, summary, claim)`, `Abstain(action_id, reason)`, `Error(action_id, reason)`
  - `step(events: list[Event], config: StepConfig) -> Action`
  - `candidate_pool(events) -> list[dict]` (each `{hash, rule, summary, text}` deduplicated by canonical AST hash)
  - `run_output(rule: list, scene: dict) -> Output | None` (label positions only; None on `RuleError`)

Result events the step reads (written by the executor, Task 8): `ActionIssued{action_id, kind}`, `ModelProposalReturned{action_id, candidates:[{rule, summary, text}], usage}`, `ModelCallFailed{action_id, reason, terminal: bool}`, `RequestIssued{request, action_id}`, `ResponseRecorded{response}`, `VersionStored{action_id, program_hash}`, `Abstained{action_id, reason}`, `Errored{action_id, reason}`.

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.teaching import codec
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.step import (
    Abstain, AskTeacher, CommitVersion, PresentPreview, RequestModelProposal, StepConfig, WaitForResult, run_output, step,
)
from open_apprentice.teaching.teacher import Response, response_to_json

# A scene where "right" and "right else below" differ: n1 sits where l0's right-hand spot would be.
BLOCKED = {"objects": [
    {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
    {"id": "n1", "kind": "node", "role": "", "attached": "", "x": 120, "y": 0, "w": 60, "h": 50},
    {"id": "l0", "kind": "label", "role": "note", "attached": "n0", "x": 0, "y": 60, "w": 40, "h": 20}],
    "canvas": {"w": 600, "h": 400}}
CLEAR = {"objects": [o for o in BLOCKED["objects"] if o["id"] != "n1"], "canvas": BLOCKED["canvas"]}
RIGHT = rule_for_spec(Spec("right", None, "all", F(12)))
FALLBACK = rule_for_spec(Spec("right", "below", "all", F(12)))
CFG = StepConfig()


class Log:
    def __init__(self):
        self.evs: list[Event] = []

    def add(self, t, payload, origin="system"):
        n = len(self.evs) + 1
        self.evs.append(Event(f"e{n}", f"e{n-1}" if n > 1 else None, n, t, origin, payload))


def registered(log, sid, scene, role):
    log.add("SceneRegistered", {"scene_id": sid, "scene_hash": codec.digest(scene),
                                "scene": codec.loads(codec.dumps(scene)), "role": role})


def demo(log):
    registered(log, "d", CLEAR, "demo")
    out = run_output(RIGHT, CLEAR)
    log.add("DemonstrationRecorded", {"scene_id": "d", "output": codec.loads(codec.dumps(out))}, "human")


def proposals(log, rules, kind="initial"):
    a = step(log.evs, CFG)
    assert isinstance(a, RequestModelProposal) and a.round_kind == kind
    log.add("ActionIssued", {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": a.round_kind})
    log.add("ModelProposalReturned", {"action_id": a.action_id, "usage": {},
                                      "candidates": [{"rule": r, "summary": s, "text": ""} for r, s in rules]}, "model")


def test_first_action_is_initial_proposal_and_waits_while_outstanding():
    log = Log()
    demo(log)
    a = step(log.evs, CFG)
    assert isinstance(a, RequestModelProposal) and a.round_kind == "initial"
    log.add("ActionIssued", {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": a.round_kind})
    assert isinstance(step(log.evs, CFG), WaitForResult)


def test_disagreement_on_batch_asks_choose_output():
    log = Log()
    demo(log)
    registered(log, "b1", BLOCKED, "batch")
    proposals(log, [(RIGHT, "right"), (FALLBACK, "fallback")])
    a = step(log.evs, CFG)
    assert isinstance(a, AskTeacher) and a.request.scene_id == "b1" and len(a.request.alternatives) == 2


def test_indistinguishable_candidates_go_to_preview_and_both_survive():
    log = Log()
    demo(log)
    registered(log, "b1", CLEAR, "batch")  # right and fallback agree here
    proposals(log, [(RIGHT, "right"), (FALLBACK, "fallback")])
    a = step(log.evs, CFG)
    if isinstance(a, RequestModelProposal):  # contrastive round first, returns nothing new
        assert a.round_kind == "contrastive"
        log.add("ActionIssued", {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": a.round_kind})
        log.add("ModelProposalReturned", {"action_id": a.action_id, "usage": {}, "candidates": []}, "model")
        a = step(log.evs, CFG)
    assert isinstance(a, PresentPreview)
    assert a.request.purpose == "learning_preview" and [i[1] for i in a.request.items] == ["b1"]


def test_runtime_failure_rejects_candidate_without_crashing():
    bad = [{"op": "for_each", "var": "o", "over": {"ref": "objects"}, "body": [
        {"op": "emit_target", "kind": "move_existing", "target": {"ref": "locals.o"},
         "x": {"op": "div", "args": [1, 0]}, "y": 0}]}]
    log = Log()
    demo(log)
    registered(log, "b1", CLEAR, "batch")
    proposals(log, [(bad, "broken"), (RIGHT, "right")])
    a = step(log.evs, CFG)
    assert not isinstance(a, Abstain)


def test_approved_preview_commits_exactly_once_and_replay_commits_nothing_more():
    log = Log()
    demo(log)
    registered(log, "b1", CLEAR, "batch")
    proposals(log, [(RIGHT, "right")])
    a = step(log.evs, CFG)
    if isinstance(a, RequestModelProposal):
        log.add("ActionIssued", {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": a.round_kind})
        log.add("ModelProposalReturned", {"action_id": a.action_id, "usage": {}, "candidates": []}, "model")
        a = step(log.evs, CFG)
    assert isinstance(a, PresentPreview)
    from open_apprentice.teaching.teacher import request_to_json
    log.add("ActionIssued", {"action_id": a.action_id, "kind": "PresentPreview"})
    log.add("RequestIssued", {"request": request_to_json(a.request), "action_id": a.action_id})
    item = a.request.items[0][0]
    log.add("ResponseRecorded", {"response": response_to_json(Response(a.request.request_id, "items", per_item=((item, "approve"),)))}, "simulator")
    c = step(log.evs, CFG)
    assert isinstance(c, CommitVersion)
    log.add("ActionIssued", {"action_id": c.action_id, "kind": "CommitVersion"})
    log.add("VersionStored", {"action_id": c.action_id, "program_hash": c.program_hash})
    final = step(log.evs, CFG)
    assert not isinstance(final, CommitVersion)


def test_no_candidates_after_revision_abstains_with_search_limit_wording():
    log = Log()
    demo(log)
    registered(log, "b1", CLEAR, "batch")
    proposals(log, [])
    proposals(log, [], kind="revision")
    a = step(log.evs, CFG)
    assert isinstance(a, Abstain) and "within the search limits" in a.reason


def test_provider_failure_terminal_is_error_not_abstain():
    log = Log()
    demo(log)
    a = step(log.evs, CFG)
    log.add("ActionIssued", {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": a.round_kind})
    log.add("ModelCallFailed", {"action_id": a.action_id, "reason": "TruncatedOutput", "terminal": True})
    from open_apprentice.teaching.step import Error
    assert isinstance(step(log.evs, CFG), Error)
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_step.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'open_apprentice.teaching.step'`. (The test imports `open_apprentice.evaluation.labels` only to build reference programs; that is allowed in tests, never in `teaching/`.)

- [ ] **Step 3: Implement `step.py`**

```python
"""Pure learning policy: step(events, config) -> Action. Deterministic; never calls the model, the browser, storage or
the teacher. Spec section 4. Plan 1 searches batch documents only; generated probes arrive in Plan 4."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional, Union

from open_apprentice.concepts.hypotheses import fits
from open_apprentice.concepts.label_teaching import magic_condition
from open_apprentice.concepts.rules import RuleError, evaluate_rule, validate_rule
from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import Evidence, derive
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.teacher import (
    SEPARATION, ChooseOutput, ConfirmPreview, Output, Request, max_error, request_from_json, response_from_json,
)


@dataclass(frozen=True)
class StepConfig:
    max_choose: int = 3
    max_previews: int = 1
    max_preview_items: int = 3
    max_attempts: int = 8
    max_evaluations: int = 5_000_000


@dataclass(frozen=True)
class WaitForResult:
    action_id: str


@dataclass(frozen=True)
class RequestModelProposal:
    action_id: str
    round_kind: str
    feedback: tuple[str, ...] = ()


@dataclass(frozen=True)
class AskTeacher:
    action_id: str
    request: Request


@dataclass(frozen=True)
class PresentPreview:
    action_id: str
    request: ConfirmPreview
    program_hash: str


@dataclass(frozen=True)
class CommitVersion:
    action_id: str
    program_hash: str
    rule: list
    summary: str
    claim: str


@dataclass(frozen=True)
class Abstain:
    action_id: str
    reason: str


@dataclass(frozen=True)
class Error:
    action_id: str
    reason: str


Action = Union[WaitForResult, RequestModelProposal, AskTeacher, PresentPreview, CommitVersion, Abstain, Error]
RESULT_TYPES = {"ModelProposalReturned", "ModelCallFailed", "ResponseRecorded", "VersionStored", "Abstained", "Errored"}


def _aid(events: list[Event], kind: str) -> str:
    """Stable action id: the action kind plus the committed history it was decided on."""
    head = events[-1].event_id if events else "root"
    return codec.digest({"kind": kind, "head": head, "n": len(events)})[:24]


def run_output(rule: list, scene: dict) -> Optional[Output]:
    try:
        st = evaluate_rule(rule, scene["objects"], scene["canvas"])
    except RuleError:
        return None
    return {o["id"]: (st[o["id"]]["x"], st[o["id"]]["y"]) for o in scene["objects"] if o["kind"] == "label"}


def _forbidden_effect(rule: list, scene: dict) -> bool:
    """Only label x/y may change: no resize, no node move, no created objects."""
    try:
        st = evaluate_rule(rule, scene["objects"], scene["canvas"])
    except RuleError:
        return False
    ids = {o["id"] for o in scene["objects"]}
    if set(st) - ids:
        return True
    for o in scene["objects"]:
        s = st[o["id"]]
        if (s["w"], s["h"]) != (o["w"], o["h"]):
            return True
        if o["kind"] != "label" and (s["x"], s["y"]) != (o["x"], o["y"]):
            return True
    return False


def candidate_pool(events: list[Event]) -> list[dict]:
    seen: dict[str, dict] = {}
    for ev in events:
        if ev.type == "ModelProposalReturned":
            for c in ev.payload["candidates"]:
                h = codec.digest(c["rule"])
                seen.setdefault(h, {"hash": h, "rule": c["rule"], "summary": c.get("summary", ""), "text": c.get("text", "")})
    return list(seen.values())


def _filter(pool: list[dict], ev: Evidence) -> tuple[list[dict], list[str]]:
    keep, feedback = [], []
    constraints = ev.positives + ev.negatives
    for c in pool:
        try:
            validate_rule(c["rule"])
        except RuleError as e:
            feedback.append(f"{c['summary'][:60]} -- syntax/validation: {str(e)[:160]}")
            continue
        if magic_condition(c["rule"]):
            feedback.append(f"{c['summary'][:60]} -- inadmissible: compares a position, size or id with a constant")
            continue
        bad = next(((ok, why) for k in constraints for ok, why in [fits(c["rule"], k)] if not ok), None)
        if bad:
            feedback.append(f"{c['summary'][:60]} -- evidence mismatch: {bad[1][:200]}")
            continue
        if any(run_output(c["rule"], sc) is None for sc in ev.scenes.values()):
            feedback.append(f"{c['summary'][:60]} -- runtime: fails on a registered document")
            continue
        if any(_forbidden_effect(c["rule"], sc) for sc in ev.scenes.values()):
            feedback.append(f"{c['summary'][:60]} -- forbidden effect: moves or resizes something other than a label")
            continue
        keep.append(c)
    return keep, feedback


def _groups(cands: list[dict], scene: dict) -> list[tuple[Output, list[dict]]]:
    groups: list[tuple[Output, list[dict]]] = []
    for c in cands:
        out = run_output(c["rule"], scene)
        for g in groups:
            if g[0] == out:
                g[1].append(c)
                break
        else:
            groups.append((out, [c]))
    return groups


def _usable(groups: list[tuple[Output, list[dict]]]) -> bool:
    if not 2 <= len(groups) <= 4:
        return False
    for (a, _), (b, _) in combinations(groups, 2):
        e = max_error(a, b)
        if e is None or e <= SEPARATION:
            return False
    return True


def _separated_pairs(groups: list[tuple[Output, list[dict]]], n: int) -> int:
    return n * (n - 1) // 2 - sum(len(g) * (len(g) - 1) // 2 for _, g in groups)


def _selected(cands: list[dict]) -> dict:
    def size(c: dict) -> int:
        return len(codec.dumps(c["rule"]))
    return min(cands, key=lambda c: (size(c), c["hash"]))


def step(events: list[Event], config: StepConfig) -> Action:
    issued: dict[str, dict] = {}
    resolved: set[str] = set()
    rounds: list[str] = []
    attempts = 0
    stored = False
    for e in events:
        if e.type == "ActionIssued":
            issued[e.payload["action_id"]] = e.payload
            if e.payload["kind"] == "RequestModelProposal":
                rounds.append(e.payload.get("round_kind", "initial"))
                attempts += 1
        elif e.type in RESULT_TYPES and e.payload.get("action_id"):
            resolved.add(e.payload["action_id"])
        if e.type == "ModelCallFailed" and e.payload.get("terminal"):
            return Error(_aid(events, "Error"), f"provider: {e.payload['reason']}")
        if e.type == "VersionStored":
            stored = True
        if e.type in ("Abstained", "Errored"):
            return WaitForResult("terminal")

    # requests waiting on a teacher response
    requests = {request_from_json(e.payload["request"]).request_id: e.payload["action_id"]
                for e in events if e.type == "RequestIssued"}
    answered = {response_from_json(e.payload["response"]).request_id for e in events if e.type == "ResponseRecorded"}
    pending_requests = [rid for rid in requests if rid not in answered]
    outstanding = [a for a in issued if a not in resolved and a not in requests.values()]
    if pending_requests or outstanding:
        return WaitForResult(outstanding[0] if outstanding else requests[pending_requests[0]])
    if stored:
        return WaitForResult("done")

    ev = derive(events)
    if attempts >= config.max_attempts and "initial" in rounds and not candidate_pool(events):
        return Abstain(_aid(events, "Abstain"), "model attempt budget exhausted")

    # rule 1: no proposals yet
    if not rounds:
        return RequestModelProposal(_aid(events, "RequestModelProposal"), "initial")

    pool = candidate_pool(events)
    cands, feedback = _filter(pool, ev)

    # rule 2: empty pool
    if not cands:
        if "revision" not in rounds and attempts < config.max_attempts:
            return RequestModelProposal(_aid(events, "RequestModelProposal"), "revision", tuple(feedback[-8:]))
        return Abstain(_aid(events, "Abstain"), "no acceptable program found within the search limits")

    # rule 3: disagreement search over batch documents (generated probes: Plan 4)
    asked_scenes = {request_from_json(e.payload["request"]).scene_id for e in events
                    if e.type == "RequestIssued" and e.payload["request"]["type"] == "ChooseOutput"}
    choose_used = sum(1 for e in events if e.type == "RequestIssued" and e.payload["request"]["type"] == "ChooseOutput")
    best: Optional[tuple[tuple, str, list]] = None
    disagreement_found = False
    if len(cands) >= 2:
        for i, sid in enumerate(sorted(ev.batch)):
            if sid in ev.approved:
                continue
            groups = _groups(cands, ev.scenes[sid])
            if len(groups) >= 2:
                disagreement_found = True
            if not _usable(groups) or sid in asked_scenes:
                continue
            score = (-_separated_pairs(groups, len(cands)), i)
            if best is None or score < best[0]:
                best = (score, sid, groups)
    if best is not None:
        if choose_used >= config.max_choose:
            return Abstain(_aid(events, "Abstain"), "unresolved disagreement")
        _, sid, groups = best
        alts = tuple((chr(65 + k), out) for k, (out, _) in enumerate(groups))
        aid = _aid(events, "AskTeacher")
        return AskTeacher(aid, ChooseOutput(f"q-{aid}", sid, ev.scene_hashes[sid], alts))
    if disagreement_found:
        return Abstain(_aid(events, "Abstain"), "unresolved disagreement")

    # rule 4: one program, or no disagreement found: one contrastive round
    if "contrastive" not in rounds and attempts < config.max_attempts:
        return RequestModelProposal(_aid(events, "RequestModelProposal"), "contrastive")

    # rule 6: commit predicate, preview, or abstain
    sel = _selected(cands)
    approvals = [sid for sid in ev.batch if sid in ev.approved and run_output(sel["rule"], ev.scenes[sid]) == ev.approved[sid]]
    unresolved_reject = any(run_output(sel["rule"], ev.scenes[s]) in outs for s, outs in ev.rejected.items())
    previews_used = sum(1 for e in events if e.type == "RequestIssued" and e.payload["request"]["type"] == "ConfirmPreview")
    if approvals and not unresolved_reject:
        claim = (f"consistent with all evidence; approved on {len(approvals)} previewed document(s); "
                 f"no distinguishing alternative found over {len(ev.batch)} searched document(s)")
        return CommitVersion(_aid(events, "CommitVersion"), sel["hash"], sel["rule"], sel["summary"], claim)
    unlabelled = [s for s in sorted(ev.batch) if s not in ev.approved and s not in ev.rejected]
    if previews_used < config.max_previews and unlabelled:
        def moves(sid: str) -> int:
            out = run_output(sel["rule"], ev.scenes[sid]) or {}
            return sum(1 for o in ev.scenes[sid]["objects"] if o["id"] in out and out[o["id"]] != (o["x"], o["y"]))
        chosen = sorted(unlabelled, key=lambda s: (-moves(s), s))[: config.max_preview_items]
        aid = _aid(events, "PresentPreview")
        items = tuple((f"i{k}", s, ev.scene_hashes[s], run_output(sel["rule"], ev.scenes[s])) for k, s in enumerate(chosen))
        return PresentPreview(aid, ConfirmPreview(f"p-{aid}", "learning_preview", items), sel["hash"])
    return Abstain(_aid(events, "Abstain"), "no approved preview" if not unresolved_reject else "preview rejected")
```

Note: the rejected-preview revision path (spec 4: exclusion → contradiction revision → back to rule 0) is covered because a rejection is a negative constraint that `_filter` applies; if it empties the pool, rule 2 triggers the shared revision.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_step.py -v`
Expected: 7 passed. If `test_indistinguishable_candidates_go_to_preview_and_both_survive` fails because `RIGHT` and `FALLBACK` happen to differ on `CLEAR`, print `run_output` for both on `CLEAR` and adjust the `CLEAR` scene (it must leave l0's right-hand spot free and on the canvas) — do not change the policy.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/teaching/step.py tests/unit/teaching/test_step.py
git commit -m "feat(teaching): pure step policy (batch questions, contrastive round, preview, commit predicate, error vs abstain)"
```

---

### Task 7: Attempt records and exposure accounting

**Files:**
- Create: `src/open_apprentice/teaching/accounting.py`
- Test: `tests/unit/teaching/test_accounting.py`

**Interfaces:**
- Consumes: `Store`, `PreconditionFailed` (Task 2), `codec` (Task 3).
- Produces:
  - `class OverBudget(Exception)`
  - `class Ledger`: `__init__(self, store: Store, cap_usd: Fraction)`; `reserve(self, attempt_id: str, action_id: str, worst_usd: Fraction) -> None` (atomic; raises `OverBudget`); `dispatched(self, attempt_id: str) -> None`; `settle(self, attempt_id: str, actual_usd: Fraction) -> None`; `fail_before_dispatch(self, attempt_id: str) -> None` (releases the reservation); `mark_unknown(self, attempt_id: str) -> None`; `exposure(self) -> dict[str, Fraction]` with keys `settled`, `reserved`, `uncertain`, `total`; `state(self, attempt_id: str) -> str | None`

States: `reserved` (counts in `reserved`), `dispatched` (counts in `uncertain` at its worst case until settled), `completed` (counts in `settled` at actual), `released` (counts nowhere), `outcome_unknown` (counts in `uncertain` at worst). Each attempt is in exactly one state.

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction as F

import pytest

from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.accounting import Ledger, OverBudget


def test_each_attempt_counts_in_exactly_one_category(tmp_path):
    L = Ledger(LocalStore(tmp_path), cap_usd=F(1))
    L.reserve("a1", "act", F(1, 10))
    assert L.exposure() == {"settled": 0, "reserved": F(1, 10), "uncertain": 0, "total": F(1, 10)}
    L.dispatched("a1")
    assert L.exposure()["reserved"] == 0 and L.exposure()["uncertain"] == F(1, 10)
    L.settle("a1", F(3, 100))
    assert L.exposure() == {"settled": F(3, 100), "reserved": 0, "uncertain": 0, "total": F(3, 100)}


def test_crash_after_dispatch_keeps_worst_case_exposure(tmp_path):
    L = Ledger(LocalStore(tmp_path), cap_usd=F(1))
    L.reserve("a1", "act", F(1, 10))
    L.dispatched("a1")
    L.mark_unknown("a1")
    assert L.state("a1") == "outcome_unknown" and L.exposure()["uncertain"] == F(1, 10)


def test_reservation_is_refused_over_cap(tmp_path):
    L = Ledger(LocalStore(tmp_path), cap_usd=F(1, 10))
    L.reserve("a1", "act", F(1, 10))
    with pytest.raises(OverBudget):
        L.reserve("a2", "act", F(1, 100))


def test_duplicate_reserve_is_idempotent(tmp_path):
    L = Ledger(LocalStore(tmp_path), cap_usd=F(1))
    L.reserve("a1", "act", F(1, 10))
    L.reserve("a1", "act", F(1, 10))
    assert L.exposure()["reserved"] == F(1, 10)


def test_two_ledgers_on_one_store_share_state(tmp_path):
    s = LocalStore(tmp_path)
    Ledger(s, F(1)).reserve("a1", "act", F(1, 2))
    with pytest.raises(OverBudget):
        Ledger(s, F(1)).reserve("a2", "act", F(3, 5))
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_accounting.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `accounting.py`**

```python
"""Durable exposure ledger. exposure = settled + outstanding reservations + conservative exposure of dispatched or
uncertain attempts; every attempt is in exactly one state. Exactly-once provider execution is NOT claimed."""

from __future__ import annotations

from fractions import Fraction
from typing import Callable, Optional

from open_apprentice.storage.store import PreconditionFailed, Store
from open_apprentice.teaching import codec

KEY = "ledger/manifest.json"


class OverBudget(Exception):
    pass


class Ledger:
    def __init__(self, store: Store, cap_usd: Fraction) -> None:
        self.store, self.cap = store, Fraction(cap_usd)

    def _update(self, fn: Callable[[dict], None]) -> dict:
        for _ in range(50):
            b = self.store.get(KEY)
            doc = codec.loads(b.data) if b else {"attempts": {}}
            fn(doc)
            try:
                self.store.put(KEY, codec.dumps(doc), if_generation=b.generation if b else None)
                return doc
            except PreconditionFailed:
                continue
        raise RuntimeError("ledger contention")

    @staticmethod
    def _sum(doc: dict) -> dict[str, Fraction]:
        out = {"settled": Fraction(0), "reserved": Fraction(0), "uncertain": Fraction(0)}
        for a in doc["attempts"].values():
            st = a["state"]
            if st == "completed":
                out["settled"] += codec.frac(a["actual"])
            elif st == "reserved":
                out["reserved"] += codec.frac(a["worst"])
            elif st in ("dispatched", "outcome_unknown"):
                out["uncertain"] += codec.frac(a["worst"])
        out["total"] = out["settled"] + out["reserved"] + out["uncertain"]
        return out

    def reserve(self, attempt_id: str, action_id: str, worst_usd: Fraction) -> None:
        def fn(doc: dict) -> None:
            if attempt_id in doc["attempts"]:
                return
            if self._sum(doc)["total"] + Fraction(worst_usd) > self.cap:
                raise OverBudget(f"reserving {worst_usd} would exceed cap {self.cap}")
            doc["attempts"][attempt_id] = {"action_id": action_id, "worst": Fraction(worst_usd), "state": "reserved"}
        self._update(fn)

    def _transition(self, attempt_id: str, allowed: tuple[str, ...], new: str, actual: Optional[Fraction] = None) -> None:
        def fn(doc: dict) -> None:
            a = doc["attempts"][attempt_id]
            if a["state"] == new:
                return
            if a["state"] not in allowed:
                raise ValueError(f"{attempt_id}: {a['state']} -> {new} not allowed")
            a["state"] = new
            if actual is not None:
                a["actual"] = Fraction(actual)
        self._update(fn)

    def dispatched(self, attempt_id: str) -> None:
        self._transition(attempt_id, ("reserved",), "dispatched")

    def settle(self, attempt_id: str, actual_usd: Fraction) -> None:
        self._transition(attempt_id, ("dispatched", "outcome_unknown"), "completed", actual_usd)

    def fail_before_dispatch(self, attempt_id: str) -> None:
        self._transition(attempt_id, ("reserved",), "released")

    def mark_unknown(self, attempt_id: str) -> None:
        self._transition(attempt_id, ("dispatched",), "outcome_unknown")

    def exposure(self) -> dict[str, Fraction]:
        b = self.store.get(KEY)
        return self._sum(codec.loads(b.data) if b else {"attempts": {}})

    def state(self, attempt_id: str) -> Optional[str]:
        b = self.store.get(KEY)
        return codec.loads(b.data)["attempts"].get(attempt_id, {}).get("state") if b else None
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_accounting.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/teaching/accounting.py tests/unit/teaching/test_accounting.py
git commit -m "feat(teaching): durable exposure ledger with one state per attempt (reserved/dispatched/settled/unknown)"
```

---

### Task 8: Local executor and the effect-free replay gate (spec gate 2.3, part 2)

**Files:**
- Create: `src/open_apprentice/teaching/executor.py`
- Test: `tests/unit/teaching/test_executor.py`

**Interfaces:**
- Consumes: `SessionLog`, `Conflict` (Task 3); `Teacher`, `validate_request`, `validate_response`, `request_to_json`, `response_to_json`, `ProtocolError` (Task 4); `step`, actions, `StepConfig` (Task 6); `Ledger` (Task 7); `Store`.
- Produces:
  - `class Proposer(Protocol): def propose(self, evidence_json: dict, round_kind: str, feedback: tuple[str, ...]) -> tuple[list[dict], dict, Fraction]` (candidates `[{rule, summary, text}]`, usage, actual cost)
  - `class Executor`: `__init__(self, store: Store, log: SessionLog, proposer: Proposer, teacher: Teacher, ledger: Ledger, config: StepConfig, worst_usd: Fraction = Fraction(1, 5))`; `run(self, max_steps: int = 50) -> str` returns the final status `committed | abstained | error | waiting`
  - Effects are claimed via `store.create(f"claims/{action_id}.json", ...)`; a claim that exists means the action was already performed or is in progress: the executor does not perform it again.

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.events import SessionLog
from open_apprentice.teaching.executor import Executor
from open_apprentice.teaching.step import StepConfig, run_output
from open_apprentice.teaching.teacher import ConfirmPreview, Response

RIGHT = rule_for_spec(Spec("right", None, "all", F(12)))
SCENE = {"objects": [
    {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
    {"id": "l0", "kind": "label", "role": "note", "attached": "n0", "x": 0, "y": 60, "w": 40, "h": 20}],
    "canvas": {"w": 600, "h": 400}}


class CountingProposer:
    def __init__(self):
        self.calls = 0

    def propose(self, evidence_json, round_kind, feedback):
        self.calls += 1
        return ([{"rule": RIGHT, "summary": "right", "text": ""}] if round_kind == "initial" else []), {}, F(1, 100)


class ApprovingTeacher:
    def __init__(self):
        self.asked = 0

    def ask(self, req):
        self.asked += 1
        assert isinstance(req, ConfirmPreview)
        return Response(req.request_id, "items", per_item=tuple((i[0], "approve") for i in req.items), source="simulator")


def start(tmp_path):
    store = LocalStore(tmp_path)
    log = SessionLog(store, "s1")
    log.create(owner="o")
    for sid, role in (("d", "demo"), ("b1", "batch")):
        log.append("SceneRegistered", "system", {"scene_id": sid, "scene_hash": codec.digest(SCENE),
                                                 "scene": codec.loads(codec.dumps(SCENE)), "role": role})
    log.append("DemonstrationRecorded", "human", {"scene_id": "d", "output": codec.loads(codec.dumps(run_output(RIGHT, SCENE)))})
    return store, log


def test_full_episode_commits_with_scripted_proposer_and_teacher(tmp_path):
    store, log = start(tmp_path)
    p, t = CountingProposer(), ApprovingTeacher()
    status = Executor(store, log, p, t, Ledger(store, F(5)), StepConfig()).run()
    assert status == "committed" and t.asked == 1
    assert [e.type for e in log.events()].count("VersionStored") == 1


def test_replay_is_effect_free(tmp_path):
    store, log = start(tmp_path)
    p, t = CountingProposer(), ApprovingTeacher()
    ledger = Ledger(store, F(5))
    Executor(store, log, p, t, ledger, StepConfig()).run()
    calls, asked, n_events, spent = p.calls, t.asked, len(log.events()), ledger.exposure()["total"]
    # a second executor over the same committed log (restart, duplicate delivery) must do nothing
    Executor(store, SessionLog(store, "s1"), p, t, ledger, StepConfig()).run()
    assert (p.calls, t.asked, len(log.events()), ledger.exposure()["total"]) == (calls, asked, n_events, spent)


def test_response_to_answered_request_is_rejected(tmp_path):
    store, log = start(tmp_path)
    ex = Executor(store, log, CountingProposer(), ApprovingTeacher(), Ledger(store, F(5)), StepConfig())
    ex.run()
    rid = next(e.payload["request"]["request_id"] for e in log.events() if e.type == "RequestIssued")
    n = len(log.events())
    assert ex.submit_response(Response(rid, "items", per_item=(("i0", "reject"),))) is False
    assert len(log.events()) == n
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_executor.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `executor.py`**

```python
"""Local executor: repeatedly step() the committed log and perform the returned action exactly as the spec's worker does
(Plan 4 moves this behind Cloud Tasks). Effects are claimed in the store by action id, so a restart or a duplicate run
never re-performs an action whose claim exists."""

from __future__ import annotations

import uuid
from fractions import Fraction
from typing import Protocol

from open_apprentice.concepts.label_teaching import describe_compact
from open_apprentice.storage.store import Store
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger, OverBudget
from open_apprentice.teaching.constraints import derive
from open_apprentice.teaching.events import Conflict, SessionLog
from open_apprentice.teaching.step import (
    Abstain, AskTeacher, CommitVersion, Error, PresentPreview, RequestModelProposal, StepConfig, WaitForResult, step,
)
from open_apprentice.teaching.teacher import (
    ProtocolError, Response, Teacher, request_from_json, request_to_json, response_from_json, response_to_json,
    validate_request, validate_response,
)


class Proposer(Protocol):
    def propose(self, evidence_json: dict, round_kind: str, feedback: tuple[str, ...]) -> tuple[list[dict], dict, Fraction]: ...


class Executor:
    def __init__(self, store: Store, log: SessionLog, proposer: Proposer, teacher: Teacher, ledger: Ledger,
                 config: StepConfig, worst_usd: Fraction = Fraction(1, 5)) -> None:
        self.store, self.log, self.proposer, self.teacher = store, log, proposer, teacher
        self.ledger, self.config, self.worst = ledger, config, worst_usd

    def _claim(self, action_id: str) -> bool:
        return self.store.create(f"claims/{action_id}.json", codec.dumps({"action_id": action_id}))

    def _issue(self, action_id: str, kind: str, extra: dict | None = None) -> None:
        self.log.append("ActionIssued", "system", {"action_id": action_id, "kind": kind, **(extra or {})})

    def submit_response(self, resp: Response) -> bool:
        """Accept a teacher response only if its request is outstanding. Returns False (and records nothing) otherwise."""
        evs = self.log.events()
        reqs = {request_from_json(e.payload["request"]).request_id: request_from_json(e.payload["request"])
                for e in evs if e.type == "RequestIssued"}
        answered = {response_from_json(e.payload["response"]).request_id for e in evs if e.type == "ResponseRecorded"}
        req = reqs.get(resp.request_id)
        if req is None or resp.request_id in answered:
            return False
        try:
            validate_response(req, resp)
        except ProtocolError:
            return False
        self.log.append("ResponseRecorded", resp.source if resp.source in ("human", "simulator") else "human",
                        {"response": response_to_json(resp)})
        return True

    def _perform(self, action: object) -> None:
        if isinstance(action, RequestModelProposal):
            if not self._claim(action.action_id):
                return
            self._issue(action.action_id, "RequestModelProposal", {"round_kind": action.round_kind})
            attempt = uuid.uuid4().hex
            try:
                self.ledger.reserve(attempt, action.action_id, self.worst)
            except OverBudget as e:
                self.log.append("ModelCallFailed", "system", {"action_id": action.action_id, "reason": f"budget: {e}", "terminal": True})
                return
            self.ledger.dispatched(attempt)
            try:
                ev = derive(self.log.events())
                cands, usage, cost = self.proposer.propose(
                    {"teaching_evidence": describe_compact(ev.positives)}, action.round_kind, action.feedback)
            except Exception as e:  # provider failure: uncertain cost, recorded
                self.ledger.mark_unknown(attempt)
                self.log.append("ModelCallFailed", "system", {"action_id": action.action_id, "reason": type(e).__name__, "terminal": True})
                return
            self.ledger.settle(attempt, cost)
            self.log.append("ModelProposalReturned", "model", {"action_id": action.action_id, "candidates": cands, "usage": usage})
        elif isinstance(action, (AskTeacher, PresentPreview)):
            if not self._claim(action.action_id):
                return
            evs = self.log.events()
            registered = derive(evs).scene_hashes
            validate_request(action.request, registered)
            self._issue(action.action_id, type(action).__name__)
            self.log.append("RequestIssued", "system", {"request": request_to_json(action.request), "action_id": action.action_id})
            resp = self.teacher.ask(action.request)
            self.submit_response(resp)
        elif isinstance(action, CommitVersion):
            if not self._claim(action.action_id):
                return
            self._issue(action.action_id, "CommitVersion")
            key = f"programs/{action.program_hash}.json"
            self.store.create(key, codec.dumps({"rule": action.rule, "summary": action.summary, "claim": action.claim}))
            self.log.append("VersionStored", "system", {"action_id": action.action_id, "program_hash": action.program_hash})
        elif isinstance(action, Abstain):
            if self._claim(action.action_id):
                self.log.append("Abstained", "system", {"action_id": action.action_id, "reason": action.reason})
        elif isinstance(action, Error):
            if self._claim(action.action_id):
                self.log.append("Errored", "system", {"action_id": action.action_id, "reason": action.reason})

    def run(self, max_steps: int = 50) -> str:
        for _ in range(max_steps):
            evs = self.log.events()
            types = {e.type for e in evs}
            if "VersionStored" in types:
                return "committed"
            if "Abstained" in types:
                return "abstained"
            if "Errored" in types:
                return "error"
            action = step(evs, self.config)
            if isinstance(action, WaitForResult):
                return "waiting"
            try:
                self._perform(action)
            except Conflict:
                continue  # someone else advanced the log: re-read and re-step
        return "waiting"
```

Note: `describe_compact` lives in `concepts/label_teaching.py`, not `hypotheses.py`.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_executor.py -v`
Expected: 3 passed. `test_replay_is_effect_free` is the spec's gate 2.3 part 2.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/teaching/executor.py tests/unit/teaching/test_executor.py
git commit -m "feat(teaching): local executor with claimed effects; effect-free replay gate"
```

---

### Task 9: Simulator teacher process

**Files:**
- Create: `src/open_apprentice/evaluation/teacher_sim.py`
- Test: `tests/unit/teaching/test_teacher_sim.py`

**Interfaces:**
- Consumes: `request_from_json`, `response_to_json`, `max_error`, `TOL`, `ChooseOutput`, `ConfirmPreview`, `RequestDemonstration`, `Response` (Task 4); `constraints.scene_from_payload` (Task 5); `evaluation.labels.Spec`, `oracle` (existing).
- Produces:
  - `class SimTeacher`: `__init__(self, spec: Spec, scenes: dict[str, dict])`; `answer(self, req) -> Response` (raises `ProtocolError` on an ambiguous match)
  - CLI: `python -m open_apprentice.evaluation.teacher_sim SPEC_JSON SCENES_JSON LOG_JSONL` reads JSON-line requests on stdin, writes JSON-line responses (or `{"protocol_error": ...}`) to stdout, appends every exchange to `LOG_JSONL`.

- [ ] **Step 1: Write the failing tests**

```python
import json
import subprocess
import sys
from fractions import Fraction as F

import pytest

from open_apprentice.evaluation.labels import Spec, oracle
from open_apprentice.evaluation.teacher_sim import SimTeacher
from open_apprentice.teaching import codec
from open_apprentice.teaching.teacher import ChooseOutput, ConfirmPreview, ProtocolError, SubprocessTeacher

SCENE = {"objects": [
    {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
    {"id": "l0", "kind": "label", "role": "note", "attached": "n0", "x": 0, "y": 60, "w": 40, "h": 20}],
    "canvas": {"w": 600, "h": 400}}
SPEC = Spec("right", None, "all", F(12))
TRUTH = oracle(SPEC, SCENE)  # {"l0": (112, 15)}
H = codec.digest(SCENE)


def test_chooses_the_matching_alternative_or_none():
    t = SimTeacher(SPEC, {"s": SCENE})
    q = ChooseOutput("q", "s", H, (("A", dict(TRUTH)), ("B", {"l0": (F(30), F(62))})))
    assert t.answer(q).selected == "A"
    q2 = ChooseOutput("q2", "s", H, (("A", {"l0": (F(200), F(15))}), ("B", {"l0": (F(30), F(62))})))
    assert t.answer(q2).kind == "none"


def test_ambiguous_match_is_protocol_error():
    t = SimTeacher(SPEC, {"s": SCENE})
    x, y = TRUTH["l0"]
    q = ChooseOutput("q", "s", H, (("A", {"l0": (x - F(1, 4), y)}), ("B", {"l0": (x + F(1, 4), y)})))
    with pytest.raises(ProtocolError):
        t.answer(q)


def test_preview_is_judged_per_item():
    t = SimTeacher(SPEC, {"s": SCENE, "u": SCENE})
    p = ConfirmPreview("p", "learning_preview", (("i0", "s", H, dict(TRUTH)), ("i1", "u", H, {"l0": (F(30), F(62))})))
    assert dict(t.answer(p).per_item) == {"i0": "approve", "i1": "reject"}


def test_subprocess_teacher_round_trip(tmp_path):
    spec_f, scenes_f, log_f = tmp_path / "spec.json", tmp_path / "scenes.json", tmp_path / "log.jsonl"
    spec_f.write_text(json.dumps({"primary": "right", "fallback": None, "scope": "all", "gap": 12}))
    scenes_f.write_text(codec.dumps({"s": SCENE}).decode())
    t = SubprocessTeacher([sys.executable, "-m", "open_apprentice.evaluation.teacher_sim", str(spec_f), str(scenes_f), str(log_f)])
    r = t.ask(ChooseOutput("q", "s", H, (("A", dict(TRUTH)), ("B", {"l0": (F(30), F(62))}))))
    t.close()
    assert r.selected == "A" and r.source == "deterministic_simulator"
    assert len(log_f.read_text().splitlines()) == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_teacher_sim.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `teacher_sim.py`**

```python
"""Deterministic simulated teacher (evaluation side). It alone holds the hidden spec. It answers the four request types
by comparing displayed outputs with the spec's output under the declared tolerance; it never reveals the spec, the
category or unseen answers, and it raises a protocol error rather than choosing between two matching alternatives."""

from __future__ import annotations

import json
import sys
from fractions import Fraction

from open_apprentice.evaluation.labels import Spec, oracle
from open_apprentice.teaching.constraints import scene_from_payload
from open_apprentice.teaching.teacher import (
    TOL, ChooseOutput, ConfirmPreview, Output, ProtocolError, RequestDemonstration, Response, max_error,
    request_from_json, response_to_json,
)


class SimTeacher:
    def __init__(self, spec: Spec, scenes: dict[str, dict]) -> None:
        self.spec, self.scenes = spec, scenes

    def _truth(self, scene_id: str) -> Output:
        scene = self.scenes[scene_id]
        moved = oracle(self.spec, scene)
        return {o["id"]: moved.get(o["id"], (Fraction(o["x"]), Fraction(o["y"])))
                for o in scene["objects"] if o["kind"] == "label"}

    def _matches(self, out: Output, scene_id: str) -> bool:
        e = max_error(out, self._truth(scene_id))
        return e is not None and e <= TOL

    def answer(self, req: object) -> Response:
        src = "deterministic_simulator"
        if isinstance(req, ChooseOutput):
            hits = [a for a, out in req.alternatives if self._matches(out, req.scene_id)]
            if len(hits) > 1:
                raise ProtocolError("more than one alternative matches the intended output")
            return Response(req.request_id, "choose", selected=hits[0], source=src) if hits else Response(req.request_id, "none", source=src)
        if isinstance(req, ConfirmPreview):
            verdicts = tuple((i, "approve" if self._matches(out, sid) else "reject") for i, sid, _, out in req.items)
            return Response(req.request_id, "items", per_item=verdicts, source=src)
        if isinstance(req, RequestDemonstration):
            return Response(req.request_id, "demonstrate", output=self._truth(req.scene_id), source=src)
        raise ProtocolError(f"unsupported request {type(req).__name__}")


def main() -> None:
    spec_path, scenes_path, log_path = sys.argv[1:4]
    s = json.loads(open(spec_path).read())
    spec = Spec(s["primary"], s["fallback"], s["scope"], Fraction(s["gap"]))
    scenes = {k: scene_from_payload(v) for k, v in json.loads(open(scenes_path).read()).items()}
    t = SimTeacher(spec, scenes)
    with open(log_path, "a") as log:
        for line in sys.stdin:
            req_json = json.loads(line)
            try:
                out = response_to_json(t.answer(request_from_json(req_json)))
            except ProtocolError as e:
                out = {"protocol_error": str(e)}
            log.write(json.dumps({"request": req_json, "response": out}) + "\n")
            log.flush()
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_teacher_sim.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/evaluation/teacher_sim.py tests/unit/teaching/test_teacher_sim.py
git commit -m "feat(evaluation): deterministic simulator teacher process (per-item previews, protocol error on ambiguous match)"
```

---

### Task 10: Learner-process isolation

**Files:**
- Create: `src/open_apprentice/teaching/isolation.py`
- Test: `tests/unit/teaching/test_isolation.py`

**Interfaces:**
- Produces: `install_learner_guard(forbidden_prefix: str = "open_apprentice.evaluation") -> None` (Python audit hook raising `ImportError` on importing any module under the prefix after installation; idempotent).

- [ ] **Step 1: Write the failing tests** (run in a subprocess because audit hooks cannot be removed)

```python
import subprocess
import sys


def run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={"PYTHONPATH": "src"})


def test_guard_blocks_evaluation_imports_after_install():
    r = run("from open_apprentice.teaching.isolation import install_learner_guard\n"
            "install_learner_guard()\n"
            "import open_apprentice.evaluation.labels\n")
    assert r.returncode != 0 and "learner process may not import" in r.stderr


def test_guard_allows_teaching_modules():
    r = run("from open_apprentice.teaching.isolation import install_learner_guard\n"
            "install_learner_guard()\n"
            "import open_apprentice.teaching.step\n"
            "print('ok')\n")
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


def test_learner_modules_do_not_pull_in_the_evaluator():
    r = run("import sys\n"
            "import open_apprentice.teaching.executor\n"
            "bad = [m for m in sys.modules if m.startswith('open_apprentice.evaluation')]\n"
            "print(bad)\n"
            "assert not bad\n")
    assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_isolation.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `isolation.py`**

```python
"""Runtime guard for learner processes: after installation, importing the evaluator raises. Complements the static
import-linter contract (which cannot stop a hidden oracle being passed in at runtime)."""

from __future__ import annotations

import sys

_installed = False


def install_learner_guard(forbidden_prefix: str = "open_apprentice.evaluation") -> None:
    global _installed
    if _installed:
        return

    def hook(event: str, args: tuple) -> None:
        if event == "import" and args and isinstance(args[0], str) and (
            args[0] == forbidden_prefix or args[0].startswith(forbidden_prefix + ".")
        ):
            raise ImportError(f"learner process may not import {args[0]}")

    sys.addaudithook(hook)
    _installed = True
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_isolation.py -v`
Expected: 3 passed. If `test_learner_modules_do_not_pull_in_the_evaluator` fails, find the import chain with `python -X importtime -c "import open_apprentice.teaching.executor" 2>&1 | grep evaluation` and remove the dependency from the `teaching/` side (never from the test).

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/teaching/isolation.py tests/unit/teaching/test_isolation.py
git commit -m "feat(teaching): learner-process import audit hook blocking the evaluator"
```

---

### Task 11: Import contract, implementation audit, full suite

**Files:**
- Modify: `pyproject.toml` (the `[[tool.importlinter.contracts]]` block, lines 71-84)
- Create: `docs/implementation_audit.md`

- [ ] **Step 1: Extend the import contract.** Add a second contract below the existing one:

```toml
[[tool.importlinter.contracts]]
name = "New learning-core packages never import the evaluator"
type = "forbidden"
source_modules = [
  "open_apprentice.teaching",
  "open_apprentice.storage",
]
forbidden_modules = [
  "open_apprentice.evaluation",
]
```

Also try adding `"open_apprentice.evaluation.labels"`, `"open_apprentice.evaluation.label_episodes"`, `"open_apprentice.evaluation.label_runner"`, `"open_apprentice.evaluation.label_reference"`, `"open_apprentice.evaluation.teacher_sim"` to the existing contract's `forbidden_modules`.

- [ ] **Step 2: Run the contract**

Run: `PYTHONPATH=src .venv/bin/lint-imports`
Expected: `Contracts: 2 kept, 0 broken.` If the existing contract breaks after the additions in Step 1, list the offending import chain in `docs/implementation_audit.md` and revert only that addition (do not weaken the new contract).

- [ ] **Step 3: Write `docs/implementation_audit.md`**: a table mapping every numbered spec section (2.1–13) to: existing code reused (path), new code (path from this plan or "Plan N"), status (`implemented` / `planned` / `deviation`), and the evidence (test name). Include the `describe_compact` and `magic_condition` reuse, the held-back validation removal (old `label_teaching.teach` is kept only for reproducing earlier results and is not used by `teaching/`), and the spike verdict link.

- [ ] **Step 4: Full local suite**

Run: `OA_ENGINE_TESTS=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q tests` (sandbox disabled), then `.venv/bin/ruff check src tests scripts && .venv/bin/black --check src tests scripts`
Expected: all pass (529 existing + the new tests), ruff and black clean. Read the output; do not claim success without it.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml docs/implementation_audit.md
git commit -m "chore: import contract for the learning core; implementation audit"
```

---

## Self-review (completed while writing)

- **Spec coverage for Plan 1's scope:** gate 2.3 part 1 (Task 0), part 2 (Task 8 `test_replay_is_effect_free`); storage and commit chain 3.1 (Tasks 2–3); two revisions 3.2 (manifest carries `intent_revision`; dependency-based result acceptance is completed in Plan 4 with the Cloud Tasks worker, where results can arrive late — recorded in the roadmap); event types 3.3 (subset used here; correction types in Plan 2); request types 3.4 (three of four; scope in Plan 2); constraint semantics 3.5 (Task 5); tolerance 3.6 (Tasks 4, 9); budgets and accounting 3.7 (Tasks 6, 7, 8); step policy 4 (Task 6, batch-only search; probes Plan 4); simulator and isolation 7 (Tasks 9, 10); corpus timing (Task 1, 16 Oct).
- **Deferred and named:** activation records and versions (Plan 2); GCS backend (Plan 2); dependency-based stale-result acceptance with concurrent workers (Plan 4); generated probes and the aggregate statement budget (Plan 4; `StepConfig.max_evaluations` is declared now and enforced when probes exist); baselines B/C/D (Plan 5).
- **Type consistency:** `Output`, `run_output`, `request_to_json`/`response_to_json`, `derive`/`Evidence`, `StepConfig`, action dataclasses and `Executor.submit_response` are used with the same names and signatures across Tasks 4–10.
