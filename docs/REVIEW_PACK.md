# Open Apprentice: full project review pack

This is a self-contained brief for an external reviewer (human or AI). It covers what the product is, every feature, the
tech stack, the process and data flow, the AI method, the evaluation and its results, the infrastructure, the security work,
the demo video, how it was built, and the known limitations. At the end are the questions we most want challenged.

- **Repository:** https://github.com/AryanG01/open-apprentice (public, MIT)
- **Live demo:** https://open-apprentice-md76de375q-uc.a.run.app
- **Hackathon:** Nebius × NVIDIA Global AI Hackathon (Devpost), track *Best Apps and Agents*. The deadline is
  30 Oct 2026, 10:00 PDT.
- **Project dates:** started 11 Oct 2026; status as of 21 Oct 2026. About 310 commits, about 25.7k lines of Python,
  3.8k lines of TypeScript for the web app, and 151 Python test files.

---

## 1. The one-paragraph pitch

Teams keep many diagrams that should follow the same layout conventions, for example "every note sits under its box,
left-aligned". These conventions are easy to show and hard to write down. Open Apprentice lets a person demonstrate the
convention once, by dragging the notes on one real draw.io diagram. NVIDIA Nemotron, called live through Nebius Token
Factory, proposes small programs that could explain the demonstration. When several programs fit, the system does not
guess. It generates a test diagram where they disagree and asks the person one question, with a rendered picture of each
answer. The agreed rule becomes a versioned "skill". The skill is applied to any number of other diagrams through
byte-exact patches of note positions. Each patch must pass three separate checks against what the real draw.io engine
rendered before it is published. Corrections create new skill versions. We evaluated the approach against the same model
acting freely, on a frozen benchmark, and we publish the results, including where we lose.

## 2. The problem and who it is for

- **Who:** engineering, platform, IT, operations and product teams that maintain many architecture maps, process flows,
  org charts, network maps, floor plans and roadmaps in draw.io (diagrams.net).
- **Pain:** diagrams drift. Notes end up scattered and inconsistent, and fixing a hundred files by hand is tedious and
  error-prone. Style guides are prose that nobody applies.
- **Why not "just use an LLM to fix it":**
  - A model that guesses a rule from one example can pick the wrong one of several equally plausible rules.
  - It then applies that mistake everywhere, silently.
  - Generated edits can break files.
- **Our position:** behave like an apprentice, not an autopilot. Learn from one example, ask when ambiguous, prove each
  edit, refuse when the examples conflict.

## 3. Features (what a user can do)

### 3.1 Diagrams area (the main product, "Apprentice")

The page is a single, dark "drafting-table" interface. A step rail runs across the top: Import, Map labels, Teach by
example, Watch it think, Reuse everywhere.

1. **Bring your diagrams.**
   - **Ways to add files:**
     - Upload `.drawio` files.
     - Click a sample: plain-language heroes (Online order journey, Hiring process, Support tickets), "The big one: AI
       platform map (217 objects)", and three older owner-authored samples.
     - Click **Load the 100-diagram library**.
   - **Rendering:** every file is rendered by the real draw.io viewer in a locked engine. The card shows a preview.
   - **Mapping:** the system proposes which note (text label) describes which box (node). It does this by nearest
     rendered geometry. Rows show readable names and colour swatches, not cell ids. The user can change the node or the
     "role" (for example note or warning) and presses **Confirm mapping**. **Confirm all suggested mappings** confirms many
     at once.
   - **Large libraries:** with more than six documents the cards become compact, show 12 at a time, and have a "Show all"
     button.
2. **Show it once (Teach).**
   - Pick the document to edit.
   - Drag note boxes on the rendered image. Arrow keys nudge by 1, Shift by 10 and Alt by 1/64. You can also type x/y.
   - Each edit triggers a server **draft render**. The confirm button only enables once the user has seen the engine's
     render of exactly the current positions.
   - Optionally tick **Use the live model**. Then press **This whole document is right**.
   - Pages larger than 32 objects are marked "for reuse only". The teaching session takes the demo document plus up to
     five other documents for previews.
