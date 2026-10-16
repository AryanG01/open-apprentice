# Screens and Journeys Implementation Plan (Plan 4C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A person can do the whole flow in the browser on real `.drawio` files — import and map, teach by dragging labels, answer
clarifying questions on rendered alternatives, approve a preview (blocked documents shown with reasons and not approvable), reuse the
skill on other documents and download the results, correct an exception and review the revision — and a real-browser journey test
proves it.

**Architecture:**
- Two backend additions to `/api/v2`: (1) scene geometry plus the document→image offset for overlays; (2) per-question item renders
  (PNG of each alternative / preview item / interpretation consequence) and per-item layout status, with approval of a blocked item
  refused. This closes the Plan 4A finding that a preview could show an output that later fails layout.
- A new `apps/web/src/v2/` folder: a typed API client, pure geometry helpers, a session-polling hook, a `DocumentView` overlay
  component, and one screen component per step, composed by `Apprentice.tsx`. `App.tsx` makes "Apprentice" the default tab and moves
  the existing tabs under "Earlier prototype", unchanged.
- The journey test (`tests/e2e/journey.test.mjs`) drives real Chromium against the real API and engine with the offline learner.

**Tech Stack:** React 18 + TypeScript + Vite (existing), FastAPI (existing), Playwright via `node --test` (existing e2e pattern).

**Spec:** `docs/superpowers/specs/2026-10-15-teach-correct-reuse-design.md` section 8 (screens, previews and overlays, provenance,
paid mode), 9 C (journey test). Built on Plan 4A's `/api/v2` (`docs/superpowers/plans/2026-10-16-p4a-api-v2.md`).

## Global Constraints

- TypeScript: no `any`/`unknown` unless necessary; named exports; `const`; ESLint (`npm run lint`, includes react-hooks rules) must stay
  at 0 errors. No new runtime dependency.
- Spec 8 wording and behaviour, exactly:
  - Teach: drag labels, then an explicit **"This whole document is right"** confirmation records the demonstration. A demonstration is
    recorded only after the user has seen the deterministic draft render that follows each drop.
  - Keys: arrow = 1 unit, Shift+arrow = 10, Alt+arrow = 1/64.
  - Clarify: 2–4 rendered alternatives + **None** / **Not sure** / **Cancel**.
  - Preview: per document **Approve** / **Reject** / **Not sure**; blocked documents with reasons.
  - Correct: partial by default; explicit per-document full approval.
  - Review revision: scope options with rendered consequences, per-item affected-example approval, revision preview.
  - Safety line under every preview image: "Previews are displayed in image context; uploaded content is separately validated and
    rendered in the locked engine."
  - Provenance shown per session, run and artifact as `Model: Live|Recorded|Fixture · Teacher: You|Simulated`.
  - When live inference is unavailable: "Live inference is unavailable. Open the recorded example." No recorded v2 example exists yet
    (it needs an approved paid run), so the message links to the "Earlier prototype" tab's recorded replay and says so; never a silent swap.
  - Polling every 2 s; responses carry `manifest_revision` and stale ones are ignored; reload resumes the stored session (URL hash).
  - Scope / superseded / unexplained states use text and icons as well as colour.
- The badge flow stays reachable, unchanged, under "Earlier prototype"; its existing e2e test keeps passing (update only how it
  reaches the tabs).
- Accessibility basics: every control has a label; images have alt text naming the document; the overlay labels are focusable buttons;
  a numeric x/y field pair edits the selected label for keyboard and screen-reader users.

## Review Focus

1. **Overlay alignment:** the label boxes drawn over a preview must sit on the rendered labels at any displayed size (window resize,
   zoom), including after a draft render whose image size or offset changed. (Task 3 unit test of the transform; Task 9 journey check.)
