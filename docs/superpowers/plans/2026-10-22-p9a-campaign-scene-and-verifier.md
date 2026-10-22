# Plan 9A: Campaign scene, fit observation, fixtures and independent verifier

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Konva engine can load, render and measure an editable promo banner and story card (text, image, shape, artboard nodes), and an independent Python verifier can judge a story-card result against authored gold outputs and the spec's invariants.

**Architecture:** The engine gains new node types and one read-only tool, `observe_fit`, that reports wrapped-text and layout violations from the real renderer with the vendored font. A new agent-side package `open_apprentice.campaign` holds limits, role validation and the public development fixtures. Gold outputs and the verifier live on the evaluator side (`open_apprentice.evaluation`) and measure text themselves from the font files with `fonttools`, never with engine code.

**Tech Stack:** Konva 9 in the locked Playwright page (`services/engine`), Node `node:test`, Python 3.12, pytest, `fonttools` (new), import-linter.

**Spec:** `docs/superpowers/specs/2026-10-22-promo-story-card-design.md` (sections 5, 6, 7.1, 7.2, 7.7, 7.8 are what this plan builds).

**This is plan 1 of 4 for the spec.** 9B: tools, procedures, rule language, learner, overflow question, preference. 9C: Campaign UI tab. 9D: Fabric contract and parity, then the private sealed set. Each is written after the previous one lands.

## Global Constraints

- Story artboard is exactly 1080×1920; safe insets top 220, bottom 220, left 72, right 72 (frozen here per spec §10).
- Minimums: body text fontSize ≥ 40, legal fontSize ≥ 24, CTA height ≥ 96, hero (product_image) width ≥ 432. Frozen here.
- Roles: `background, brand_mark, product_image, headline, price, cta, legal`. Exactly one of each per artboard that holds it; children of a role-bearing group carry no role.
- Never writable by any later edit: `text`, `fontFamily`, `fontStyle`, `fill` of text, `asset`, `crop`, `link`. Writable: `x, y, width, height, scaleX, scaleY, parent, z, fontSize, cornerRadius`.
- Exact copy means byte-equal Python `str` comparison; no Unicode normalization, no trimming.
- Fonts: only the vendored Liberation Sans 2.1.5 files listed in `services/engine/vendor/MANIFEST.json`; scene font family name `Liberation Sans`.
- Agent-visible packages (`open_apprentice.campaign` included) must never import `open_apprentice.evaluation`; gold JSON lives only under `src/open_apprentice/evaluation/campaign_gold/`.
- No eval/exec. Python 3.12. Black. Conventional commits. Commit with explicit paths: the working tree has unrelated uncommitted `repaired_by` changes that must not ride along.
- Engine and engine-backed Python tests need Chromium and a local port; they cannot run in the agent sandbox. When blocked, say so and ask the owner to run them with `!`; never report them as passing unrun.

## Review Focus

1. A single word wider than its text frame (German compounds): Konva silently breaks it mid-word; the engine and verifier must both report overflow instead.
2. Measuring before the font has loaded: widths come from a fallback font and every fit verdict is wrong; the engine must await the vendored font before `load` returns.
3. Konva drops lines that exceed a fixed text height, so reading `textArr` on the real node hides overflow; measurement must use an unbounded clone.
4. Copy that differs only by Unicode form (NFC `ü` vs NFD `u`+combining) or trailing space must fail the exact-copy check, not pass.
5. A scene naming an unknown asset id must fail to load with `INVALID_SCENE`, not render a blank image that then "fits".

Each is pinned by a test in the owning task below.

---

### Task 1: Vendored campaign assets and fonts in engine sessions

**Files:**
- Create: `services/engine/vendor/assets/h7-headphones.svg`, `services/engine/vendor/assets/halden-wordmark.svg`
- Modify: `services/engine/vendor/MANIFEST.json` (two entries, each with `sha256`, `bytes`, `source: "authored in-repo for Open Apprentice, 2026-10-22"`, `licence: "project"`, `width`, `height`)
- Modify: `services/engine/src/drawio.js` (export `FONT_CSS`, add family `"Liberation Sans"` to its family list; export `read`)
- Modify: `services/engine/src/engine.js` (`create`: add `FONT_CSS` style tag, await `document.fonts.load` for regular and bold `"Liberation Sans"`, pass an asset map `{id: {data_url, width, height}}` into `window.__engine.load`)
- Test: `services/engine/test/vendor.test.js`, `services/engine/test/campaign.test.js` (new)

