# Open Apprentice — "Legendary demo" upgrade (product + 3-min video)

## Context
Owner watched the first narrated demo: robotic `say` voice, long silent waits, a plain grey UI full of raw cell ids
(`SWpWR8r…-10`), toy flowcharts, and a live Nemotron take that ran 11 min and failed (completion-cap truncation, $0.68).
Judges see only a ~3-min video, so impression decides everything. Goal: an engaging, colourful product and a
motion-graphics video that shows real, successful runs — without weakening the honest evaluation (README keeps the
22/48 vs 28/48 result; four evidence axes stay separate; no fabricated output).

Owner decisions: combine three concepts — (1) **Watch it think**: Nemotron's candidate rules as ghost overlays, count
collapsing N → question → 1, the generated probe diagram; (2) **Teach once, fix 100**: a wall of ~100 colourful
NVIDIA-style diagrams fixing themselves with per-document checks; (3) **One apprentice across worlds**: the earlier
prototype's badge-on-UI-card transfer across Konva/Fabric/SVG, labelled "same approach, different skill". Video via
**Remotion**; voice via **Kokoro-82M** (open source); improve live success/speed *before* recording; video shows only
genuine successful live takes (all takes logged).

Deadline 2026-10-31 01:00 SGT (12 days). Spec + plan docs are written into the repo on approval
(`docs/superpowers/specs/2026-10-19-legendary-demo-design.md`, `docs/superpowers/plans/2026-10-19-legendary-demo.md`).

## Phase A — Backend (small, text-blind learner preserved)
1. **Display names and colours** — new `plain_text(value)` in `src/open_apprentice/drawio/parse.py` (reuse the
   `_LabelHtml` HTMLParser pattern, parse.py:79); add `display: {cell_id: {text, fill, stroke, font_color}}` to
   `get_document` (service.py ~160) and `page_scene_view` (service.py ~1030). **Never** into `sc.scene`/`SceneRegistered`
   (keeps scene hashes stable and the learner text-blind). Tests: `tests/unit/api_v2/test_display.py` (HTML stripped,
   scene_hash unchanged, no text in scene payload).
2. **Thinking trace** — pure `thinking_trace(evs)` in `src/open_apprentice/teaching/step.py`, re-deriving
   rounds/survivors/probes/questions from existing events (`ModelProposalReturned.candidates`, `ActionIssued.round_kind`,
   `SceneRegistered role=probe`, `ProbeRendered`, `RequestIssued` ChooseOutput alternatives, `ResponseRecorded`) using
   `candidate_pool`, `_filter`, `_groups`; expose `thinking` + `scene_refs` in `session_state` (service.py:497), cached
   by head event id. Fixture candidates labelled "offline enumerator", never "model". Tests: replay determinism, survivor
   counts match step decisions, every group key maps to an alternative.
3. **After-image** — capture the PNG `publish` already renders in `_apply_one` (service.py:766); store
   `runs/{run}/{doc}-{page}.png`; `export?format=png`. Test: only for `published`.
4. **Batch** — no new endpoint: client imports in a loop, "Confirm all proposed mappings" (one confirm per doc), apply in
   chunks of 25 (parallel `apply_version` calls) to stay inside the Cloud Tasks deadline. Measure timing on staging.

## Phase B — Live reliability and speed (pre-registered, disclosed)
1. Add `elapsed_s` to `usage` in `providers/teaching_adapter._call` (diagnostic).
2. **Product policy "product-1"**: `StepConfig(probes=True, tolerate_truncation=True)` in `advance()` (service.py:419),
   product-only `NEBIUS_COMPLETION_CAP=16000`; provenance line gains `· Policy: product-1` (unanchored e2e regex still
   passes); session meta records policy. Evaluated rows untouched.
3. **Model check**: pre-register in `docs/evaluation/product_model_check.md` *before* running — adopt Nemotron-3-Super
   for the live product only if, on the same 8 dev learning episodes, success ≥ Ultra-A, ≤ 1 wrong commit, and median
   time-to-first-question ≤ 90 s; else keep Ultra + product-1. Run via `oa eval manifest … --ceiling-usd` + owner
   approval file + `oa eval run --split dev --mode live` (≈ $0.4 Super, ≈ $1.4 Ultra; caffeinate).
