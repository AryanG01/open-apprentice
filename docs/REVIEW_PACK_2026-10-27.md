# Open Apprentice: review pack, 27 Oct 2026

For an outside reviewer (e.g. ChatGPT). Supersedes `docs/REVIEW_PACK.md` (21 Oct). Everything here is checkable in the repo;
file paths are given. Written by the assistant that built most of the code, so treat its self-assessment as biased and challenge it.

**Submission:** Nebius x NVIDIA Global AI Hackathon, track *Best Apps and Agents*. Deadline 30 Oct 2026 10:00 PDT.
Demo must stay up until 15 Dec. Repo: github.com/AryanG01/open-apprentice. Production: Cloud Run revision `00056-roj` (image `prod-cd9f35d`).

**Video to review:** `video/out/open_apprentice_demo.mp4`, 1:52 (111.9 s), recorded live on candidate `00053-zat`.
ChatGPT cannot watch video: sections 3 (timed storyboard + full narration) and the two key-frame sheets
`docs/review/video_storyboard_1.png` and `docs/review/video_storyboard_2.png` stand in for it.

---

## 1. What the product is, in one paragraph
A user brings **a banner image** or **a hand sketch plus a product-page URL**. Nemotron reads the layout into labelled parts;
the user drags/edits any box it got wrong; the app rebuilds the banner as editable layers, learns the story-card layout
(1080x1920) from one example, and asks a question only when the result is genuinely ambiguous (a long headline that does not
fit). An independent verifier then re-measures the result. Nothing the model says is trusted until the user confirms or a
deterministic check passes. Original project (earlier weeks): teach a layout rule by demonstration, reuse it through checked
procedures on real Konva and Fabric backends; diagrams and a UI-prototype lane remain under "More".

## 2. Architecture and data flow
| Step | Door 1: banner | Door 2: sketch + page |
|---|---|---|
| Read | Nemotron-3.5-Super-VL returns roles/boxes/text (`campaign/vision.py`) | Same VL model reads a wireframe (`campaign/sketch.py`, `prompts/campaign_sketch.md`) |
| Page | n/a (optional price check) | Tavily Extract reads the page (`campaign/pages.py`); Nemotron-3-Super lifts facts with source quotes and drafts up to 3 headlines of at most 44 chars (`campaign/facts.py`, `copy.py`) |
| Ground | Deterministic layer checks (boxes on canvas, roles, glyph coverage, price has digit) | Quote must be on page; numbers/currency/names must be on page; claim-word list; glyph coverage; typography normaliser |
| Human | Edit boxes/text, snap to content, crop previews | Same, plus supply own logo + product picture + colour (never generated; Token Factory has no image model) |
| Rebuild | Layers rendered on real Konva and Fabric via the engine service | Same |
| Adapt | Learned story-card rule; overflow question worded by Nemotron-3-Super, fact-checked | Same |
| Verify | `evaluation/campaign_verifier.py`: 14 independent checks (no gold answer for uploads) | Same + `evaluation/page_check.py` (match / mismatch / unknown, advisory) + "Where every part came from" panel |

Trust rules enforced in code: import-linter forbids agent-side code (`campaign/`) importing the evaluator; verifier shares no
geometry code with the engine; no `eval/exec`; procedures run only in a restricted JSON-AST interpreter; four evidence
axes (intent, symbolic, native, held-out) never collapsed to one score; `PROVIDER_MODE=mock` default.

Stack: FastAPI + Pydantic 2, React/TS/Vite, Node/Playwright engine (Konva/Fabric), z3, Remotion video pipeline, Cloud Run +
Cloud Build, Secret Manager (`nebius-api-key`, `tavily-api-key`), GCS durable spend ledger.

## 3. The video: timed storyboard and full narration (111.9 s)
Narration is Kokoro TTS; captions are burned in; screens are real sessions on the public demo (waiting time shortened in edit).