**Interfaces:**
- Produces: `window.__engine.load(scene, privateConfig, assets)` is now `async`; `assets` maps asset id to `{data_url, width, height}`. Asset ids: `h7-headphones` (1000×1000, the product), `halden-wordmark` (480×120, the logo). Both are simple authored SVGs (headphones glyph; "HALDEN" wordmark as outlined paths, no `<text>`, no scripts).

- [ ] **Step 1: Write failing tests.** In `vendor.test.js`: both new files' sha256 and bytes match MANIFEST. In `campaign.test.js` (same harness style as `engine.test.js`): `test("session pages measure with the vendored font")` creates a session with a one-text scene and asserts the canvas width of `"Silence the city."` at `72px bold "Liberation Sans"` measured inside the session page equals `eng.textWidthForTest`-style measurement at the same font (add an optional `weight` param to `textWidthForTest`) within 0.01 px.
- [ ] **Step 2: Run** `npm test -w services/engine` and confirm the new tests fail (missing files / no font).
- [ ] **Step 3: Author the two SVGs, add MANIFEST entries, export `FONT_CSS`/`read`, update `create`.** Assets are read through `read()` so their hashes are checked at startup.
- [ ] **Step 4: Run** `npm test -w services/engine`; all engine tests pass (existing ones included).
- [ ] **Step 5: Commit** `feat(engine): vendored campaign assets and Liberation Sans in session pages`.

### Task 2: Text, image, shape and artboard nodes in Konva

**Files:**
- Modify: `services/engine/src/dispatcher.browser.js` (`build`, `kind`, `publicProps`, `nativeState`)
- Test: `services/engine/test/campaign.test.js`

**Interfaces:**
- Consumes: Task 1 asset map.
- Produces, scene node schema (input) and `nativeState` node schema (output), identical field names:
  - all: `id, type, parent, role, x, y, width, height, scaleX, scaleY, rotation, z` (`z` = `zIndex()` within parent);
  - `artboard`: Konva `Group` with attrs `oaType:"artboard"`, `format` (`"16:9"|"9:16"`), `safe` `{top,right,bottom,left}`, `sequence` (int); `width/height` stored as attrs; children clipped to its bounds;
  - `rect` (existing) and `shape` (Konva `Rect` with `cornerRadius`; used for the CTA plate): `fill, stroke, strokeWidth, cornerRadius`;
  - `text`: Konva `Text` with `text, fontFamily, fontSize, fontStyle ("normal"|"bold"), lineHeight, align, wrap:"word", fill`; `width/height` are the frame;
  - `image`: Konva `Image` with `asset, crop` (`null` = full frame), `focal` `{x,y}` in asset pixels;
  - `group` (existing) gains `role` and `link` attrs (the CTA is a `group` with role `cta`, `link`, holding one `shape` and one `text`).
  - `role`, `link`, `asset`, `focal`, `format`, `safe`, `sequence`, `oaType` are stored with `node.setAttr` and echoed by `nativeState`.
- `kind(n)` returns `n.getAttr("oaType") ?? ("group"|"rect"|"text"|"image")` from the class name; existing tools that check `kind === "rect"` keep their behaviour.