4. **Demo scenario design**: a rule family the model handles well (labels below nodes; warnings right) with a designed
   ambiguity (centred-below vs left-aligned-below, distinguishable only on a wide node) so a probe/question appears.
   Rehearse offline (free), then live takes; every take recorded in `docs/demo_takes.md` (failures included).
5. Disclose in README: product model/policy differ from evaluated A; takes were selected; published final rows stand.

## Phase C — UI/UX redesign (`apps/web/src/v2`, `apps/web/src/styles.css`)
- Dark NVIDIA-esque theme at token level (`:root`): near-black surfaces, `#76b900` accent, cyan/amber/magenta for
  alternatives A/B/C; vendored Inter woff2 (OFL) under `apps/web/public/fonts/` (CSP `default-src 'self'` stays —
  no Google Fonts). Smooth transitions, focus styles kept.
- Canvas-first layout with a 5-step stepper rail (Import → Map → Teach → Think → Reuse); existing sections/ids/buttons
  wrapped and restyled, never renamed.
- `ImportMap.tsx`: readable names + colour swatch instead of ids (id as secondary text; aria-labels unchanged).
- `DocumentView.tsx`: label chips show text, dashed ghost of original position, animated moves (keep
  `.docview-stage`, `button[data-label]`, `[data-pending]`, `x of <id>`/`y of <id>`).
- New `Thinking.tsx` beside `Question.tsx`: big animated counter (N → K → ? → 1), candidate chips, probe card
  ("generated test diagram from Training workflow"), ghost overlays A/B/C as SVG over the probe preview.
- `Reuse.tsx` → **wall**: grid of `article.result[data-result]` tiles (thumbnail, Published/Blocked glow, `.checks li`
  ×3, `.err`), progress "37/100 checked", headline "Published 93 · Blocked 7" (no combined badge); tile click opens a
  before/after slider (`preview.png` vs after-image).
- **UI merge (owner: "whatever impresses most without jeopardising anything")** — merge at the *shell*, not the code:
  one branded Open Apprentice home (hero line, live-model status pill, "Try it in 30 s" CTA) with two world tiles —
  **Diagrams** (new draw.io flow, default) and **UI components** (the prototype: Konva · Fabric · SVG badge transfer,
  labelled "same teach-ask-check approach, different skill and learner"). Shared header, theme tokens, fonts and
  navigation; the prototype's internals, routes (`#live`, `#svg`, …) and the tab names `ui.test.mjs` asserts stay
  untouched (the shell renames the outer tab label only if no test asserts it; "Earlier prototype" tab stays reachable).
  Why not a deeper merge: the two learners differ, unifying them would cost days, risk both test suites, and blur the
  honesty line between evaluated and prototype work.
- Guard: every selector the e2e suites use (listed in exploration notes) must survive; add a selector-presence test.

## Phase D — Diagram library (owner-authored, provenance-checked)
- `scripts/corpus/generate_library.py` (seed 20261019): ~100 varied colourful diagrams from templates — DGX SuperPOD,
  GPU cluster + InfiniBand, AI-factory pipeline, k8s namespaces, data lakehouse, inference serving. Within classifier
  limits: no `fontFamily`, ≤ 32 objects, ≤ 16 single-line top-level `text` labels, no images/`data:`/`http`, no zone
  rectangles behind labels; labels deliberately misplaced but nearest their node.
- Output `apps/web/public/samples/library/*.drawio` + `index.json`; `docs/corpus/library_provenance.md` (generator,
  seed, SHA-256 table, owner approval). Kept apart from `tests/fixtures/drawio_corpus` and `benchmarks/`.
- Tests: `tests/unit/test_library.py` (every file passes `load_drawio` + `classify`), engine test renders a subset with no
  demotions, extended exclusion test (hash list, no `image=`/`data:`/`http`).
- Add 3 hero samples to `SAMPLES` in `ImportMap.tsx` (keep existing three; tests use them).

