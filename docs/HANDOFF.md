# CURRENT STATE — 2026-10-16 (read this section first; the rest of the file is the 2026-10-13 snapshot)

**Direction (since 15 Oct):** the product is the teach → clarify → correct → reuse flow on real `.drawio` files, validated internally.
Spec: `docs/superpowers/specs/2026-10-15-teach-correct-reuse-design.md`. Roadmap: `docs/superpowers/plans/2026-10-15-roadmap.md`.
Owner workflow: plans written with superpowers:writing-plans, executed natively with superpowers:executing-plans (TDD, a ledger,
one opus whole-branch review, one fix pass, then "merge locally / PR / keep"). Push only when asked, after a secret scan.

**Done and merged to master (all reviewed, tests green on 3.13 and 3.12, CI green):** Plan 1 foundations, Plan 2 versions and
corrections, Plan 3 draw.io adapter and engine route, Plan 4A `/api/v2`, Plan 4C screens + browser journey (Apprentice tab;
badge demo under "Earlier prototype"), Plan 4B generated probes + Cloud Tasks with OIDC. Suite: 836 Python, 38 engine, 11 browser.

**Staging (approved, created and checked 2026-10-16):** `docs/staging_results.md` — render, GCS race, Cloud Tasks OIDC dispatch,
restart survival, forged-call refusal all pass. Resources stay up (scale to zero; bucket objects expire after 7 days); teardown in
`docs/deploy_staging_proposal.md`. Production service `open-apprentice` untouched (still the older badge build).

**Plan 5 evaluation: built offline, reviewed, merged to master 2026-10-16 (not pushed).** Plan
`docs/superpowers/plans/2026-10-16-p5-evaluation.md`; rulings and review outcomes `docs/evaluation/plan5_rulings.md`.
Frozen battery (36 final + 18 dev, battery-v2.3; final private files in git-ignored `benchmarks/final/battery/`, hashes in
`docs/evaluation/battery_final.md`), isolated learner process (teacher over inherited pipes; import/file/spawn audit hook),
systems A/B/C/D, scoring, analysis (`oa eval freeze|run|report|manifest`), offline dry run
(`results/eval_v2/dryrun-20261016/report.md`, not a model result), and the paid-run gate. Suite 945 on 3.13 and 3.12.
**Production cutover staged 2026-10-18 (traffic NOT moved):** image `demo:prod-590c34f` (master `590c34f`); bucket `oa-prod-46697f`
(versioned, no expiry), queue `oa-prod`, service account `oa-prod@…`; revisions `open-apprentice-00005-qiw` (tag `candidate`,
task target = its tag URL) and `00006-maz` (tag `final`, task target = the main URL, durable cap $5). **Live traffic is still
100% on `open-apprentice-00002-8lx` (the old badge build) = the rollback target.** The full browser journey passed against the
candidate (Cloud Tasks + GCS + engine). To cut over: `gcloud run services update-traffic open-apprentice --project
oa-demo-1013-19737 --region us-central1 --to-revisions open-apprentice-00006-maz=100` (and `--min-instances 1` for the judging
window); then run `OA_E2E=1 OA_E2E_URL=https://open-apprentice-md76de375q-uc.a.run.app node --test tests/e2e/journey.test.mjs`.
Rollback: `… update-traffic … --to-revisions open-apprentice-00002-8lx=100`.