3. **The apprentice at work (session view).**
   - **Provenance line:** `Model: Live · Teacher: You · Policy: product-1`.
   - **State:** shown alongside the provenance line.
   - **The open question.** It takes one of three types:
     - *ChooseOutput*: "Your example fits more than one rule. Which result did you mean?" It shows two to four rendered
       pictures of the same test diagram, one per alternative, in colour-coded frames A/B/C/D. Each frame lists the rule(s)
       behind it.
     - *ConfirmPreview*: approve, reject or "not sure" for each unseen document. Documents that would break layout are
       shown as "Blocked" and cannot be approved.
     - *ConfirmCorrectionScope*: used in correction sessions (see 3.1.5).
   - **"Apprentice's notebook" panel (watch it think):**
     - a big counter of how many rules still fit;
     - each proposal round, with the number proposed and the number that fit, plus the rule summaries;
     - "Drew a test diagram";
     - "Asked you: here N rules give K different results", with the rules behind each option;
     - your answer and how many rules are left;
     - "Kept as a skill: …".
   - **Evidence:** budgets, spend and result, in a collapsible "Evidence" section.
   - **Controls:** Cancel session, and Start over.
4. **Reuse everywhere.**
   - **Apply:** the skill's active version is shown. Pick documents (Select all, Select none) and press **Apply**. Large
     applies are chunked into runs of 25 documents.
   - **The wall:** a grid of tiles. Each tile shows:
     - a thumbnail, with a "rendering…" placeholder until it loads;
     - a status (Published, Blocked, Unchanged or Failed);
     - three check lines with ✓ or ✗;
     - reasons when blocked;
     - downloads: `.drawio`, SVG and Receipt (JSON);
     - **Correct this document**.
   - **Tally:** "N of M checked · X published · Y blocked by a check".
   - **Before/after:** clicking a published tile opens a slider comparing the imported render with the published render.
5. **Correct a result.**
   - The user nudges notes on a published or blocked result and submits.
   - A correction session asks how the correction should be kept:
     - **Change the skill**, with a proposed scope selector (for example "labels where role == note") and its consequences
       on other documents shown as rendered previews;
     - **Keep a one-off override**;
     - **That edit was a mistake**.
   - Accepted revisions are stored as a new skill version and activated through compare-and-set. Corrections are limited
     to pages of up to 32 objects.

### 3.2 "UI components · Earlier prototype" area

This is the original prototype, kept working. It teaches a "badge on a card" placement rule, then transfers it to two real
graphics engines (Konva and Fabric, in a browser). It simulates a silent tool change, reproduces the mismatch and repairs
only the native procedure. It also has a stress test, an SVG lane (real SVG files) and an offline evidence re-check. Its
modes are Home, Learn, Reuse, Transfer, Challenge, Compare, Try it live and Real SVG. It uses its own learner (reference
enumerator, live Nemotron, or a recorded replay) and keeps four separate evidence axes: intent, symbolic, native and
held-out.

### 3.3 Supported inputs and limits

- **Inputs:** draw.io `mxfile`, including compressed pages. Movable notes are text cells (style contains `text`) at the top
  level, unrotated and single-line.
- **Teaching limits:** at most 32 objects per page, including at most 16 notes, because the model prompt and probe search
  are sized for this.
- **Applying limits:** a learned skill applies to pages of up to 400 objects and 200 notes.
- **Refused files:** files over 2 MB, more than 20 pages, more than 8 MB decoded in total, non-Helvetica fonts, DOCTYPE or
  entities, unsafe page ids, and cells outside the page. Each refusal comes with a reason.
- **Edits:** only note x/y. Nothing is restyled.

## 4. Tech stack

| Layer | Technology |
|---|---|
| AI model | NVIDIA Nemotron via **Nebius Token Factory** (OpenAI-compatible API): `nvidia/nemotron-3-super-120b-a12b` for live product sessions, `nvidia/Nemotron-3-Ultra-550b-a55b` for the frozen evaluation. `reasoning_effort=low`, JSON mode (`json_object`), completion cap 32k. |
| Backend | Python 3.12 (also tested on 3.13), FastAPI 0.115, Pydantic 2, uvicorn, httpx, z3-solver 4.13.4 (witness search in the prototype), SQLAlchemy (legacy paths) |
| Rendering engine | Node + Playwright driving headless Chromium with the vendored draw.io viewer (`viewer-static.min.js`, hash-checked), all network requests blocked. Konva 9 and Fabric 6 for the prototype. Liberation Sans stands in for Helvetica. |
| Frontend | React 18, TypeScript 5.6, Vite 5, one hand-written CSS file with design tokens, Barlow font (OFL, self-hosted via @fontsource). No UI library. |
| Storage | `Store` interface: local filesystem or Google Cloud Storage, with compare-and-set (`if_generation`) and create-only writes |
| Infra | Google Cloud Run (1 vCPU, 2 GiB, min 1 / max 6 instances, session affinity), Cloud Storage, Cloud Tasks (OIDC-authenticated callbacks), Secret Manager (Nebius key), Cloud Build (tagged images) |
| Video | Remotion 4.0.536 (React video), Kokoro-82M TTS (Apache-2.0, local), procedurally generated music (numpy), ffmpeg via imageio-ffmpeg |
| Quality | pytest (≈1200 tests, plus engine tests), Playwright end-to-end tests (12), import-linter boundary contracts, ruff, black, ESLint, GitHub Actions CI |