## Phase E — Video (Remotion + Kokoro + generated music)
- `video/` workspace with its own `package.json` (not a root workspace), pinned `remotion@4.0.536` + matching `@remotion/*`
  (licence: free for individuals/≤3-person companies — verify on install).
- `video/script.json`: beats {id, scene, text, onScreen, minSec}; ~410 words for 3:00.
- `video/tools/tts.py`: Kokoro `kokoro==0.9.4` (Apache-2.0) under `uv run --python 3.12`, voice `af_heart` (alt
  `af_bella`), per-word timestamps → karaoke captions; needs `brew install espeak-ng` (will ask/confirm at run time).
- `video/tools/music.py`: procedurally generated licence-free ambient bed (numpy), ducked under speech in Remotion.
- `video/capture/capture.mjs`: Playwright + CDP `Page.startScreencast` PNG frames at 1920×1080 (2× for zoom scenes),
  injected green cursor dot, smooth scroll, recorded zoom targets; reuse helpers from `scripts/record_demo.mjs`;
  frames → H.264 via imageio-ffmpeg. Live scenes recorded once at real speed with `events.json`.
- Composition: cold-open hook ≤ 10 s, title, demonstrate, LIVE (sped ×N tag + tech explainer overlays during waits),
  question, wall of N, correction, other worlds, honest close. Explainers labelled as illustrations when not screen output.
- Storyboard (3:00): 0:00 hook "You fix a diagram once. The apprentice fixes the other hundred — and proves every edit." ·
  0:09 title + "NVIDIA Nemotron on Nebius Token Factory" · 0:20 demonstrate · 0:45 live think (N→1, probe) · 1:15 ask ·
  1:30 wall + 4 checks + byte-exact patch · 2:00 correct → v2 · 2:20 other worlds · 2:40 honest stats + repo.
- Final: loudnorm −14 LUFS, ≤ 3:00, 1080p30 H.264. Old `scripts/record_demo.mjs`/`mux_demo.sh` superseded.

## Schedule
| Day | Date | Work |
|---|---|---|
| 1 | 10-19 | Spec/plan docs; generator + library tests + provenance; confirm Nebius balance; check hackathon video rules |
| 2 | 10-20 | A1 display names, A3 after-image; staging timing of 100-doc import/apply |
| 3 | 10-21 | A2 thinking trace; B1/B2 product-1; pre-register model check, manifest for owner approval |
| 4 | 10-22 | Live dev check (Super vs Ultra/product-1); decide; disclosure text |
| 5 | 10-23 | Theme, font, stepper, readable names |
| 6 | 10-24 | Thinking panel + ghost overlays |
| 7 | 10-25 | Wall, chunked apply, slider, wall e2e |
| 8 | 10-26 | Prototype card; full suites (3.12 + 3.13), staging deploy |
| 9 | 10-27 | Video tooling (TTS, music, capture); offline rehearsal; live takes |
| 10 | 10-28 | Production deploy (candidate → e2e → traffic; rollback recorded); README/HANDOFF |
| 11–12 | 10-29/30 | Remotion edit, render, watch-through, fixes, upload |

## Verification
- Python: `uv run pytest tests/unit tests/integration tests/contracts tests/evaluation` on 3.12 and 3.13; `lint-imports`.
- Web: `npm run lint`, build, `OA_E2E=1 npm run test:e2e` (journey, ui, new wall test) locally and against the candidate URL.
- Live: dev check report vs the pre-registered rule; `/health/ready` spend under the durable cap; `docs/demo_takes.md`.
- Video: duration ≤ 3:00 (ffprobe); loudness −15…−13 LUFS; caption text == script; no silence > 1.5 s; every sped span
  tagged; every number on screen matches stored results; no secrets in frame.

## Needs from owner (asked at the right step, not blocking start)
- Current Nebius balance (budget for model check ≈ $2 + live takes ≈ $2–4).
- Approval of the dev model-check manifest (paid-run gate).
- Permission to `brew install espeak-ng` (Kokoro dependency) and to install Remotion in `video/`.
- Hackathon rules link (video length limit, logo/branding use).