**Funded tier ran 2026-10-17/18 on the frozen final battery** (`docs/evaluation/final_results.md`): 240 live runs, $41.4 ledger
(about $46.8 real), 0 boundary violations. **A did not beat B on either primary endpoint** (learning 22/48 vs 28/48;
correction 18/36 vs 22/36, neither distinguishable from zero). A is cheaper ($0.17 vs $0.26 per run), refuses
conflicting/unsupported cases far more often (18/24 vs 9/24) and wins the ambiguous catalogue episodes 2/12 vs 0/12 (small
n); B wins identifiable rules (12/12 vs 7/12). **Policy v2 (A2/D2: more revision rounds) was tried on development episodes
and not adopted** (`docs/evaluation/policy_v2_dev_check.md`: 5/8 against a pre-registered 6/8 bar, and twice the cost).
The 3 real-file episodes were not run (the adapter refuses the frozen final file). Money: ledger spent $87.35, owner balance
about $13 (reported $15.40 before the v2 check), ~$3 spendable above the $10 reserve; the ledger now prices output at
$3.4/M. **Next:** the production cutover (`docs/deploy_production_proposal.md`, approved by the owner in chat; no traffic
moved yet), the demo video, and the written four-axis report. No further paid evaluation is planned.
master is 26 commits ahead of origin (not pushed).

**Money:** `results/redesign/budget.json` = $50 authorized, $10 reserve; about $38.60 already spent → about **$1.40 spendable**.
Plan 5 is built offline and stops at a priced calibration manifest; no paid run without the owner's approval and a top-up.

**Local quirk:** the macOS hidden flag reappears on `.venv/.../_editable_impl_open_apprentice.pth`; run lint-imports as
`PYTHONPATH=src uv run lint-imports` (CI sets PYTHONPATH).

---

# HANDOFF — read this first (written 2026-10-12; rewritten 2026-10-13 after the improvement plan, the live deployment and the NeMo Gym work)