- [ ] **Step 1: Write failing tests** in `campaign.test.js`:
  - `test("story scene round-trips through nativeState")`: load `teach_after` (copy it from Task 4's fixture once that exists; until then an inline 1080×1920 artboard with one node of each type) and assert every input field above comes back unchanged in `eng.nativeState`.
  - `test("unknown asset id fails INVALID_SCENE")`: `asset: "nope"` → `eng.create` rejects with `code === "INVALID_SCENE"` (Review Focus 5).
  - `test("image keeps no crop and its aspect")`: image node 720×720 of `h7-headphones` → `nativeState` `crop === null`, width/height 720.
- [ ] **Step 2: Run** `npm test -w services/engine`; new tests fail.
- [ ] **Step 3: Implement** the node builders in `build`, making `load` await image decoding (`new Image()` from `data_url`, `await img.decode()`), and extend `publicProps`/`nativeState`.
- [ ] **Step 4: Run** `npm test -w services/engine`; all pass, including `engine.test.js` and `fabric.test.js` unchanged.
- [ ] **Step 5: Commit** `feat(engine): text, image, shape and artboard nodes for campaign scenes`.

### Task 3: `observe_fit` read-only tool

**Files:**
- Modify: `services/engine/src/dispatcher.browser.js` (new tool in `TOOLS`, not in `MUTATING`)
- Modify: `services/engine/src/engine.js` (`PUBLIC_TOOL_SCHEMAS.konva.tools` gains `observe_fit: ["artboard_id", "limits"]`; Fabric schema unchanged, so its hash is unchanged; update any test that pins the Konva hash)
- Test: `services/engine/test/campaign.test.js`

**Interfaces:**
- Produces: `observe_fit({artboard_id, limits}) -> {fits: bool, text: [{id, lines: [string], line_widths: [number], text_height: number, frame_width, frame_height}], violations: [{kind, node_id, detail}]}`.
  - `limits` = `{safe:{top,right,bottom,left}, min_font, min_legal_font, min_cta_height, min_hero_width}` (values from Global Constraints; passed in, not hard-coded in JS).
  - Violation kinds, exactly: `text_overflow` (text_height > frame_height), `word_too_wide` (any single word wider than frame_width), `outside_safe` (node world bounds outside the artboard's safe rect; `background` exempt), `below_minimum` (font, legal font, CTA height or hero width under its limit), `overlap` (two content nodes' bounds intersect with positive area; `background` and nodes inside the same CTA group exempt).
  - Text is measured on an off-stage clone with `height: "auto"` (Review Focus 3); `word_too_wide` uses `measureText` per word (Review Focus 1).

- [ ] **Step 1: Write failing tests:**
  - `test("short English copy fits the taught layout")`: `teach_after` → `fits === true`, `violations` empty, headline `lines.length === 1`.
  - `test("fixed-height frame does not hide overflow")`: headline frame height 80 with three lines of text → `text_overflow` reported and `lines.length === 3`.
  - `test("over-wide German compound is reported, not broken")`: frame width 300, text `"Geräuschunterdrückungstechnologie"` at 72px → `word_too_wide`.
  - `test("observe_fit does not mutate")`: revision unchanged after the call.
  - `test("node outside safe area and overlapping nodes are reported")`: brand mark at y 100 → `outside_safe`; price frame overlapping headline frame → `overlap`.
- [ ] **Step 2: Run** `npm test -w services/engine`; new tests fail.
- [ ] **Step 3: Implement `observe_fit`.**
- [ ] **Step 4: Run** `npm test -w services/engine`; all pass.
- [ ] **Step 5: Commit** `feat(engine): observe_fit reports measured text and layout violations`.

### Task 4: `open_apprentice.campaign`: limits, role validation, development fixtures

**Files:**
- Create: `src/open_apprentice/campaign/__init__.py`, `limits.py`, `scene.py`, `fixtures/*.json`, `fixtures.py`
- Modify: `pyproject.toml` (add `open_apprentice.campaign` to the "New learning-core packages never import the evaluator" contract's `source_modules`)
- Test: `tests/unit/campaign/test_scene.py`, `tests/unit/campaign/test_fixtures.py`

**Interfaces:**
- Produces:
  - `limits.py`: `STORY_W = 1080`, `STORY_H = 1920`, `SAFE = {"top": 220, "right": 72, "bottom": 220, "left": 72}`, `MIN_FONT = 40`, `MIN_LEGAL_FONT = 24`, `MIN_CTA_H = 96`, `MIN_HERO_W = 432`, `ROLES: tuple[str, ...]`, `def fit_limits() -> dict` (the `observe_fit` `limits` argument).
  - `scene.py`: `class RoleError(Exception)` with `.problems: list[str]`; `def role_map(scene: dict, artboard_id: str) -> dict[str, str]` (role → node id; raises `RoleError` listing every missing and every duplicated role).
  - `fixtures.py`: `FIXTURE_IDS: tuple[str, ...]`; `def load_fixture(fid: str) -> dict` (returns a fresh deep copy).
- Fixture ids and content (all copy below is exact; fonts `Liberation Sans`; CTA link `https://halden.example/h7-sale`, `/de/h7-angebot` for German, `/fr/h7-offre` for French):
  - `teach_before`: 1600×900 artboard `16:9`, product left, offer right. Headline `Silence the city.`, price `Now $179 (was $249)`, CTA label `Shop now`, legal `Offer ends 31 Oct 2026. While stocks last. Terms apply.`
  - `teach_after`: the taught story (1080×1920, `9:16`, sequence 1), same copy, layout exactly:

    | role | x | y | w | h | other |
    |---|---|---|---|---|---|
    | background | 0 | 0 | 1080 | 1920 | |
    | brand_mark (image `halden-wordmark`) | 72 | 220 | 240 | 60 | |
    | product_image (`h7-headphones`) | 180 | 320 | 720 | 720 | |
    | headline (bold 72, lineHeight 1.1) | 72 | 1080 | 936 | 160 | |
    | price (bold 56, lineHeight 1.1) | 72 | 1256 | 936 | 72 | |
    | cta group | 72 | 1360 | 936 | 112 | shape cornerRadius 16; label bold 44 centred |
    | legal (normal 24, lineHeight 1.3) | 72 | 1540 | 936 | 160 | |
  - `short_a` (1280×720) and `short_b` (1920×1080): different node ids, different English copy (`Hear only what matters.` / `Now $159 (was $229)`; `Your commute, muted.` / `Now $199 (was $279)`), same CTA label and legal.
  - `de_long_a`: headline `Bring die Stadt endlich zum Schweigen – mit aktiver Geräuschunterdrückung.`, price `Jetzt 179 € (statt 249 €)`, CTA `Jetzt kaufen`, legal `Angebot gültig bis 31.10.2026, solange der Vorrat reicht. Es gelten die AGB der Halden Audio GmbH. Abbildung ähnlich.`
  - `de_long_b`: as `de_long_a` but legal `Angebot gültig bis 31.10.2026 und nur, solange der Vorrat reicht. Es gelten die Allgemeinen Geschäftsbedingungen der Halden Audio GmbH, Musterstraße 1, 10115 Berlin. Unverbindliche Preisempfehlung des Herstellers. Alle Preise inklusive gesetzlicher Mehrwertsteuer. Abbildung ähnlich, Farbabweichungen möglich.`
  - `fr_long`: headline `Faites taire la ville grâce à la réduction de bruit active nouvelle génération.`, price `179 € au lieu de 249 €`, CTA `Acheter`, legal `Offre valable jusqu'au 31/10/2026 dans la limite des stocks disponibles. Voir conditions générales.`
  - `missing_role` (`short_a` without `price` role), `duplicate_role` (`short_a` with two `headline` roles).
  - Every fixture carries `"locale"` (`en|de|fr`) and `"provenance": "authored in-repo, development fixture, not held out"`.

- [ ] **Step 1: Write failing tests:** `role_map(load_fixture("teach_after"), "story-1")` returns all seven roles; `missing_role` raises `RoleError` whose `problems` names `price`; `duplicate_role` names `headline` twice-claimed; every fixture's text nodes use only `Liberation Sans`; `load_fixture` returns independent copies (mutating one does not change the next load).
- [ ] **Step 2: Run** `uv run pytest tests/unit/campaign -q`; fail (module missing).
- [ ] **Step 3: Implement** the package and author the fixtures.
- [ ] **Step 4: Run** `uv run pytest tests/unit/campaign -q` and `PYTHONPATH=src uv run lint-imports`; both pass.
- [ ] **Step 5: Commit** `feat(campaign): limits, role validation and development fixtures`.

### Task 5: Gold outputs (evaluator side)

**Files:**
- Create: `src/open_apprentice/evaluation/campaign_gold/*.json`, `src/open_apprentice/evaluation/campaign_gold.py`
- Modify: `pyproject.toml` (add `open_apprentice.evaluation.campaign_gold` and `open_apprentice.evaluation.campaign_verifier` to the first contract's `forbidden_modules`)
- Test: `tests/unit/evaluation/test_campaign_gold.py`

**Interfaces:**
- Produces: `def load_gold(fixture_id: str, outcome: str) -> dict | None` (`None` when the outcome is not applicable); `GOLD_KEYS: tuple[tuple[str, str], ...]`.
- Outcomes and authored layouts (artboard-local coordinates; copy, fonts, links identical to the fixture):
  - `layout` for `short_a`, `short_b`: the `teach_after` table with the fixture's own ids and copy.
  - `shrink` for `de_long_a`: as the table except product_image `324, 320, 432, 432`, headline `72, 792, 936, 448`.
  - `shrink` for `de_long_b`: `None` (shrinking the hero frees space only for the headline, so the overflowing legal line still does not fit; outcome A "does not fit").
  - `split` for `de_long_a`, `de_long_b`, `fr_long`: two artboards, `story-1` (sequence 1) and `story-2` (sequence 2), each 1080×1920 with its own background. Card 1: brand_mark `72,220,240,60`, product_image `180,320,720,720`, headline `72,1080,936,620`. Card 2: brand_mark `72,220,240,60`, price `72,800,936,72`, cta `72,904,936,112`, legal `72,1380,936,320`. The brand mark is the only node on both cards (ids `<id>` and `<id>-2`).
  - `shrink` for `fr_long`: authored like `de_long_a` (the French copy is chosen to fit after shrinking).
- **Expected fit verdicts** (these define the fixtures; measured with Task 6's `text_layout.fit`, which must agree with the engine):

  | fixture | base story layout | shrink layout | split layout |
  |---|---|---|---|
  | short_a, short_b | fits | n/a | n/a |
  | de_long_a, fr_long | headline overflows | fits | fits |
  | de_long_b | legal overflows | legal still overflows | fits |

  If `de_long_b`'s legal copy measures at 5 lines or fewer at 24px in 936px, append whole sentences of plausible German legal text until it needs at least 6 lines (overflowing the 160px frame) while staying within 10 lines (fitting the split card's 320px frame). Record the final copy in Task 4's fixture. Copy for every other fixture is fixed as given.

- [ ] **Step 1: Write failing tests:** every `GOLD_KEYS` entry loads; `load_gold("de_long_b", "shrink") is None`; each gold scene's copy strings equal its fixture's; split golds have exactly two artboards with sequences 1 and 2; every row of the expected-verdicts table holds when computed with `text_layout.fit` (this test lives in `test_campaign_gold.py` but is added in Task 6, once `fit` exists).
- [ ] **Step 2: Run** `uv run pytest tests/unit/evaluation/test_campaign_gold.py -q`; fail.
- [ ] **Step 3: Author the gold JSON and the loader.**
- [ ] **Step 4: Run** the test and `PYTHONPATH=src uv run lint-imports`; pass.
- [ ] **Step 5: Commit** `feat(evaluation): authored gold outputs for campaign development fixtures`.

### Task 6: Independent text layout in Python

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (`uv add "fonttools>=4.54,<5"`)
- Create: `src/open_apprentice/evaluation/text_layout.py`
- Test: `tests/unit/evaluation/test_text_layout.py`, `tests/integration/test_campaign_text_crosscheck.py`

**Interfaces:**
- Produces: `def advance_width(text: str, font_size: float, bold: bool) -> float` (sum of `hmtx` advances × size / unitsPerEm, no kerning); `def wrap(text: str, width: float, font_size: float, bold: bool) -> list[str]` (greedy on single spaces, same rule as Konva `wrap:"word"`); `@dataclass Fit(lines: list[str], height: float, word_too_wide: bool)`; `def fit(text, width, font_size, bold, line_height) -> Fit`.
- Reads the TTFs from `services/engine/vendor/fonts/` resolved from the repo root, verifying sha256 against MANIFEST. It must not import anything from `services/` or call the engine.

- [ ] **Step 1: Write failing tests:** unit: `wrap("Silence the city.", 936, 72, True) == ["Silence the city."]`; the German compound at width 300 sets `word_too_wide`; `fit(...).height == len(lines) * font_size * line_height`; a tampered font hash raises. Integration (`engine_url`): for every text node in every fixture and gold scene, the engine's `observe_fit` line count equals `fit(...)` line count; any mismatch is printed with both line lists so fixture copy can be adjusted away from wrap boundaries.
- [ ] **Step 2: Run** unit tests; fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** unit tests (pass); ask the owner to run the integration test unsandboxed: `! OA_ENGINE_TESTS=1 PYTHONPATH=src:. $TMPDIR/venv312/bin/python -m pytest -q tests/integration/test_campaign_text_crosscheck.py`.
- [ ] **Step 5: Commit** `feat(evaluation): independent font-table text layout for the campaign verifier`.

### Task 7: Campaign verifier

**Files:**
- Create: `src/open_apprentice/evaluation/campaign_verifier.py`
- Test: `tests/unit/evaluation/test_campaign_verifier.py`, `tests/integration/test_campaign_verifier_engine.py`

**Interfaces:**
- Consumes: `campaign.limits`, `campaign.scene.role_map`, `campaign_gold.load_gold`, `text_layout.fit`, existing `verifier.Check`/`VerifierReport`.
- Produces: `GOLD_TOL_PX = 2.0`; `def verify_story(source: dict, final_native: dict, gold: dict | None) -> VerifierReport`. Checks, one `Check` each, named exactly: `exact_copy`, `copy_once`, `link_preserved`, `logo_preserved`, `image_aspect`, `image_uncropped`, `focal_visible`, `role_order`, `card_sequence`, `inside_safe`, `minimum_sizes`, `text_fits`, `no_overlap`, `non_writable_unchanged`, `matches_gold`. `matches_gold` fails when `gold is None` and the result was committed. `text_fits` uses only `text_layout.fit`.
- Must not import `open_apprentice.environments`, `services/*`, or call `measure_node`/`observe_fit`.

- [ ] **Step 1: Write failing tests.** Unit, starting from each gold scene as a perfect result: all checks pass. Then one mutation per check, each failing exactly its named check: headline text NFD-normalised (Review Focus 4) → `exact_copy`; headline gets a trailing space → `exact_copy`; price duplicated onto card 2 → `copy_once`; link changed → `link_preserved`; image 720×700 → `image_aspect`; image `crop` set → `image_uncropped`; legal moved above CTA → `role_order`; sequences 1,1 → `card_sequence`; brand mark y 100 → `inside_safe`; legal fontSize 20 → `minimum_sizes`; headline frame height 80 → `text_fits`; price overlapping CTA → `no_overlap`; headline `fill` changed → `non_writable_unchanged`; headline y +5 px → `matches_gold`.
  Disagreement case: a result where the engine's `observe_fit` (recorded JSON captured once from the engine and stored as a test fixture) says `fits: true` but the frame is 1 px shorter than the verifier's computed height → `text_fits` fails.
  Integration (`engine_url`): load each gold scene into Konva via `EvaluatorHarness.open_session`, take `native`, and `verify_story(fixture, native, gold)` passes every check.
- [ ] **Step 2: Run** unit tests; fail.
- [ ] **Step 3: Implement** `verify_story`.
- [ ] **Step 4: Run** unit tests (pass), `PYTHONPATH=src uv run lint-imports` (pass); ask the owner to run the integration test unsandboxed as in Task 6.
- [ ] **Step 5: Commit** `feat(evaluation): independent campaign story verifier`.

### Task 8: Records and full check

**Files:**
- Modify: `docs/status.md`, `docs/decisions.md` (new numbered decision: campaign lane limits and tolerances frozen; symbolic axis not used in this lane; fonttools added)

- [ ] **Step 1: Run the full suite on 3.12:** `UV_PROJECT_ENVIRONMENT=$TMPDIR/venv312 uv sync --frozen --python 3.12`, then `PYTHONPATH=src:. $TMPDIR/venv312/bin/python -m pytest -q tests`, `PYTHONPATH=src uv run lint-imports`, `uv run black --check src tests`. Engine-backed and Node tests: owner runs `! npm test -w services/engine` and `! OA_ENGINE_TESTS=1 PYTHONPATH=src:. $TMPDIR/venv312/bin/python -m pytest -q tests`. Report exact counts, and which runs were the owner's.
- [ ] **Step 2: Update** `docs/status.md` (what works, what was tested, by whom) and add the decision entry.
- [ ] **Step 3: Commit** `docs: plan 9A status and decisions`.
