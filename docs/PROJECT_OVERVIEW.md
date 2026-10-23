# Open Apprentice: full project overview (for an external review)

Status as of 23 Oct 2026. Written so a reviewer who has never seen the project can judge it end to end. Every number
below comes from a file in the repository; the source is named next to it. Where something is weak, unproven or not
built, it says so.

- **Live demo:** https://open-apprentice-md76de375q-uc.a.run.app (no login, no key)
- **Repository:** https://github.com/AryanG01/open-apprentice (MIT)
- **Video:** 2:11, rendered locally (`video/out/open_apprentice_demo.mp4`), not yet on YouTube
- **Event:** Nebius × NVIDIA Global AI Hackathon, track *Best Apps and Agents*. Deadline 30 Oct 2026, 10:00 PDT. The
  demo must stay up until judging ends (15 Dec 2026). The rules require a runtime NVIDIA open model on Nebius, a public
  licensed repo, a working demo, a public video under 3 minutes and the Devpost form.

---

## 1. What it is, in one paragraph

Open Apprentice learns a visual layout rule from **one demonstration**. It applies the rule to new documents in **real
graphics engines**, and it **asks one question** when the example is genuinely ambiguous instead of guessing. Every
result is **proven by an independent checker** before it is saved. NVIDIA Nemotron (on Nebius Token Factory) proposes,
but deterministic checks decide. When the model's output fails a check, the product falls back to a labelled baseline
and says so on screen.

There are two product lanes:

1. **Campaign lane (newest, the video's focus).** A 16:9 promo banner becomes a 1080×1920 vertical story card. It
   runs in Konva and Fabric.
2. **Diagram lane (the original product).** Teach where notes go on one real `.drawio` diagram, then apply that to a
   hundred more.

---

## 2. End to end: what a user does

### 2a. Campaign lane: banner to story card (demo tab "Campaign")

1. **Teach once.** *Learn this layout* shows one example: a layered 16:9 headphone banner (logo, product image,
   headline, price, CTA button, legal line) and the 1080×1920 story card made from it. The system learns the rule by
   **search**, with no model involved: for each layer *role*, it learns where the layer goes and what size and style
   it takes. Pixel positions are not memorised.
2. **Reuse.** Pick another banner. The rule runs as a restricted procedure inside a real engine (**Konva** or
   **Fabric**, chosen by the user). The result is shown only if an **independent verifier** passes it. The verifier
   has 15 named checks, for example: exact copy, link preserved, logo preserved, image aspect, not cropped, focal point
   visible, safe areas, minimum sizes, text fits (measured from the font tables), no overlap, and matches the
   expected output. The page shows "15 of 15 checks passed".
3. **The question.** A long German headline does not fit the card. The system does not squeeze or overflow it.
   Instead it **stops** and shows **two fully rendered outcomes**: *shrink the product image* or *split across two
   cards*. Each is marked "fits" or "does not fit". There is also *Neither (leave unchanged)*. The question is worded
   either by Nemotron (only if every number and element in its wording matches the measured facts) or by a template,
   and the page says which.
4. **Preference.** The answer is saved as a **versioned preference per language**. The next long German banner is
   handled without asking, and the preference can be rolled back. Another language asks again.
5. **Untagged banners.** A banner can arrive without role tags. **Nemotron-3-Super proposes the roles live.** It sees
   the layers with their names hidden behind opaque ids (L1…L7) in a hashed order, so ids cannot give the roles away.
   A deterministic checker rejects impossible mappings, for example: font sizes must run headline > price > legal, the
   price must contain a currency sign, and the product image must be larger than the logo. A rule-of-thumb heuristic
   is the fallback. The **owner confirms** the mapping before anything runs.
6. **Second engine.** Switch to Fabric and the same learned rule runs unchanged through the same sandboxed procedure.
7. **Native procedures (off in production).** Nemotron can also write the native procedure for each engine. It is
   accepted only if the verifier passes it on one seen banner and two unseen ones. It works, but it is switched off on
   the public demo for cost reasons (see §4).

### 2b. Diagram lane: real `.drawio` files (demo tab "Apprentice", the default)

1. **Bring diagrams.** Import `.drawio` files, or use samples or the 100-diagram library. The **real draw.io viewer**
   renders each one in a locked, offline headless Chromium and measures every box. The apprentice matches each note
   to the box it describes, and the user confirms.
2. **Show it once.** Drag the notes on one diagram to where they belong. Every move is re-rendered by the engine.
3. **Watch it think.** Nemotron proposes candidate rules as small programs in an exact-arithmetic rule language, and
   these are unioned with a bounded symbolic search. Each candidate is replayed against the demonstration. If several
   still fit, the apprentice searches (with Z3) for a **test diagram on which they disagree**, renders each outcome,
   and asks one question with a picture of each answer. A side panel shows all of this.
4. **Preview, then commit.** The rule is previewed on unseen diagrams. A diagram it would break is shown as blocked and
   cannot be approved. The rule is then stored as a **versioned skill**.
5. **Reuse everywhere.** Apply the skill to the whole library in one click, then to a 217-object platform map.
   - Each edit is a **byte-exact patch of the note x/y only**.
   - Before publishing, the file is re-parsed, re-rendered and measured.
   - Three separate checks must pass: conformance to the rule, preservation of everything else, and layout safety.
   - You can download the `.drawio`, an SVG or a receipt.
6. **Correct it.** Nudge a result. The apprentice asks whether you meant to change the skill, keep a one-off override,
   or undo a mistake.

There are limits: teaching works on pages of up to 32 objects, and applying a skill works on up to 400 objects and 200
notes.

### 2c. Older lanes, still in the app

- **Earlier prototype:** badge placement on UI cards across Konva and Fabric, including a silent "tool change" and a
  binding-only repair.
- **Real SVG:** apply a taught rule to SVG files as byte-exact patches.
- **NeMo Gym environment** (`gym/`): a "calibrated asking" task for NVIDIA NeMo Gym.

---

## 3. Metrics (everything measured, including what is unflattering)

### 3a. Campaign lane

| What | Result | Source |
|---|---|---|
| Same rule on Konva and Fabric, development fixtures | **16 / 16** verifier rows pass | `docs/evaluation/campaign_parity.md` |
| **Sealed held-out set**: 8 new banners, 4 new languages (es, nl, pl, it) | **22 / 22** rows pass on both engines | `docs/evaluation/campaign_sealed.md` |
| Asks exactly when it should, on the sealed set | **16 / 16** banner × engine cases (no question on 3 short banners; question on 5 long ones; on the 2 extra-long ones "shrink" is correctly marked *does not fit*) | same |
| Nemotron role proposals (live, opaque ids) | **6 / 6** correct, but a simple heuristic is also 6/6, so **no gain is shown** | `docs/evaluation/campaign_nemotron.md` |
| Nemotron wording of the overflow question | **0 / 3** passed the strict fact check in the measurement, so the template was shown. (In one later live recording the wording did pass, so acceptance varies from run to run.) | same |
| Nemotron-written native procedures | Accepted on both engines (Konva on attempt 1, Fabric on attempt 2). They follow the prompt's input contract almost verbatim, which shows **contract-following, not procedure design**. | same |
| Live measurement spend (4 runs) | $0.358 in the ledger (the latest run alone $0.255, mostly two cut-off procedure calls) | `docs/evaluation/campaign_nemotron.md` |

**Caveats on the sealed set** (stated in its doc):
- It was written by a fresh AI agent that saw only the written rules and format examples, never the code. It was not
  written by the owner, and that agent is the same model family that built the system.
- Its hashes were committed before the run.
- The cases are clear-cut: every headline is at least half a line from a wrap boundary.
- Font sizes match the teaching example.
- It tests correct application of the rule to new copy, languages and positions. It does not test learning a new
  layout.

### 3b. Diagram lane: frozen, pre-registered evaluation (Nemotron-3-Ultra)

The setup:
- 36 synthetic label-placement episodes × 3 repeats, 240 runs, with live Nemotron.
- Spend: $41.4 in the ledger, about $47 real.
- The learner runs in an isolated process that cannot read the answers (0 boundary violations), and an independent
  oracle scores it.
- Source: `docs/evaluation/final_results.md`.

| Question | Apprentice (asking policy) | Same model acting freely |
|---|---|---|
| Learns the rule (16 × 3) | 22/48 | **28/48** |
| Corrects a wrong result end to end (12 × 3) | 18/36 | **22/36** |
| Refuses when inconsistent/unsupported | **18/24** | 9/24 |
| Surfaces a conflicting demonstration | **12/12** | 6/12 |
| Ambiguous demonstrations (must ask) | **2/12** | 0/12 |
| Identifiable rules (no question needed) | 7/12 | **12/12** |
| Cost per run | **$0.17** | $0.26 |
| Wrong commits (of 108 runs each) | 3 | 3 |

**What this means:**
- The pre-registered hypothesis, that asking beats the same model acting freely, is **not supported**: both primary
  endpoints point the other way, and neither difference is distinguishable from zero.
- The apprentice wins where stopping matters (conflicts, unsupported tasks, ambiguity) and on cost.
- It loses on easy rules because it gives up after its proposal rounds.
- 94.5% of the programs it committed were correct on fresh documents.
- A v2 policy was tested against a rule fixed in advance, failed it, and was **not adopted**
  (`docs/evaluation/policy_v2_dev_check.md`).

### 3c. Other measured results (development split, small samples)

- **Model alone vs hybrid:**
  - The model alone committed to a wrong rule 15 of 34 times (44%).
  - Unioning its proposals with a bounded symbolic search cut that to 1 of 20 (5%).
  - On six rules outside the search's grammar: search alone 0/12, model alone 5/12 (2 confident-wrong), hybrid 5
    committed, all correct.
- **Compound conditional programs** (`docs/redesign_gate.md`):
  - Frozen gate set: 15/15 in two runs.
  - Held-out 24 episodes: 8/8 unambiguous, 8/8 ambiguous (asked, then committed).
  - One wrong commit on a noisy demonstration.
- **Product model choice** (`docs/evaluation/product_model_check.md`): Super runs the live site.
  - Median session about 22 s vs about 58 s for Ultra, at roughly a tenth of the cost.
  - Super: 2/3 sessions succeeded, with one abstention. Ultra: 3/3.

### 3d. Engineering

- **Tests:** 1,523 Python tests (unit, integration, contracts, evaluation) and 85 engine tests (Konva and Fabric in
  real Chromium), plus browser end-to-end journeys.
- **CI:** GitHub Actions on Python 3.12: lint, import contracts, web build, engine, browser.
- **Clean-clone check:** the README setup steps were re-run from a fresh clone on 22 Oct and all passed.

---

## 4. How Nemotron is used (and where it is not)

| Job | Model | In production? | Gate |
|---|---|---|---|
| Diagram lane: propose rule programs | Nemotron-3-Super (live site), Ultra (evaluation) | Yes, under a durable dollar cap and 3 live sessions per visitor per hour | Replayed against the demonstration; unioned with symbolic search; the teacher decides |
| Campaign: propose layer roles | Nemotron-3-Super | Yes | Deterministic role checker, then owner confirmation; heuristic fallback |
| Campaign: word the overflow question | Nemotron-3-Super | Yes | Strict fact check (every number, element and polarity); template fallback |
| Campaign: write native procedures | Nemotron-3-Super | **Off** (`CAMPAIGN_MODEL_PROCEDURES` unset) | Verifier on 1 seen + 2 unseen banners; reference fallback |

**Why procedures are off:** Super's hidden reasoning is not bounded by `max_tokens`. One procedure request ran about
35k reasoning tokens (about $0.11 per call, about $0.25 per request with two attempts), and the measured result shows
contract-following rather than design.

**Cost controls:**
- Model mode is off unless `DEMO_MODEL_ENABLED=1`.
- The diagram lane has a durable dollar cap shared by all instances.
- The Campaign lane has a per-instance cap and 6 requests per address per hour. This is a **known gap**: it is not on
  the durable ledger.
- When the cap is reached, the page says so and offers the offline learner or the recorded REPLAY. It never silently
  downgrades.
- The Nebius balance is $12.26, with a $10 reserve kept for judging.

---

## 5. Architecture, tools and frameworks

```
Browser (React + TypeScript, Vite)
   │  HTTPS
   ▼
FastAPI (Python 3.12, Pydantic 2)  ── Nemotron via Nebius Token Factory (OpenAI-compatible API, JSON mode)
   │   ├─ learner: search + model proposals → rule programs (exact-arithmetic JSON AST)
   │   ├─ restricted JSON-AST interpreter (no eval/exec; model output is data, never code)
   │   ├─ Z3 witness search (finds the test case where candidate rules disagree)
   │   ├─ independent verifier (separate geometry code; never calls the agent's measure tool)
   │   └─ event-sourced, hash-chained teaching ledger; versioned skills and preferences
   ▼
Engine service (Node 22 + Playwright) → locked, offline headless Chromium running
   the real draw.io viewer, Konva 9.3.22 and Fabric 6.9.1 (vendored fonts and assets)
```

- **Languages:** Python 3.12 (uv, black, ruff, import-linter), TypeScript (ESLint, Prettier), Node 22.
- **Backend:** FastAPI, Pydantic 2, SQLAlchemy 2, z3-solver, fontTools (independent text measurement), httpx.
- **Frontend:** React, TypeScript, Vite.
- **Engines:** Playwright + Chromium; draw.io viewer, Konva, Fabric.js.
- **Model:** NVIDIA Nemotron-3-Super (`nvidia/nemotron-3-super-120b-a12b`) and Nemotron-3-Ultra
  (`nvidia/Nemotron-3-Ultra-550b-a55b`) on Nebius Token Factory.
- **Cloud:** Google Cloud Run (gen2, 1 CPU, 2 GiB, max 1 instance), Cloud Storage (state), Cloud Tasks with OIDC
  (long steps), Cloud Build + Artifact Registry, Secret Manager (API key), a GCP budget alert. The current revision is
  `open-apprentice-00032-dux`, and the previous one remains available for rollback.
- **Video:** Remotion; a Playwright screencast of the real public demo; Kokoro-82M (offline TTS) for narration.
- **Other:** NVIDIA NeMo Gym environment (`gym/`); Docker Compose for local use.

**Trust rules enforced in code:**
- Agent-visible code can never import the evaluator. This is checked by `lint-imports` in CI.
- There is no `eval`/`exec` anywhere.
- The verifier shares no geometry code with the engine.
- The four evidence axes (intent, symbolic, native, held-out) are reported separately, with no single combined score
  or "Verified" badge.
- Private evaluation sets live in a git-ignored folder; only their hashes are committed.

---

## 6. Timeline: what was built, in order

1. **Prototype:** badge placement on UI cards, Konva + Fabric, silent tool change and binding repair, independent
   verifier, evidence packages that can be re-checked offline.
2. **Research line:** a label-program language, Z3 witness search, live Nemotron pilots, the hybrid (model + search)
   result, compound conditional programs.
3. **Diagram product:** real `.drawio` import and render, show once, ask, preview, byte-exact patching, the 100-diagram
   library, the 217-object map, deployment on Cloud Run with a durable cap.
4. **Frozen evaluation:** 240 live Ultra runs, results published as they came out, including the negative primary
   result.
5. **Campaign lane (Plans 9A–9E, 22 Oct):**
   - scene model and verifier;
   - learning and the overflow question;
   - API and web tab;
   - Fabric parity and the sealed-set tooling;
   - Nemotron for roles, wording and procedures, with live measurement.

   Each plan was test-driven and reviewed by a fresh reviewer before merge.
6. **22–23 Oct:**
   - Campaign deployed to production.
   - Sealed set authored, sealed and run (22/22).
   - Video rebuilt around Campaign.
   - Two production bugs found while making the video, fixed with tests and redeployed: result images were cropped to
     the banner's 16:9 area, and the role table showed every role as "background".

---

## 7. Known gaps and open risks

- **The Campaign lane is development-stage:**
  - One product template (the Halden headphone banner) and 7 fixed roles.
  - Only the vendored font and two vendored assets.
  - Story geometry is fixed per role.
- **The sealed set is agent-authored, not owner-authored**, and avoids borderline cases.
- **Nemotron's measurable added value in Campaign is small:**
  - Roles tie a heuristic.
  - Wording usually fails the fact check.
  - Procedures are off.

  The model's clearest value is in the diagram lane's hybrid result, and that is on small development samples.
- **On the diagram lane's frozen evaluation, the asking policy does not beat the same model acting freely on learning.**
- **The Campaign spend cap is per instance**, not on the durable ledger.
- **Text measurement differs slightly between macOS and Linux Chromium near wrap boundaries.** The cross-check
  compares fit verdicts, not line counts (`docs/decisions.md` #61).
- **The ledger runs about 11% below real spend.**
- **Not built:** a skill inspector, entering a corrected example after "Neither", model-written SVG patches, and
  Campaign templates beyond the one banner family.

---

## 8. Where to look in the repo

| Topic | File |
|---|---|
| Setup and summary | `README.md` |
| Devpost text | `docs/submission.md` |
| Current state, how to run, rollback | `docs/HANDOFF.md` |
| Every design decision and deviation | `docs/decisions.md` |
| Running test log | `docs/status.md` |
| Frozen evaluation | `docs/evaluation/final_results.md` |
| Campaign: parity / Nemotron / sealed | `docs/evaluation/campaign_parity.md`, `campaign_nemotron.md`, `campaign_sealed.md` |
| Campaign design spec | `docs/superpowers/specs/2026-10-22-promo-story-card-design.md` |
| Submission checklist | `docs/submission_checklist.md` |
| Claims and limitations | `docs/claims_and_limitations.md` |

---

## 9. Questions we would like the reviewer to answer

1. Is the Campaign lane a convincing "agent" story for a judge, or does it read as a scripted layout tool with a model
   attached?
2. Given that Nemotron's measured gain in Campaign is small, how should the submission frame the model's role without
   overselling it?
3. Is leading the video with Campaign (and giving the diagram lane one beat) the right call?
4. What is the single most valuable improvement possible before 30 Oct, given about $2 of spendable model credit?
5. Are any claims above stronger than their evidence?