## 5. Architecture and code map

```
apps/web/            React app (src/v2/* is the Apprentice; App.tsx shell; prototype components)
services/engine/     Node/Playwright engine: /drawio/render (PNG/SVG + measured boxes), Konva/Fabric tools (prototype)
src/open_apprentice/
  api/app.py         FastAPI app, health (/health/ready shows the durable live ledger), static web, legacy prototype API
  api/v2/            routes.py (HTTP), service.py (all v2 logic), records.py (owner-checked records, idempotency),
                     context.py (wiring: store, renderer, proposer, ledger, dispatcher, rate limiter), tasks.py (Cloud Tasks)
  drawio/            parse.py (safe XML parse, compressed pages, plain_text/display), classify.py (movable vs fixed,
                     limits, refusals), mapping.py (note->node proposal, confirm, digest), render.py (engine client,
                     2-slot semaphore), scene.py (scene objects from rendered geometry), patch.py (byte-span edits),
                     publish.py (re-parse, re-render, checks, receipt)
  teaching/          events.py (event-sourced SessionLog with compare-and-set head), step.py (pure policy step(),
                     thinking_trace), executor.py (runs actions: model calls, probes, requests), constraints.py (evidence
                     derive), probes.py (generated test diagrams + search), teacher.py (request/response types),
                     correction_* (correction policy and executor), layout.py (refusal of unsafe conventions), accounting.py
                     (durable Ledger), codec.py
  concepts/          rules.py (exact-arithmetic rule language + interpreter), rule_text.py (text syntax), hypotheses.py
                     (fit checks), label_enumerative.py (offline enumerator), label_teaching.py (prompt evidence)
  providers/         nebius.py, factory.py, teaching_adapter.py (proposer/scope proposer over the model), spend.py
  skills/            versions.py (SkillStore: versions, activation compare-and-set), interpreter.py (restricted JSON-AST)
  storage/           store.py (LocalStore), gcs.py (GcsStore)
  evaluation/        frozen battery, isolated learner runner, scoring, analysis, manifests and paid-run gate
  learner/           isolated learner process (systems A, A2, B, C, D, D2) talking to the teacher over pipes
scripts/corpus/      generate_library.py (100-diagram library + hero diagrams, seeded)
video/               capture/capture.mjs (records a real session), tools/ (tts.py, music.py, encode.py), src/ (Remotion)
docs/                evaluation/*, corpus provenance, HANDOFF.md, submission.md, decisions.md, deploy*.md, specs/plans
```

**Trust boundaries (enforced by import-linter in CI):**
- Agent-visible code (`agent`, `concepts`, `skills`, `providers`, `environments`) never imports the evaluator or the
  frozen benchmark.
- Nothing uses `eval` or `exec`. Model output is data, run only by the interpreter.

## 6. Process flow

### 6.1 User flow (happy path)

Import → render → confirm mapping → demonstrate on one diagram → (live) Nemotron proposes → filter on the demonstration →
probe search builds a test diagram → question with pictures → answer → preview on unseen docs → commit and activate skill →
apply to many docs → three checks per doc → publish and receipt → optional correction → new version.

### 6.2 System flow, step by step

1. **Upload** (`POST /documents`):
   - Parse the file safely: no DOCTYPE or entities, size, page and decoded limits, and page ids restricted to
     `[A-Za-z0-9_-]`.
   - Classify each page. Store the source in the store, keyed per owner.
   - Dispatch a **render** job (local thread pool, or a Cloud Task in production). The engine returns a PNG plus the
     measured box of every cell.
   - The mapping proposal is computed from the measured geometry: each note goes to its nearest node.