| Time | Beat | On screen | Narration (verbatim) |
|---|---|---|---|
| 0.0-7.7 | e-hook | Headphone banner in EN/FR/EN/DE shapes fanning out to story cards | Every campaign ships the same ad in a dozen shapes and languages, and someone rebuilds each one by hand. |
| 7.7-19.9 | e-banner | Live: German banner dropped in; layer editor with Nemotron's boxes; a box dragged | I drop in a banner. Nemotron 3.5 Super VL reads its parts, and I drag the boxes it got wrong. Nothing it says is trusted until I confirm it. |
| 19.9-32.5 | e-ask | Live: question about the long German headline; both options rendered | A long German headline does not fit the story card. A blind tool would squeeze it. This one stops, renders both options for real, and Nemotron 3 Super words the question. |
| 32.5-43.5 | e-answer | Live: split chosen; story card; "14 of 14 checks passed"; note that no authored answer exists | I pick split, and an independent verifier re-measures the result. For my own banner there is no authored answer, and the app says so instead of counting one. |
| 43.5-54.6 | e-sketch | Live: "No banner yet?" sketch + sample product page URL; label "This is a sample sketch we generated" | No banner yet? Start from a sketch and your product page. This is a sample sketch we generated. Nemotron reads its boxes, and Tavily reads the page. |
| 54.6-68.2 | e-facts | Live: facts (product, $159, $229, 40-hour battery, 30 dB ANC, offer ends 31 Oct) each with its page quote; headline options | Nemotron 3 Super lifts the facts from the page, each with the quote it came from, and drafts headlines from those facts only. A headline with a number or a name that is not on the page is thrown away. |
| 68.2-77.5 | e-build | Live: owner's logo and product picture uploaded, then Build | I add my own logo and product picture, and build. The banner is rebuilt as editable layers, and adapted to a story card. |
| 77.5-88.8 | e-prov | Live: "14 of 14 checks", Page check "Match: banner price $159 is on the page", provenance panel | A page check compares the price with the page. And this panel says where every part came from: the layout from the sketch, the words from the page, the pictures from me. |
| 88.8-103.2 | e-limits | Live: "What it cannot do yet" list, then results slide "Measured, not claimed" | It also says what it cannot do: flat backgrounds, one font, sixteen by nine, and no generated pictures. On our test, sketch reading named every part but its boxes were loose, which is why you drag them. |
| 103.2-111.9 | e-close | Title card | The numbers, and the failures, are in the repository. Open Apprentice: bring a banner or a sketch, and trust the result. |

Results slide on screen (e-limits): banner reading 6/6 roles named (words 83% exact, boxes only partly right); sketch reading
6/6 synthetic wireframes, 6/6 roles but all layers found on only 2 of 6 (partial); 252/274 real designs fit the *current* rule
(upper bound by element count; the old six-part rule: 0/274); 14/14 independent checks for the banner in the video; sealed
set 22/22 on Konva and Fabric. Footnote: one pre-registered run on 6 development banners; 274 designs scanned ourselves,
not user research; sealed set written by a separate AI agent; screens are real sessions.

Honest flags about the video itself: the sample sketch and the product page/pictures are **generated by us** for a fictional
brand (Halden), labelled as such on screen; the banner in the first half is also from our samples (owner-authored); no
real hand-drawn sketch and no third-party banner has been shown yet. Key frames: `docs/review/video_storyboard_*.png`.

## 4. Evidence table (what was measured, where)
| Claim | Number | Source | Caveat |
|---|---|---|---|
| VL reads banner roles | 6/6 banners, roles named; words 83% exact; median box overlap 0.551 | `docs/evaluation/campaign_vision_dev_run3.md` | Dev set of 6 synthetic banners; pre-registered rule gave **partial** |
| VL reads wireframe sketches | 6/6 roles, median overlap 0.611, all layers found 2/6, cost $0.027 | `docs/evaluation/campaign_sketch_dev_run1.md` | Synthetic wireframes drawn by us; **partial** |
| Real hand-drawn sketches | not yet run | `docs/evaluation/campaign_sketch_real_protocol.md` (pre-registered go: recall >= 0.9 and box-on-target >= 0.7) | Waiting on owner's drawings |
| Role mapping, rule-based vs text model | 17/24 vs 7/24 | `docs/evaluation/campaign_roles_v2.md` | Our own generated set |
| Sealed generalisation | 22/22 (8 new banners, 4 new languages) | `docs/evaluation/campaign_sealed.md` | Set written by separate AI agent from rules only |
| Konva/Fabric parity | 16/16 | `docs/evaluation/campaign_parity.md` | |
| Real-world coverage | 252/274 fit current rule (upper bound), 23 lower bound, old rule 0/274 | `docs/evaluation/real_world_coverage.md` | Crello metadata only; no images downloaded (licence terms not accepted); counts by element, not rendered |
| Accessibility | axe-core 4.10.2: 0 violations across 8 UI states, light and dark | `tests/e2e/adapt.test.mjs` | Banner/sketch lanes only; Diagrams/Prototype lanes not fully scanned |
| Live smokes (production/candidates) | 14/14 checks, page check "match", facts found, 3 headline options | HANDOFF.md 26 Oct | Model copy varies run to run |
| Original learning benchmark | apprentice A trailed baseline B on learning and correction in the frozen run | `docs/evaluation/final_results.md` | Reported as is |