You are continuing **Open Apprentice**, a solo project for the **Nebius x NVIDIA Global AI Hackathon**. **Deadline: 31 Oct 2026 01:00 SGT** (about 18 days from this note).
The owner is **Aryan Ganju** (rajeevganju0@gmail.com; NUS CS: AI + DB Systems). Authoritative spec: `Open_Apprentice_Claude_Code_Build_Spec.md` (v1.3, 2597 lines). Short operational pointers are in `.claude/CLAUDE.md`.
Living logs you must keep honest: `docs/status.md` (what works / what was tested), `docs/decisions.md` (numbered deviations and results, #1–#55), `README.md`.

Repository state: git, branch `master`, **private GitHub repo `AryanG01/open-apprentice`**, everything pushed (head `5feda31` at the time of writing) and **GitHub Actions CI is green** (it runs on Python 3.12: lint, black, import contracts, web build, Node engine tests, engine-backed Python tests, browser tests).
Tests: **397 Python (`OA_ENGINE_TESTS=1 pytest -q tests`, on 3.12) + 27 Node + 9 browser (`npm run test:e2e`)**. **Run the Python tests on 3.12, not only the host's 3.13** (see `.claude/CLAUDE.md`): a `Fraction` `+` format spec worked on 3.13 and crashed on 3.12, which hid a production HTTP 500 until CI caught it.

**LIVE DEPLOYMENT (Google Cloud Run, 2026-10-13): https://open-apprentice-664860383135.us-central1.run.app** (project `oa-demo-1013-19737`, region us-central1, service `open-apprentice`, revision 00002 at the time of writing). It runs live **NVIDIA Nemotron-3-Ultra on Nebius Token Factory** by default (the hackathon requires Token Factory); the recording is only a labelled fallback when the dollar cap is reached. The Nebius key is in Secret Manager (`nebius-api-key`), never in the image or repo. Settings, cost guard (budget alert SGD 1, emails only), teardown commands and the KNOWN WEAKNESS (the global dollar cap lives in memory and resets on every cold start; the real limit is the Nebius balance) are in `docs/deploy.md` section 4. Verified on the live URL: health, a full reference flow, a full live Nemotron flow, and the site in a real browser. A real cold start has not been timed. The static HF Space (`AryanG01/open-apprentice-static`) is public but is an old build and does not link to the live demo.

**What the 2026-10-12/13 work added (all committed and pushed):**
1. **Replay mode** (decisions #49): one real Nemotron session recorded to `docs/replay/nemotron_tape.json`; labelled REPLAY everywhere (a bug that labelled it LIVE in run/evidence/SVG was fixed).
2. **Improvement plan phases A and B** (details in `docs/status.md`, decisions #50, #51): security fix (script could run in the SVG-measuring browser), engine session leaks and cap race, spend accounting, 402 on budget, interpreter overflow, hybrid cap interleaving, deterministic z3 `rlimit` solver budget (CPU speed no longer changes answers; verified at 0.1 vCPU), work moved off the event loop, CI, a blank-tab React bug, a page-width CSS bug, a misleading post-repair message.
3. **Live Nemotron is the default** in the UI (decisions #52); "Watch the story" buttons for live Nemotron, the free reference learner, and the recording.
4. **Calibrated-asking environment + NeMo Gym wrapper** (decisions #53–#55; `src/open_apprentice/evaluation/asking_env.py`, `asking_baselines.py`, `gym/`): see section 6 for results and `gym/README.md` for how to run it (separate Python 3.13.16, `vllm_model`, results come back out of order: match on `_ng_task_index`).
5. A **dedicated GCP project, Secret Manager secret, Artifact Registry repo, Cloud Build config (`deploy/cloudbuild.yaml`) and `.gcloudignore`**.

---

## 1. What the product is (one paragraph)
Teach a layout rule by **placing a badge on a card**. The system finds an input where candidate rules disagree, shows each outcome as a picture, asks the user (Neither is always allowed), **seals** the chosen rule with a hash
(rule + domain + teaching ledger), carries it to a second graphics engine (Konva → Fabric) through a **checked native procedure**, reproduces a mismatch when a tool silently changes, and **repairs only the native procedure** (rule hash unchanged).
Evidence stays on four separate axes (intent / symbolic / native / held-out); there is never a combined score or a single "Verified" badge. Layouts export as editable SVG with an **evidence package** that can be re-checked **offline**.

## 2. Non-negotiable rules (from the owner and the spec — follow them)
- Never invent numbers, hardcode a repair, expose hidden drift labels, or weaken verification. Report outcomes faithfully; **a blocked or failed check is reported as blocked or failed**. Label mock / recorded / scripted things on screen.
- Keep user intent separate from native execution. A model's own inferred rule is never its correctness oracle (the teacher decides). No `eval`/`exec`; model procedures run only through `skills/interpreter.py`.
- Agent-visible code (`agent, concepts, skills, providers, environments`) must never import `evaluation/verifier.py`, `evaluation/episodes.py` or `benchmarks/final/` (`uv run lint-imports`). **Never run the final split** before a freeze.
- The independent verifier must not use the agent-facing `measure_node` or share the engine's geometry code.
- **Secrets:** the Nebius key lives only in `.env` (mode 600, git-ignored). Never print/paste/commit it. `oa doctor` shows only `<set>`. Other keys in `.env` slots: LangSmith, Tavily, Tendem set; Toloka blank (none are used by the code; Tavily has no honest role; Tendem is a paid human-expert service — never spend it without explicit approval).
- **Permission layer:** the auto-mode classifier blocks the agent from creating public surfaces (e.g. `hf repo create`, pushing to a Space) even after the owner says yes in chat. The owner runs those as `! <command>` themselves; give exact copy-paste commands, one command per `!` message (a second `!` line inside one message does NOT run).
- Owner's global preferences: push back when they are wrong; never say "done/works" unless you ran it; check that packages/APIs exist; black + type hints; conventional commits; no `any` in TS; **commit only when asked** (they asked for commits this session and said yes to the current practice); never commit `.env`/build output.
- The owner reads terse output (a "caveman" hook is active): fragments are fine in chat, but **code, commits and docs are written normally**.

## 3. How to run things (copy-paste)
```bash
cd /Users/aryanganju/Desktop/Code/Nvidia
export PYTHONPATH=src:.
uv run pytest tests/unit tests/contracts tests/evaluation                   # offline, fast
OA_ENGINE_TESTS=1 .venv/bin/pytest -q tests                                  # + engine-backed integration (needs Chromium; run UNSANDBOXED)
(cd services/engine && node --test test/*.test.js)                           # 21 Node tests
.venv/bin/lint-imports; .venv/bin/ruff check src tests scripts; .venv/bin/black --check src tests scripts
(cd apps/web && ../../node_modules/.bin/tsc --noEmit && ../../node_modules/.bin/vite build)
npm run lint                                                                # eslint, incl. react-hooks/rules-of-hooks (1 known exhaustive-deps warning in App.tsx)
npm run build:web && npm run test:e2e                                       # 7 browser tests (tests/e2e/ui.test.mjs): tabs, learner box, replay, repair/break/export/tamper, both guided stories (+ page-size regression), static-copy wording; needs Chromium, run UNSANDBOXED
PYTHONPATH=src .venv/bin/python -m uvicorn open_apprentice.api.app:app --port 8000   # whole product at http://localhost:8000 (serves apps/web/dist)
DEMO_MODEL_ENABLED=1 DEMO_MODEL_MAX_USD=2 ...same...                          # adds capped Nemotron mode (needs .env key)
PYTHONPATH=src:. .venv/bin/python scripts/build_demo_bundle.py               # regenerate UI data (needs Chromium); then rebuild web
scripts/make_hf_space.sh dist/hf-space                                       # Hugging Face Space folder (dist/ is git-ignored)
```
Use `python -m open_apprentice.cli <cmd>` (the bare `oa` script breaks when macOS re-hides the editable `.pth`; `chflags nohidden .venv/lib/python3.13/site-packages/*.pth` fixes it). Live commands: `learn`, `learn-oog`, `compare`, `report`, `replay-evidence`, `provider probe`, `doctor`.

**Environment gotchas (cost real time this session):**
- Anything needing Chromium, `git add/commit` (writes `.git`), Docker, npm/PyPI, or Nebius needs `dangerouslyDisableSandbox: true`. Host Python is 3.13 (project targets 3.12 via uv), host Node is 25 (containers pin node:22).
- **Interactive prompts cannot run in the `!` shell (no TTY):** `hf auth login` and `gcloud auth login` must be run by the owner in a normal terminal (Terminal.app/iTerm); then verify with `hf auth whoami` / `gcloud auth list`. Tokens are never pasted in chat. Current state: **hf logged in as AryanG01; gcloud logged in as rajeevganju0@gmail.com, no project set, and the only billing account is CLOSED (owner emailed Google support to reopen it).**
- macOS has **no `timeout` command** (a script using it silently "failed" my first Docker limit tests); use `perl -e 'alarm N; exec @ARGV'`. BSD `sed -i` needs `-i ''`. Heredocs: write real newlines, not `'\n'` (I once appended a literal backslash-n to status.md).
- `hf` CLI flags on the installed version: `hf repo create <id> --repo-type space --space_sdk docker|static --exist-ok`. Space README front matter: `short_description` must be <= 60 chars and must not contain a colon (the push is rejected otherwise). A freshly created Space has a starter commit, so the first push needs `--force`.
- **Claude-in-Chrome extension is often not connected**; headless Playwright from the repo works instead (`node_modules/playwright`, scripts under the session scratchpad; copy the pattern: launch chromium, `page.getByText('Try it live', {exact:true}).click()`, read `body.innerText`, watch `pageerror`). Use it for every UI claim.
- **`black` reformats files, so scripted string `.replace()` edits silently miss** (this bit me ~6 times). After a replace, grep to confirm it applied, or edit the formatted text.
- **Never chain `git commit` after a test run with `;`** (I committed with a failing test once). Use `&&`.
- Browser automation: the first click after a page load often misses (wait ~3 s, click again); screenshot coordinates are in the displayed image's pixels; `wait` max is 10 s; the window cannot be resized, so **phone-width layout is untested**.
- The `!` prefix runs a shell command **only if it is the first characters of a user message** (the owner's `! vercel login` / `! hf auth login` attempts were on the second line and never ran).
- Long background jobs: `oa learn` formerly wrote results only at the end (now per trial). Laptop sleep stalls jobs. Monitors expire after 30 min; re-arm.

## 4. Architecture map
```
src/open_apprentice/
  concepts/   rules.py (exact-rational rule language), symbolic.py + witness.py (AST→Z3, typed witness search), teaching.py (TeachingSession),
              hypotheses.py (model candidate generation), rule_text.py (closed-grammar text front-end), enumerative.py (bounded symbolic search over a DECLARED grammar),
              hybrid.py (model ∪ search), bindings.py/transfer.py (native bindings, transfer + repair), query_selection.py, schemas.py (sealed concept, ledger)
  skills/interpreter.py   restricted JSON-AST interpreter (depth 8, 64 stmts, …)
  agent/      policies.py + synth.py (reference + 4 baselines), binding_templates.py
  providers/  base.py (Provider, completion_floor, aclose), nebius.py, mock.py, factory.py, capabilities.py (live probe), replay.py (RecordingProvider / ReplayProvider, ReplayMismatch), budget in ../budget.py
  evaluation/ verifier.py (INDEPENDENT), harness.py, runner.py, pilot.py (learn trials, oog trials, compare), episodes.py, oog.py, replay.py (offline evidence replay), report.py, metrics.py
  api/        app.py (lifespan, static web, headers), teach.py (live demo API), svg.py (SVG lane), svg_export.py, geometry.py, fixtures.py (scripted bindings, origin=fixture)
  svg/        safety.py (validator), document.py (byte-exact editing + inventory), patch.py (typed whitelisted patch), rule_apply.py, samples/*.svg (3 owner-authored assets + NOTICE.md)
services/engine/   Node + Playwright, real Konva and Fabric in a network-blocked Chromium; evaluator-only drift; /internal/svg/measure (browser-measured SVG world geometry)
apps/web/          React + TS + Vite: Home, recorded walkthrough (Learn/Reuse/Transfer/Challenge), Compare, Try it live (TryIt.tsx, DemoCanvas.tsx), Real SVG (SvgLane.tsx)
docker/demo.Dockerfile   single-container demo (API + web + engine); deploy/ + scripts/make_hf_space.sh for Hugging Face
```
Data flow for the UI: `scripts/build_demo_bundle.py` writes `apps/web/public/data/{demo,evidence}.json` from real engine runs and stored `results/` (not hand-typed). `tests/unit/test_ui_data.py` fails if the committed UI data drifts from `results/`.

## 5. Live-demo API (what judges will use)
`POST /api/teach` (`mode: reference|nemotron|replay`, optional `demonstration`; `replay` serves the recorded Nemotron session from `docs/replay/nemotron_tape.json`: free, labelled REPLAY, default demonstration only, anything not byte-identical to a recorded request gets HTTP 409 and nothing is improvised. Set `DEMO_RECORD_TAPE=path` with the model enabled to record a new tape; a tape is only valid for the exact prompts it saw), `/answer`, `/run`, `/break` (40-input stress test), `/repair`, `/export.svg`, `/evidence.json`; `POST /api/replay` (offline package check);
`GET/POST /api/svg/{samples,inspect,apply,harmful-demo}`; `/health/live`, `/health/ready`. Safety: Nemotron mode **off unless `DEMO_MODEL_ENABLED=1`**, global cap `DEMO_MODEL_MAX_USD` (default 1.5), per-session 120k tokens/24 calls (a measured full session used 32k tokens/3 calls),
per-client limits (60 free, 60 replay, 3 live-model, 120 svg sessions/hour), security headers, in-memory sessions (max 20, TTL 30 min). Nemotron mode = **hybrid** (model proposals ∪ bounded symbolic search); a failed model call degrades to search-only and says so;
a failed model *native procedure* is replaced by a **labelled scripted fixture**. Scripted bindings carry `origin="fixture"` everywhere.

## 6. Results so far (all development split, small n — never claim more)
| Experiment | Result |
|---|---|
| Five-method pilot, dev eps 3–5 (reference / full_v1_2 / fresh / text_memory / structured) | reference 24/24; every model method commits wrong output often (full_v1_2 5 of 8 commits wrong). NOT a comparison. |
| Model alone (control), 48 trials | 34 committed, **15 wrong = 44%**, 9 abstained |
| Model + audit round | 10 committed, 4 wrong (40%), **30 abstained** — audit did NOT help (decisions #44) |
| **Hybrid** (model ∪ symbolic search), 24 trials | 20 committed, **1 wrong = 5%**, 3 abstained (decisions #46). Does NOT prove model value (search alone also solves these) |
| **Out-of-grammar battery** (6 rules search cannot express, 2 reps) | search 0/12 correct; model 5/12 (2 confident-wrong); hybrid 5 committed, **0 wrong** (11 trials; ceiling skipped 1). **First real evidence of model value** (decisions #47) |
**NeMo Gym / calibrated asking (development split, small n):** scripted policies on 24 tasks (15 ambiguous, 9 unambiguous), no model: never_ask correct 0.50 (confidently wrong on 12 of 15 ambiguous), always_ask 0.92 but needless questions on all 9 unambiguous, calibrated 0.92 with asking 1.00 and economy 0.75, always_abstain 0. **Nemotron-3-Ultra via Gym, 13 of 24 tasks (partial; stopped by the $1.00 cap)**: correct 0.385, held_out 0.47, asking 0.77 (asked on all 8 ambiguous tasks, so never confidently wrong; over-asked on 3 of 5 unambiguous), economy 0.28; 5 of 13 tasks ended with neither commit nor abstain (one repeated a refused `ask` 26 times). The refusal message after the question limit has since been fixed, so a rerun is not comparable with those 13 rows. Rows: `results/gym_ultra/`, `results/asking_baselines/`. The scripted policies are NOT language-model comparisons. NeMo Gym 0.6.0 also ships an `abstention` environment (LLM-judged factual QA); only what ships in 0.6.0 was checked.
Other facts: ~10–15% of model trials end in `TruncatedOutput` (reasoning runaway) even at a 32k completion floor; Nemotron-3-Ultra at `reasoning_effort=low` is the chosen model (Super was much worse); native-action allowance raised 24→48 and episode caps to 300k tokens/120 calls (decisions #33–#35); interpreter depth 4→8 (#34).
**Honest limits to keep stating:** the reference learner's grammar was built knowing the benchmark's rule families (it shows tasks are solvable inside a grammar, not "understanding"); hybrid's search keeps only the simplest few behaviours that fit the demo, so a harder in-grammar rule can lose (#45);
the live demo is **one concept (badge) and one scene family**; spacing/composition exist only in the evaluation harness; the SVG lane is experimental (no matched baseline pilot, no model-written patches); mypy has 84 dict-typing errors (decisions #43); phone layout, screen readers, Firefox/Safari unchecked.

## 7. Money (read `~/.claude/projects/-Users-aryanganju-Desktop-Code-Nvidia/memory/live-run-cost.md`)
Nebius balance, owner-reported: $2.57 (2026-10-12) -> **$2.24** (2026-10-13). Since the $2.57 reading about 0.9M tokens went through Token Factory (a recording, three live demo sessions, a Gym smoke test, a 13-task Ultra evaluation); `.env` rates ($1/M in, $3/M out, owner-entered, unverified) price that at about $1.35 but the balance fell about $0.33, so for an INPUT-HEAVY tool-calling workload the configured rates overstate real spend about 4x (balances may lag). Output-heavy teaching runs were $3-4/M earlier: estimate per workload and re-check the balance after each run. A full live demo session is about 5 calls / 36k tokens (about $0.07-0.09 at configured rates). The Gym evaluation averaged about 58k tokens per task (range 9k-171k): a one-task smoke test (10.8k tokens) badly underestimated it. Always cap runs (the Gym run used a watcher script that kills the run at a dollar cap). Google Cloud: budget alert SGD 1 (emails only); billing account currency is SGD.

## 8. Open work, in priority order
1. **Link the live demo.** The README now links the Cloud Run URL; the static HF Space still has an old build and no link. To refresh it: rebuild `apps/web/dist`, copy into `dist/hf-static/` (keep its `README.md`), and the owner runs the push as its own `!` message (the classifier blocks the agent from publishing to Spaces; `gcloud`/`gh` public actions were NOT blocked this session).
2. **Measure a real cold start** on Cloud Run (let the instance idle ~15 minutes, time the first request) and note it in `docs/deploy.md`. Decide whether the in-memory dollar cap weakness needs a durable counter (for example Cloud Storage); the Nebius balance is the real limit today.
3. **Rerun the Gym evaluation** with the fixed refusal message (all 24 tasks, Ultra; budget the owner approves, with a spend watcher; expect roughly $0.3-1.0 real). Optional: Nemotron-3-Super / Nano (Token Factory lists `nvidia/nemotron-3-super-120b-a12b`, `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/Nemotron-3_5-Lightning`; their cost is unmeasured). Then show the result table on Home/Compare (stored-rows pattern) and in the README, with the small-n caveats.
4. **Remaining improvement-plan items** (`~/.claude/plans/ok-can-u-brainstorm-effervescent-meteor.md`): Phase D (a second live concept, spacing, in the UI/API; expected-information-gain question selection benchmarked offline); a durable spend cap; deferred cleanup (TypedDicts/mypy debt, dead code, ARIA polish).
5. **GitHub:** the repo is private; **make it public before submission** if Devpost needs it (`gh repo edit AryanG01/open-apprentice --visibility public --accept-visibility-change-consequences`), after re-running the secret scan (every `.env` secret value was absent from all history on 2026-10-13).
6. **Video** (<=3 min): run-of-show in `docs/demo_script.md` (live Nemotron on Token Factory is the model segment; replay only as a labelled backup). The owner records it. Do not claim Nemotron repaired the tool: in every live run so far its own repair attempt failed the checks and a labelled scripted fixture was promoted, or the tool change did not break its procedure.
7. **Submission polish:** re-read README for accuracy; a fresh `git clone` + README steps check after big changes; keep `docs/status.md`/`decisions.md` honest.
8. **Never done and must not be faked:** the locked final study (spec 27.5 gates NOT evaluated on any dev result); the final split is untouched; no user study (benchmark teacher answers are scripted); no live-vs-baseline comparison with confidence intervals; no claim that the method beats baselines; replay shows one recorded run (default badge position) and has no model repair.

## 9. What I would do first in the next session
1. Read this file, `docs/status.md` (tail), `docs/decisions.md` #50-#55 and the cost memory note. Run the Python tests on **3.12** (`.claude/CLAUDE.md`), `npm test`, `npm run lint`, `npm run build:web && npm run test:e2e` (need Chromium, run unsandboxed). `gh run list` should show green CI.
2. Ask the owner: current Nebius balance; the budget for a Gym rerun; whether the repo must be public for Devpost; whether to refresh the static Space.
3. Check the live service: `curl <url>/health/ready` (engine true, model available, `can_start` true) and `gcloud run services describe open-apprentice --region us-central1 --project <project>`; check the GCP budget email/alerts if the owner mentions any.
4. Verify every UI claim in headless Playwright, not by reading code. Update README/status/decisions, commit (`&&` after tests), push only when asked (secret scan first), and tell the owner exactly what is verified vs unverified.

## 10. Where the truth lives
Numbers → `results/` (stored trial JSON, run `rows.jsonl`) and `scripts/analyze_audit_experiment.py`; UI numbers are generated from them. Deviations → `docs/decisions.md`. Tested vs untested → `docs/status.md`. Cost lessons → memory note. If this file and those disagree, trust them and fix this file.