2. **Confirm mapping** (`POST /documents/{id}/mapping`): compare-and-set on the stored mapping. The mapping digest becomes
   the `mapping_hash` that every later reference must quote, which protects against stale state.
3. **Scene:** for teaching, each page becomes a "scene" of objects (`id, kind, role, attached, x, y, w, h` as exact
   rationals) plus the canvas size. It is built from rendered boxes, not from raw geometry. Display text and colours are
   sent to the UI separately and **never** placed in the scene, so the learner is text-blind.
4. **Draft render** (`POST /documents/{id}/draft`): applies the user's note positions as a temporary patch and renders it.
   Nothing is stored. The UI shows the engine's measured boxes and only counts a demonstration as "seen" when the render of
   exactly those positions has landed.
5. **Create session** (`POST /sessions`, idempotent):
   - Validates the documents, which must be at most 32 objects and have fresh mapping hashes.
   - Records the scenes, the demonstration output, and the policy: `A` offline, `product-1` live.
   - Dispatches **advance**.
6. **Advance** (executor loop), repeated until the session needs a person or ends:
   - The pure policy `step(events, config)` decides the next action from the event log:
     - **Rule 1:** no proposals yet → `RequestModelProposal("initial")`.
     - **Rule 2:** no candidates survive the filter → one "revision" round with feedback, then abstain ("no acceptable
       program found within the search limits").
     - **Rule 3:** several candidates disagree on a registered document → `AskTeacher(ChooseOutput)` with up to four
       groups of identical outputs.
       - Otherwise run the **probe search**: generate test diagrams (nudged copies of real scenes) and pick one that
         separates the candidates.
       - Then `RenderProbe` renders it in the engine; a probe whose render differs from the plan is never shown.
       - Then ask.
     - **Rule 4:** a single behaviour, or no disagreement found → one "contrastive" round asking the model for rules that
       would disagree.
     - **Rule 6:** select the simplest surviving program.
       - Refuse if the demonstrated convention itself breaks layout.
       - If it is not yet approved on a preview → `PresentPreview` (ConfirmPreview on up to N unseen documents, with
         blocked items flagged).
       - When approved → `CommitVersion`.
   - **Executor:** for each action it appends events (`ActionIssued`, `ModelProposalReturned`, `ModelCallFailed`,
     `RequestIssued`, `ResponseRecorded`, `ProbeRendered`, `VersionStored`, `Abstained`, `Errored`) to the log. It uses
     compare-and-set on the head.
   - **Model calls:** made through the proposer, with a durable ledger reservation before each call (worst-case cost) that
     is settled afterwards.
   - **Product policy `product-1`:** a reply cut at the completion cap becomes an empty round instead of a terminal error.
7. **Filter:** every candidate rule must pass, in order:
   1. parse and validate;
   2. not be "magic" (comparing a position, size or id with a constant);
   3. fit every positive and negative constraint within 1/2 unit;
   4. run on every registered scene;
   5. change nothing except note positions.
8. **Answer** (`POST /sessions/{sid}/responses`): checked against the open request and its intent revision. Answers become
   constraints; for example a chosen alternative becomes a positive example on the probe scene. The executor continues.
9. **Commit:**
   - **Stored:** the version artefact holds the rule, a summary, a claim, the evidence items and its provenance.
   - **Activated:** activation is a compare-and-set on the skill pointer, so concurrent activations cannot both win.
   - **Recorded:** skill provenance records the model, the teacher and the policy.
10. **Apply** (`POST /skills/{id}/versions/{v}/apply`, idempotent, chunked by 25 in the UI). For each document:
    - run the rule on its scene → target positions;
    - `plan_edits`, which converts targets to geometry by subtracting the measured offset and rounding to integers;
    - `apply_edits`: byte-span replacement of only the `x=`/`y=` attributes, with the expected old values and the
      source hash checked;
    - **publish** (6.3).
11. **Export:** `.drawio` (the published bytes), PNG (the exact render the checks measured, stored at publish time), SVG
    (rendered by the engine) and the receipt (JSON).
12. **Correction:** `POST /skills/{id}/corrections` starts a correction session. Its scope proposer (the model or the
    offline enumerator) proposes how to generalise. The person picks revise, override or accidental. Revisions are
    checked on affected examples and then activated.

### 6.3 Publish checks (the safety net)

For each changed document:
1. **Re-parse** the new bytes.
2. **Other pages unchanged:** bytes outside the edited page must be identical.
3. **Preservation:** nothing changed except the x/y of edited notes.
4. **Conformance:** re-render in the engine; every measured note box must equal its target within 0.5 plus rounding, at
   the same size and on a single line.
5. **Layout safety:** nothing is outside the page and no edited note overlaps another object.

Steps 2–3 are reported as one "Preservation" check. The UI and receipt show three checks: Conformance, Preservation and
Layout safety. Two of them use the same render measurement, so we call them "separate", not "independent". Only if all
pass is the file published, via a create-only write, so it can never be overwritten. Otherwise the document is "Blocked"
with reasons.

## 7. The AI method in detail

- **Rule language:** a small JSON AST with statements `let`, `if`, `for_each` (over objects) and `emit_target`, and
  operations `add sub mul div min max lt le gt ge eq ne and or not get len by_id`. It has a text syntax, for example:
  `for o in objects { if o.kind == "label" { let a = object(o.attached) move o to (a.x, a.y + a.h + 8) } }`.
  - All arithmetic is exact (`Fraction`).
  - Numbers are capped at 256 bits.
  - Literals accept only bounded decimals and fractions, never exponents.
  - Limits: 64 statements, depth 8, 500 expression nodes, 300k statement steps, 1M loop iterations, 400 objects.
- **Model's role:**
  - Propose candidate programs (4–8 per round) with a summary each.
  - Propose revisions with feedback on why earlier candidates failed.
  - Propose contrastive candidates that would disagree with the current ones.
  - Propose correction scopes.
  - The model never edits files directly.
- **Why asking works:**
  - A demonstration usually under-determines the rule. For example "gap 8 below" versus "node height + 8" versus
    "fixed 64 from the top" are identical on equal-height boxes.
  - Probe search builds the one diagram where the surviving rules give different pictures.
  - One answer prunes the wrong rules.
- **Offline learner:** a template enumerator (side × gap × scope). The product works with no model; such sessions are
  labelled "offline enumerator".
- **Text-blindness and anti-cheating:** the learner never sees note text. Rules comparing ids, positions or sizes with
  constants are rejected as "magic".

## 8. Evaluation: frozen benchmark (honest results)

- **Battery:** 36 final plus 18 development episodes of synthetic label-placement tasks (battery-v2.5, scoring
  score-v2.2). The strata are:
  - catalogue (identifiable, or ambiguous and requiring a question);
  - beyond-catalogue;
  - inconsistent demonstrations;
  - unsupported rules;
  - sequential (acquire, then correct).
  The private manifests are git-ignored, and their hashes are recorded.
- **Isolation:**
  - The learner runs in a separate process with an audit hook that blocks imports, file reads under benchmarks, and
    process spawns.
  - The teacher simulator talks to it over inherited pipes.
  - 0 boundary violations.
- **Systems:**
  - **A**, the apprentice policy;
  - **B**, the same Nemotron model acting freely with the same tools (option protocol), with its own correction cycle;
  - **C**, a 24-program catalogue;
  - **D**, the apprentice with uniformly random questions.
- **Paid-run gate:** every live run needs an owner-approved manifest whose id is a hash of its terms. It enforces a cap,
  a protected reserve, and a cross-process spend ledger with reservations.
- **Final results** (Ultra, 3 repeats; `docs/evaluation/final_results.md`):

| Endpoint | A (apprentice) | B (free agent) |
|---|---|---|
| Learning success (16 × 3) | 22/48 | 28/48 |
| Correction success, end to end (12 × 3) | 18/36 | 22/36 |
| Appropriate refusal, inconsistent + unsupported | **18/24** | 9/24 |
| Conflicting demonstrations surfaced | **12/12** | 6/12 |
| Ambiguous catalogue (must ask) | **2/12** | 0/12 |
| Identifiable catalogue | 7/12 | **12/12** |
| Cost per run | **$0.17** | $0.26 |
| Wrong commits | 3 | 3 |

- **Conclusion:** the primary hypothesis, that the asking policy beats the free agent on learning, is **not supported**.
  The apprentice wins on refusing, surfacing conflicts, ambiguity and cost. It loses on easy identifiable rules, because
  after its proposal rounds it gives up where B just keeps proposing.
- **Policy v2** (more revision rounds) was tested against a rule registered in advance on the development split. It did
  not meet the rule (5/8 against a bar of 6/8) and was **not adopted**.
- **Product model check** (`docs/evaluation/product_model_check.md`): 3 live sessions per model on the demo flow.
  - Ultra: 3/3 correct, median 58 s.
  - Super: 2/3 correct (1 abstained), 0 wrong, median 22 s.
  - The registered rule adopted Super for the live site.
  - A scoring bug in the check script is disclosed, together with the corrected scores.
  - Also noted: under the spec's stricter draft rule, Ultra would have won.

## 9. Product reliability measures added after the evaluation

- **`product-1` policy:** truncation-tolerant, for live sessions only. It is disclosed in the session, skill and run
  provenance and in the video. Evaluated rows are unchanged.
- **Durable spend cap:** a storage-backed ledger with compare-and-set reservations, shared by all instances
  (`DEMO_MODEL_MAX_USD=5`). The site never silently downgrades; the user is told and offered the offline learner.
- **Rate limit:** 3 live sessions per hour per client. The key is the rightmost `X-Forwarded-For` entry, which cannot be
  spoofed behind Cloud Run.
- **Throughput:**
  - The render semaphore queues instead of failing on the engine's 2-render limit.
  - Event-chain caching by head event id.
  - The thinking trace is cached.
  - Exports reuse the PNG rendered at publish time.
  - The client polls at most 8 pending documents per tick.
  - Cloud Run allows 6 instances.

## 10. Security work (from two reviews)

- **Fixed:**
  - Unbounded `Fraction` parsing, where `"1e30000000"` froze an instance for about 41 s.
  - A decompression memory bomb across many pages.
  - Unsafe page ids, which caused path and header issues.
  - Uploads blocking the event loop.
  - Idempotency and task-claim races, fixed with nonces.
  - Spoofable rate-limit keys.
  - Unbounded rule arithmetic, now capped at 256 bits.
  - Unbounded loop iterations, now capped at 1M.
  - The secure cookie flag behind the proxy.
  - The display trace no longer 500s the session.
  - Owner-cookie races on parallel first uploads.
- **Verified sound:**
  - Owner checks on every v2 record.
  - The HMAC-signed owner cookie.
  - OIDC verification on the Cloud Tasks callback.
  - Compare-and-set skill activation.
  - XML hardening: no entities, depth and size limits.
  - The label HTML allowlist.
  - Engine network isolation.
  - Strict CSP: `default-src 'self'`.
- **Known remaining (minor):**
  - The rate limiter is in memory, per instance; the durable cap is the real guard.
  - Failed background jobs are not retried.
  - Some malformed request bodies return 500 instead of 400.
  - `get_document` re-parses the source on every poll.
  - The before/after dialog does not trap focus.

## 11. Data: demo library and provenance

- **Library:** `scripts/corpus/generate_library.py` (seed 20261019) writes **100 diagrams** in ten themes:
  - AI factory pipeline, DGX SuperPOD, LLM inference serving, RAG assistant, Kubernetes GPU cluster, data lakehouse;
  - **GPU data-hall floor plan**, **org chart**, **model release roadmap**, **spine-leaf network**.
- **Hero diagrams:** order journey, hiring process, support tickets, and a **217-object company AI platform map** with
  108 services, about 160 random dependencies and 108 notes.
- **Note text:** written in plain language.
- **Deliberate messiness:** positions are untidy so the skill has work to do.
- **Tests:** every file is checked to import, render in the real engine, map each note to its own box, and fit the demo
  rule without overlaps.
- **Provenance:** `docs/corpus/library_provenance.md`. The files are generated by our script with no external assets, and
  the library is not evaluation data.

## 12. The demo video (2:37)

- **Pipeline:**
  - `video/capture/capture.mjs` records one continuous **real** session on the production site, using Chrome screencast
    PNG frames at 1080p, a visible cursor and timestamped marks.
  - A scripted "person" answers each question by comparing the rendered outcomes with the intended placement.
  - The capture saves real before/after renders for the montage and the finale.
  - `video/src` (Remotion) cuts the clips on the marks, speeds up waits, zooms on the focus areas, and adds karaoke
    captions from Kokoro word timings, animated "how it works" chips, title, architecture, breadth and finale scenes, and a
    results card.
  - The music is generated and ducks under the voice.
  - Loudness is normalised to −14 LUFS.
- **Story:**
  1. Montage of real before/after renders.
  2. Title, then "Under the hood".
  3. The plain-language order journey: teach by dragging.
  4. Live Nemotron: proposes, draws a test diagram, asks, previews, commits.
  5. 100+ diagrams in one click.
  6. Not just flowcharts: floor plan, org chart, roadmap, network.
  7. The UI-cards prototype.
  8. **Finale:** the 217-object map, wiping from imported to published.
  9. Honest results card.
- **Disclosures in the video:** "Every screen is a real session; waiting time is shortened in the edit". The live runs use
  Nemotron-3-Super and product-1, while the benchmark uses Nemotron-3-Ultra and policy A. Each row of the results card
  highlights its winner.
- **Takes log:** `docs/demo_takes.md` records every take, including the one where a wrong answer led the layout check to
  block 10 floor plans (90/100), and the failed early live take.

## 13. How it was built (process)

- A spec-first, plan-driven workflow: design specs and plans are in `docs/superpowers/`, and every deviation is recorded
  in `docs/decisions.md`.
- Test-driven development for every fix. Independent whole-branch code reviews before merges: correctness and security,
  efficiency, and a final branch review.
- Pre-registered decision rules before every paid experiment, with failures published.
- Production cutovers as a no-traffic candidate first, then a browser journey against the candidate URL, then a traffic
  move with a recorded rollback.
- About $100 of Nebius credit was spent across development, the evaluation (about $47 for the funded final run) and the
  demos. The live site's durable cap is $5.

## 14. Deployment and operations

- **Project:** GCP `oa-demo-1013-19737`, us-central1, Cloud Run service `open-apprentice`.
- **Production:** revision `00027` serves the latest master. Rollback is one `gcloud run services update-traffic` command
  (`docs/HANDOFF.md`).
- **Settings:** bucket `oa-prod-*`, queue `oa-prod`, a service account with least privilege, the Nebius key in Secret
  Manager, min 1 / max 6 instances, session affinity, and env `NEBIUS_MODEL=nvidia/nemotron-3-super-120b-a12b`.
- **Running locally:** `uv sync`, `npm ci`, `npx playwright install chromium`, `npm run build:web`, then
  `uv run uvicorn open_apprentice.api.app:app`. It works offline with no key.

## 15. Tests and CI

- **Python:** about 1197 tests in unit, contracts and evaluation, about 1297 including engine integration tests, on
  Python 3.12 and 3.13.
- **Engine tests:** `npm test -w services/engine`.
- **Browser:** Playwright journeys, 12 in total, covering:
  - import, map, teach, clarify, commit, reuse, download, correct, cancel and reload;
  - overlay alignment and the draft-render gate;
  - samples;
  - the prototype;
  - one optional paid live story against a deployment.
- **CI:** GitHub Actions runs lint, import boundaries, the Python tests and the engine tests. The latest master is green.

## 16. Known limitations (stated plainly)

- On the benchmark the apprentice does **not** beat the free agent on learning success. Its advantages are refusal,
  conflict detection, asking, and cost.
- The task family is narrow: note placement relative to boxes. It does not restyle, change colours or align groups.
- Live runs can abstain ("unresolved disagreement", "no acceptable program") or take minutes on Ultra.
- Teaching is limited to pages of 32 objects. Corrections are disabled on larger pages.
- The real-file final episodes could not be run. The adapter refused the frozen file, which put a cell outside the page.
  There is therefore no held-out real-file generalisation result.
- Draw.io coordinates are written as integers. Centred placement of fractional-width notes can land up to 0.5 units off,
  which is why the demo uses left alignment.
- The demo library is generated by us, not real customer files.
- One provider (Nebius) and one model family (Nemotron).

## 17. Questions we want a reviewer to challenge

1. Is the core claim, "asking beats guessing", adequately supported given the benchmark result (22/48 against 28/48)? How
   should we frame the value honestly yet compellingly for judges?
2. Is the product compelling and coherent for a real audience, or does it still read as a technical proof of concept? What
   would most improve the *Design* and *Potential Impact* criteria?
3. Is the use of Nemotron and Token Factory deep and non-obvious enough for the *Quality of the Idea* and *Technological
   Implementation* criteria? Is the Super/Ultra split well justified?
4. Are there correctness or security risks in the flow above, especially publish checks, idempotency, compare-and-set
   activation, the rule interpreter limits, or owner isolation?
5. Is any claim in the README, video or submission text overstated?
6. In the demo video, which parts drag or confuse? Is 2:37 the right length? Does the finale land?
7. What is the single highest-leverage change to make before the deadline (30 Oct, 10:00 PDT)?