## 5. Deployment, spend and limits
- Production `00056-roj` (prod-cd9f35d); rollback chain 00053-zat, 00048-wuq, 00046-wuc (all documented in `docs/HANDOFF.md`).
  Owner runs gcloud (the agent's deploys are blocked by design).
- Spend: owner cap **$5 total** live spend from 26 Oct. My tally about $0.6-0.8; the Nebius dashboard is authoritative.
  Public demo has a $3 durable cap (about $1.23 used). Per-address quotas: 10 vision reads/h, 6 page reads/h, model 6/h,
  3 pages/workspace; Cloud Run CSP `script-src 'self'`.
- Secrets only in Secret Manager; never committed.

## 6. Tests and gates run for this pack (27 Oct, on the working tree at 9dd33a9)
All run 27 Oct on the working tree (code identical to production `prod-cd9f35d`; only docs changed since).
| Gate | Result |
|---|---|
| Python tests (3.12 venv) | 1768 passed, 3 warnings |
| Engine tests (`npm test -w services/engine`) | 92/92 |
| Geometry / snap tests | 4/4 and 8/8 |
| Browser e2e (real Chromium + engine, incl. axe scans) | 18 passed, 0 failed, 1 skipped (skip-link test) |
| ruff / black | clean / 373 files unchanged |
| Web lint | 0 errors, 1 warning (`react-hooks/exhaustive-deps` at `App.tsx:169`, not fixed) |
| Trust-boundary check (`lint-imports`) | **not re-run in this session**: the rebuilt venv lacked it and the sandbox blocked reinstalling from PyPI. Last green on CI at commit cd9f35d; run `uv run lint-imports` to confirm. |

## 7. Known weaknesses (stated by me, not softened)
1. **No real hand-drawn sketch has been read.** Only synthetic wireframes; result was partial. The sketch door is therefore a prototype of an idea, not a demonstrated capability.
2. **No third-party banners and no external users.** Everything evaluated is ours. Impact claims are unsupported by users.
3. **Output is a "first draft" banner:** flat backgrounds, Liberation Sans only, 16:9 input, no generated imagery, one story-card layout learned from one example.
4. **Headline quality** is checked for grounding (is it true to the page), not for persuasiveness. Model drafts vary and sometimes exceed 44 chars (app then asks).
5. **Demo material is generated:** sample sketch, product page, product picture are ours for a fictional brand. Labelled, but a skeptical judge may call it staged.
6. **Original thesis (learn from demonstration) is now less visible** than the banner tool; the frozen benchmark showed no win over the baseline.
7. img2threejs only did a blockout pass; the 3D headphone loader is hand-written. Decorative.
8. Deploy chain is manual (owner), so a late bug fix risks timing.

## 8. Open owner actions
- Draw 4-5 real sketches -> run `node scripts/sketch_probe_real.mjs <dir>` -> publish result whatever it is -> optionally re-record video with `node video/capture/full.mjs --sketch PATH`.
- Choose: A) test on the owner's own real banners (recommended) or B) agree to VistaCreate terms for Crello images (I will not accept terms on their behalf).
- Watch v2 video, upload to YouTube (public), give link for README and `docs/submission.md`; fill Devpost; check Nebius balance before 15 Dec.

## 9. Questions I want the reviewer to attack
1. Does the first 30 s of the video show an aha for a stranger, or is the generated-brand staging too obvious?
2. Is "6/6 roles but boxes loose, so you drag them" a credible product story, or does it read as an excuse?
3. Is the sketch door worth its video time (about 60 s) versus deepening the banner door with a real third-party banner?
4. Would a judge read the honesty slides ("Measured, not claimed", "What it cannot do yet") as rigour or as lack of confidence?
5. What single change in the next 2.5 days most raises placement odds?
6. Are any claims in README/`docs/submission.md` stronger than the evidence in section 4?

## 10. My own re-score (strict; previous 62/100 on 26 Oct)
Criteria weights assumed 25 each (technology, design, impact, idea). Scores are my estimate, not the judges'.

| Criterion | Prev | Now | Why |
|---|---|---|---|
| Technology | 20 | 21 | Two real models + Tavily wired end to end with deterministic grounding, independent verifier, quotas, durable spend cap, 3.12/CI discipline, pre-registered evals incl. failures. Up one for page check, provenance and tested a11y; held back because the sketch reading is only partial and Nemotron-3-Super is used for wording more than reasoning. |
| Design / completeness | 15 | 17 | Redesign is coherent, axe-clean in 8 states, limits panel, provenance panel. Output banners are still first-draft quality and flat; staging with a generated brand is visible. |
| Potential impact | 11 | 11 | Real problem (multi-format ad rebuilds) but zero users, zero third-party banners, no real sketch. Cannot rise until at least one outside artefact is run. |
| Idea / originality | 16 | 16 | Ask-before-guessing plus grounded copy plus visible provenance is distinctive; sketch-to-banner is a common pitch and the learning-by-demonstration core is now background. |
| **Total** | **62** | **65** | |

Rough placement odds (guesses, ~6,000 teams, wide uncertainty): top-3 overall roughly 3-6%; Best Use of Tavily prize
roughly 10-20% (real, grounded, non-decorative use, but one of many entrants); a track win roughly 8-15%.
Biggest swing items: (a) one real hand-drawn sketch read live in the video, honest even if boxes are loose; (b) one real
third-party banner through the banner door; (c) a first outside person trying it. Each is owner-dependent.