2. **Stale poll overwrite:** a slow poll response with a lower `manifest_revision` must never replace newer state on screen (e.g. after
   answering). (Task 4 test of the hook's reducer.)
3. **Blocked preview item:** an item that fails layout is shown with its reasons, its Approve control is disabled, and a crafted
   approve answer is refused by the server with 409. (Task 2 tests + Task 9 journey.)
4. **Reload mid-session:** reloading while a question is open resumes the same session at the same question, without re-creating it.
   (Task 9 journey.)
5. **Double submit:** double-clicking "This whole document is right", "Apply" or an answer creates one session / one run / one answer
   (idempotency keys generated once per user action). (Task 9 journey.)

---

## File Structure

| File | Responsibility |
|---|---|
| `src/open_apprentice/drawio/render.py` (modify) | `Rendered.translate` |
| `src/open_apprentice/api/v2/service.py`, `routes.py` (modify) | page scene route, image offset, item renders, item checks, blocked-approve refusal, `GET /config` |
| `apps/web/src/v2/api.ts` | typed client for `/api/v2` (error envelope → `ApiError`) |
| `apps/web/src/v2/types.ts` | response types |
| `apps/web/src/v2/geometry.ts` | doc↔image↔display transforms, nudge steps, exact decimal formatting |
| `apps/web/src/v2/useSession.ts` | 2 s polling hook with stale-revision guard |
| `apps/web/src/v2/DocumentView.tsx` | PNG + label overlay, select/drag/keys/fields, draft render on drop |
| `apps/web/src/v2/ImportMap.tsx`, `Teach.tsx`, `Question.tsx`, `Reuse.tsx`, `Correct.tsx` | screens |
| `apps/web/src/v2/Apprentice.tsx` | step router, URL-hash resume, provenance badge, evidence panel |
| `apps/web/src/App.tsx` (modify) | "Apprentice" default; old tabs under "Earlier prototype" |
| `apps/web/src/styles.css` (modify) | v2 styles |
| `tests/unit/api_v2/test_screens_backend.py` | Tasks 1–2 backend tests |
| `tests/e2e/geometry.test.mjs` | pure transform and stale-revision tests, importing the `.ts` helpers with `node --experimental-strip-types` (Node ≥ 22.6) |
| `tests/e2e/journey.test.mjs` | real-browser journey |
| `package.json` (modify) | `test:e2e` runs both e2e files |

---

### Task 1: Scene geometry and image offset for overlays

**Files:** Modify `src/open_apprentice/drawio/render.py`, `src/open_apprentice/api/v2/service.py`, `src/open_apprentice/api/v2/routes.py`; Create `tests/unit/api_v2/test_screens_backend.py`

**Interfaces:**
- `Rendered` gains `translate: tuple[Fraction, Fraction] = (Fraction(0), Fraction(0))` (last field, default), parsed from the engine's `translate`. The PNG is a screenshot of the viewer's SVG at scale 1, so **image pixel = document coordinate + translate** (spike: `toDoc = svg − translate`).
- `_render_json` stores `translate`; `parse_render` reads it (absent → 0, for renders stored before this change).
- `GET /api/v2/documents/{doc_id}/pages/{page_id}/scene?mapping_hash=…` → `{scene_hash, canvas: {w, h}, image_offset: {x, y}, objects: [{id, kind, role, attached, x, y, w, h}], movable: [...]}` (numbers as exact strings).
- `POST …/draft` response gains `image_offset`.

- [ ] **Step 1: Failing tests** (`tests/unit/api_v2/test_screens_backend.py`):

```python
from tests.unit.api_v2.conftest import import_and_confirm


def test_scene_route_returns_geometry_and_image_offset(client, v2, doc_bytes):
    ref = import_and_confirm(client, v2, doc_bytes)
    r = client.get(f"/api/v2/documents/{ref['doc_id']}/pages/{ref['page_id']}/scene", params={"mapping_hash": ref["mapping_hash"]})
    assert r.status_code == 200
    s = r.json()
    assert s["canvas"] == {"w": "600", "h": "400"} and set(s["image_offset"]) == {"x", "y"}
    l1 = next(o for o in s["objects"] if o["id"] == "l1")
    assert (l1["kind"], l1["x"], l1["y"], l1["w"], l1["h"]) == ("label", "52", "103", "30", "14")
    assert sorted(s["movable"]) == ["l1", "l2"] and len(s["scene_hash"]) == 64


def test_parse_render_reads_translate_and_defaults_to_zero():
    from fractions import Fraction

    from open_apprentice.drawio.render import parse_render

    base = {"labels": {}, "nodes": {}}
    assert parse_render(base).translate == (0, 0)
    assert parse_render({**base, "translate": {"x": -32, "y": 12.5}}).translate == (Fraction(-32), Fraction(25, 2))
```

- [ ] **Step 2:** run → FAIL (404 / attribute missing). **Step 3:** implement (route reuses `page_scene`; `image_offset` = stored render's translate). **Step 4:** run `tests/unit/api_v2 tests/unit/drawio` → PASS. **Step 5:** commit `feat(api-v2): page scene geometry and image offset for overlays`.

---

### Task 2: Item renders, item checks, blocked approvals refused, config

**Files:** Modify `service.py`, `routes.py`; extend `tests/unit/api_v2/test_screens_backend.py`

**Interfaces:**
- `def _ref_for_scene(v, meta, scene_id) -> dict` — the document ref (`doc_id, page_id, mapping_hash`) behind a session scene id: from `meta["documents"]` for teaching sessions; for corrections from the run's documents (`meta["run_id"]`).
- `def item_outputs(req: dict) -> dict[str, tuple[str, dict]]` — every renderable item of an outstanding request: ChooseOutput alternatives `alt_id → (scene_id, output)`; ConfirmPreview items `item_id → (scene_id, output)`; ConfirmCorrectionScope consequences `f"{interp_id}:{k}" → (scene_id, output)`.
- `def item_checks(v, owner, sid, req) -> dict[str, dict]` — for each item: `{"ok": bool, "reasons": [str]}` from a **geometric layout check** on the session's scene (label boxes at the output positions must lie inside the page and not overlap any other object's box; touching allowed). Pure geometry, no render, so it is cheap on every poll.
- `session_state(...).outstanding` gains `checks` (above) and `item_ids` (ordered).
- `GET /api/v2/sessions/{sid}/requests/{request_id}/items/{item_id}.png` → PNG of that output (draft render on the item's document), cached at `sessions/{sid}/renders/{request_id}/{sha256(item_id)}.png`; 404 for unknown request/item; owner-checked.
- `submit_answer` refuses `approve` for an item whose check failed: 409 `BLOCKED_ITEM` "this document cannot be approved: <reasons>". The `approve_all_answer` convenience uses `reject` for blocked items.
- `GET /api/v2/config` → `{"live_available": bool, "model": "Live"|"Fixture", "max_upload_bytes": 2097152}` (no owner data).

- [ ] **Step 1: Failing tests** — append to `test_screens_backend.py`:

```python
from tests.unit.api_v2.conftest import answer_until_done, start_session
from tests.unit.drawio.fixtures import drawio, label, model, node


def test_item_pngs_and_checks_for_an_open_question(client, v2, two_docs_session):
    sid, s = two_docs_session
    q = s["outstanding"]
    assert q["item_ids"] and set(q["checks"]) == set(q["item_ids"])
    png = client.get(f"/api/v2/sessions/{sid}/requests/{q['request_id']}/items/{q['item_ids'][0]}.png")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert client.get(f"/api/v2/sessions/{sid}/requests/{q['request_id']}/items/nope.png").status_code == 404


def test_blocked_preview_item_cannot_be_approved(client, v2, doc_bytes):
    # the batch page is narrow: "right of the node, gap 12" pushes its label off the page
    narrow = drawio(model([node("m1", 300, 100, 120, 60), label("k1", 300, 180)], w=440, h=300))
    sid = start_session(client, v2, doc_bytes, narrow, key="narrow")
    s = client.get(f"/api/v2/sessions/{sid}").json()
    q = s["outstanding"]
    assert q and q["request"]["type"] == "ConfirmPreview", s
    blocked = [i for i, c in q["checks"].items() if not c["ok"]]
    assert blocked and "outside the page" in " ".join(q["checks"][blocked[0]]["reasons"])
    bad = {"request_id": q["request_id"], "intent_revision": q["intent_revision"], "kind": "items",
           "per_item": [[i, "approve"] for i in q["item_ids"]]}  # fmt: skip
    r = client.post(f"/api/v2/sessions/{sid}/responses", json=bad)
    assert r.status_code == 409 and r.json()["error"]["code"] == "BLOCKED_ITEM"
    assert dict(q["approve_all_answer"]["per_item"])[blocked[0]] == "reject"


def test_config_reports_live_availability(client):
    c = client.get("/api/v2/config").json()
    assert c == {"live_available": False, "model": "Fixture", "max_upload_bytes": 2 * 1024 * 1024}
```

If the narrow-page session commits without a preview or the preview shows no blocked item, adjust the page geometry (record the values in a ruling) — the test must exercise a genuinely blocked item.

- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** run `tests/unit/api_v2` → PASS (including Plan 4A tests: `answer_until_done` must still reach `committed` for the default fixtures). **Step 5:** commit `feat(api-v2): rendered question items, per-item layout checks, blocked approvals refused, config`.

---

### Task 3: Web client foundation — API client, types, geometry, transform tests

**Files:** Create `apps/web/src/v2/api.ts`, `types.ts`, `geometry.ts`, `tests/e2e/geometry.test.mjs`

**Interfaces:**
- `api.ts`: `export class ApiError extends Error { status: number; code: string }`; `export async function get<T>(path: string): Promise<T>`; `post<T>(path, body?)`; `upload<T>(path, file: File)`; base `/api/v2`. Error envelope `{error:{code,message}}` → `ApiError(message, status, code)`; network failure → `ApiError("The server is not reachable.", 0, "NETWORK")`.
- `geometry.ts` (no React, no DOM types beyond numbers):

```ts
export type Box = { x: number; y: number; w: number; h: number };
export type Frame = { offsetX: number; offsetY: number; scale: number }; // doc → displayed px: (x + offset) * scale
export const frameFor = (offset: { x: number; y: number }, naturalWidth: number, displayedWidth: number): Frame =>
  ({ offsetX: offset.x, offsetY: offset.y, scale: naturalWidth > 0 ? displayedWidth / naturalWidth : 1 });
export const toDisplay = (f: Frame, b: Box): Box => ({ x: (b.x + f.offsetX) * f.scale, y: (b.y + f.offsetY) * f.scale, w: b.w * f.scale, h: b.h * f.scale });
export const toDoc = (f: Frame, px: number, py: number): { x: number; y: number } => ({ x: px / f.scale - f.offsetX, y: py / f.scale - f.offsetY });
export const step = (e: { shiftKey: boolean; altKey: boolean }): number => (e.altKey ? 1 / 64 : e.shiftKey ? 10 : 1);
export const snap64 = (v: number): number => Math.round(v * 64) / 64;
export const fmt = (v: number): string => String(snap64(v)); // multiples of 1/64 print exactly in JS
export const parseNum = (s: string): number => (s.includes("/") ? Number(s.split("/")[0]) / Number(s.split("/")[1]) : Number(s));
```

  (`parseNum` accepts the server's exact strings like `"105/2"`; `fmt` sends decimals that are exact multiples of 1/64, which the server parses with `Fraction(str(v))` exactly.)
- `tests/e2e/geometry.test.mjs` imports the built helpers through a tiny esbuild-free path: copy the same functions into `apps/web/src/v2/geometry.ts` **and** export them as plain JS-compatible code; the test file uses `node --experimental-strip-types` to import `geometry.ts` directly (Node ≥ 22.6 supports type stripping; the repo's Node is 22/25). If type stripping is unavailable in CI's Node 22.x, record a ruling and test the transform inside the journey instead.

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { frameFor, toDisplay, toDoc, step, snap64, parseNum } from "../../apps/web/src/v2/geometry.ts";

test("doc → display → doc round trip at any displayed size", () => {
  for (const shown of [300, 640, 1024]) {
    const f = frameFor({ x: -32, y: 12 }, 640, shown);
    const d = toDisplay(f, { x: 100, y: 50, w: 30, h: 14 });
    const back = toDoc(f, d.x, d.y);
    assert.ok(Math.abs(back.x - 100) < 1e-9 && Math.abs(back.y - 50) < 1e-9);
  }
});

test("nudge steps and exact parsing", () => {
  assert.equal(step({ shiftKey: false, altKey: false }), 1);
  assert.equal(step({ shiftKey: true, altKey: false }), 10);
  assert.equal(step({ shiftKey: false, altKey: true }), 1 / 64);
  assert.equal(snap64(10.007), 10);
  assert.equal(parseNum("105/2"), 52.5);
});
```

- [ ] Steps: write the test → run `node --experimental-strip-types --test tests/e2e/geometry.test.mjs` → FAIL (module missing) → implement → PASS → `npm run lint` and `npm run build:web` pass → commit `feat(web): v2 API client, types and overlay geometry`.

---

### Task 4: Session polling hook with stale-revision guard

**Files:** Create `apps/web/src/v2/useSession.ts`; extend `tests/e2e/geometry.test.mjs`

**Interfaces:**
- `export function accept(prev: SessionState | null, next: SessionState): SessionState` — returns `next` unless `prev` exists for the same session with a **higher** `manifest_revision` (then `prev`). Pure; tested.
- `export function useSession(sid: string | null): { state: SessionState | null; error: string | null; refresh: () => void }` — polls `GET /sessions/{sid}` every 2000 ms while the state is not terminal (`committed`, `failed`, `cancelled`, `activated`, `activation_rejected`, `override`, `dismissed`); every response goes through `accept`; `refresh()` polls now (used after answering); aborts on unmount (AbortController) and when `sid` changes.

- [ ] Steps: add a test that `accept(stateRev5, stateRev4)` keeps rev 5 and `accept(stateRev4, stateRev5)` takes rev 5 → FAIL → implement → PASS → lint/build → commit `feat(web): session polling with stale-revision guard`.

---

### Task 5: DocumentView — preview image, overlay, drag, keys, fields, draft render

**Files:** Create `apps/web/src/v2/DocumentView.tsx`; modify `styles.css`

**Interfaces:**
- Props: `{ docId: string; pageId: string; mappingHash: string; editable: boolean; boxes?: Record<string, {x: number; y: number}>; onChange?: (boxes: Record<string, {x: number; y: number}>, seen: boolean) => void; title: string }`.
- Loads `GET …/scene` and the preview PNG; renders `<img alt={title}>` with an absolutely positioned overlay. Each movable label is a `<button aria-label={"label " + id}>` placed with `toDisplay(frameFor(offset, naturalWidth, displayedWidth), box)`; recomputed on image load and on `ResizeObserver` changes (Review Focus 1).
- Editable mode: pointer drag moves a marked ghost (dashed outline, "moved" text badge); on drop, and on each keyboard nudge (arrows with `step(e)`) after a 300 ms debounce, calls `POST …/draft` with all moved boxes; the returned PNG (data URL) and `image_offset` replace image **and** frame together; `onChange(boxes, seen=true)` fires only after that render is displayed (spec 8: a demonstration is recorded only after the user has seen the render). While a draft render is pending `seen=false`.
- Selected label shows a numeric x/y field pair (`<input aria-label="x of <id>">`, step 1/64) editing the same state.
- The safety line is rendered under the image.

- [ ] Steps: implement; `npm run lint` and `npm run build:web` pass; exercised by the journey (Task 9). Commit `feat(web): document view with draggable label overlay and draft renders`.

---

### Task 6: Import & map and Teach screens; App navigation

**Files:** Create `apps/web/src/v2/ImportMap.tsx`, `Teach.tsx`, `Apprentice.tsx`; modify `App.tsx`, `styles.css`, `tests/e2e/ui.test.mjs` (reach old tabs via "Earlier prototype")

**Interfaces / visible contract (the journey test relies on these names):**
- `App.tsx`: top tabs **"Apprentice"** (default, hash `#apprentice`) and **"Earlier prototype"** (renders the existing `MODES` nav and pages unchanged; old hashes `#learn` … `#svg` open it on that mode).
- `Apprentice.tsx`: steps `import → teach → question → result → reuse → correct`; the current session id lives in the hash (`#apprentice/s/<sid>`, runs `#apprentice/r/<run_id>`); on load with a session id it resumes there (Review Focus 4). Shows `Model: … · Teacher: …` for the session/run, and an **Evidence** `<details>` with the session's state, budgets, spend and result JSON.
- `ImportMap.tsx`: file input labelled **"Add .drawio files"** (multiple); per document a card with name, per-page status (refused pages show the reason), render status, the `DocumentView` (read-only), and a mapping table (label → node `<select>`, role `<input>`), button **"Confirm mapping"**. "Next: teach" is enabled when ≥ 2 documents are confirmed (NEED_BATCH explained in text).
- `Teach.tsx`: pick the document to demonstrate on (`<select aria-label="Document to edit">`), editable `DocumentView`, live checkbox **"Use the live model"** disabled unless `GET /config` says `live_available` (else the exact unavailable sentence plus a link to the prototype replay), button **"This whole document is right"** — disabled until every moved label's draft render has been seen; it generates one idempotency key per click-sequence (Review Focus 5) and posts `/sessions`.

- [ ] Steps: implement; update `ui.test.mjs` to click "Earlier prototype" before the old tabs; `npm run lint`, `npm run build:web`, `OA_E2E=1 node --test tests/e2e/ui.test.mjs` (unsandboxed) pass. Commit `feat(web): Apprentice tab with import, mapping and teaching; prototype tabs kept under Earlier prototype`.

---

### Task 7: Question screens — Clarify, Preview, Review revision

**Files:** Create `apps/web/src/v2/Question.tsx`

**Visible contract:**
- One component renders the outstanding request by type, each item image loaded from the item PNG route, with `alt` text naming the document and option:
  - `ChooseOutput`: 2–4 option cards (radio `name="alt"`, labels "Option A" …), plus **None**, **Not sure**, **Cancel**; button **"Submit answer"**.
  - `ConfirmPreview` (`purpose` affected_examples → heading "Affected examples"; revision_preview → "Revision preview"; teaching → "Preview"): per item radios **Approve** / **Reject** / **Not sure**; blocked items show "Blocked:" + reasons with an icon and Approve disabled (Review Focus 3); button **"Submit verdicts"**.
  - `ConfirmCorrectionScope`: one card per interpretation (revise: summary, selector in text, rendered consequences; override: "Keep this edit on this document only"; accidental: "That edit was a mistake"), plus **None** / **Not sure** / **Cancel**; button **"Submit answer"**.
- Submits once per click (button disabled while posting; the request id makes duplicates idempotent on the server), then calls `refresh()`.
- States `waiting_for_model` / `teaching` show "Working…" with the spend line; terminal states hand control back to `Apprentice`.

- [ ] Steps: implement; lint/build pass. Commit `feat(web): clarify, preview and revision-review screens with rendered items`.

---

### Task 8: Reuse & export and Correct screens

**Files:** Create `apps/web/src/v2/Reuse.tsx`, `Correct.tsx`

**Visible contract:**
- `Reuse.tsx` (after a commit, or for an activated skill): checklist of the owner's imported, confirmed documents (from local state), button **"Apply"** (one idempotency key per click-sequence), then per-document results: **Published** (download links **".drawio"**, **"SVG"**, **"Receipt"**; receipt summary with conformance / preservation / layout as three separate lines, never one score) or **Blocked** (reasons) / **Unchanged** / **Failed**; button **"Correct this document"** on each result.
- `Correct.tsx`: editable `DocumentView` on the run's input document starting from the run's output positions; moved labels form the mask (partial by default); checkbox **"Everything on this document is right (full approval)"**; button **"Submit correction"** → `POST /skills/{id}/corrections` with the current active version/generation from `GET /skills/{id}` → the session flows through `Question.tsx`; terminal states: activated ("Version N is now active"), override ("Kept as a one-document override; the skill is unchanged"), dismissed, failed (reason), activation_rejected (reason, with "reload the skill").

- [ ] Steps: implement; lint/build pass. Commit `feat(web): reuse with per-document receipts and downloads; corrections`.

---

### Task 9: Journey test in a real browser

**Files:** Create `tests/e2e/journey.test.mjs`; modify `package.json` (`"test:e2e": "OA_E2E=1 node --test tests/e2e/ui.test.mjs tests/e2e/journey.test.mjs"` and add `"test:geometry": "node --experimental-strip-types --test tests/e2e/geometry.test.mjs"`)

**The journey** (same server-spawn pattern as `ui.test.mjs`, own ports 8767/8768, `OA_STORE_DIR` in a temp folder, `DEMO_MODEL_ENABLED=0`; a `newPage` that records page errors and unexpected 4xx/5xx):
1. Open `/#apprentice`; add `d1.drawio` and `d2.drawio`; wait for renders; **Confirm mapping** on both.
2. Teach on d1: for each movable label, compute "centred below its node, gap 8" from `GET …/scene` (via `page.request`, which shares the cookie), enter it in the label's x/y fields; wait until every draft render is seen; click **"This whole document is right"** **twice quickly** — assert exactly one `POST /sessions` returned 202 with a new id (Review Focus 5) and the hash holds `#apprentice/s/<sid>`.
3. When a question shows, **reload** the page — assert the same question (same request id in the DOM `data-request-id`) is shown (Review Focus 4).
4. Answer through the preview (Approve all non-blocked; Submit) until "committed"; assert the provenance line reads `Model: Fixture · Teacher: You`.
5. Reuse: import `d3.drawio`, confirm it, tick d2 and d3, **Apply**; assert each result is Published with three separate check lines, or Blocked with reasons; download the `.drawio` of a published result and assert it starts with `<mxfile`.
6. Correct a published result: nudge one label with Alt+Down ×64 (= 1 unit) then Down (1 unit); **Submit correction**; answer through the scope question and reviews with the first offered choices; assert a terminal correction state is shown with its sentence.
7. Overlay alignment: at two window widths (1280, 800) assert each label button's centre lies inside the rendered label's bounding box measured from the image (Review Focus 1): compare against `GET …/scene` boxes transformed with the page's own frame — the test reads `img.naturalWidth`, `img.clientWidth` and the stored offset.
8. Live unavailable: assert the live checkbox is disabled and the exact sentence "Live inference is unavailable. Open the recorded example." is shown.
9. Cancel: start a second session and press **Cancel** on its first question → state "cancelled", no error.
10. Earlier prototype: open the tab and assert the old "Try it live" page renders.

- [ ] Steps: write the test; build web; run `OA_E2E=1 node --test tests/e2e/journey.test.mjs` (unsandboxed) → fix real defects until green (systematic debugging; never loosen an assertion without a ruling); run the full e2e and `test:geometry`. Commit `test(e2e): full teach → clarify → preview → reuse → correct journey in a real browser`.

---

### Task 10: Docs and audit

- [ ] Update `docs/implementation_audit.md` (section 8 screens rows, the preview-blocked row now implemented, journey test evidence), README "How to use" section for the Apprentice tab (only what exists), `docs/demo_script.md` steps if that file exists. Run all CI steps (ruff, black, lint-imports with `PYTHONPATH=src`, `npm run lint`, full pytest with engine tests, `npm test`, `npm run build:web && npm run test:e2e`). Commit `docs: audit and usage for the Apprentice screens`.

---

## Final verification

- Full pytest on 3.13 and 3.12 with `OA_ENGINE_TESTS=1`; `npm test`; `npm run lint`; `npm run build:web && npm run test:e2e`; `npm run test:geometry`.
- Demo image builds; the container serves the built web app with the Apprentice tab and completes a manual upload → render.
