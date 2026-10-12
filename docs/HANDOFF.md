# HANDOFF — read this first (written 2026-10-12, end of a very long session)

You are continuing **Open Apprentice**, a solo project for the **Nebius x NVIDIA Global AI Hackathon**. **Deadline: 31 Oct 2026 01:00 SGT** (about 18 days from this note).
The owner is **Aryan Ganju** (rajeevganju0@gmail.com; NUS CS: AI + DB Systems). Authoritative spec: `Open_Apprentice_Claude_Code_Build_Spec.md` (v1.3, 2597 lines). Short operational pointers are in `.claude/CLAUDE.md`.
Living logs you must keep honest: `docs/status.md` (what works / what was tested), `docs/decisions.md` (numbered deviations and results, #1–#48), `README.md`.

Repository state: git, branch `master`, **28 commits, clean tree** (last: `7eb743e`). Tests: **369 Python + 21 Node pass** (see "How to run"). Nothing is deployed permanently yet (see "Open work").

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
PYTHONPATH=src .venv/bin/python -m uvicorn open_apprentice.api.app:app --port 8000   # whole product at http://localhost:8000 (serves apps/web/dist)
DEMO_MODEL_ENABLED=1 DEMO_MODEL_MAX_USD=2 ...same...                          # adds capped Nemotron mode (needs .env key)
PYTHONPATH=src:. .venv/bin/python scripts/build_demo_bundle.py               # regenerate UI data (needs Chromium); then rebuild web
scripts/make_hf_space.sh dist/hf-space                                       # Hugging Face Space folder (dist/ is git-ignored)
```
Use `python -m open_apprentice.cli <cmd>` (the bare `oa` script breaks when macOS re-hides the editable `.pth`; `chflags nohidden .venv/lib/python3.13/site-packages/*.pth` fixes it). Live commands: `learn`, `learn-oog`, `compare`, `report`, `replay-evidence`, `provider probe`, `doctor`.

**Environment gotchas (cost real time this session):**
- Anything needing Chromium, `git add/commit` (writes `.git`), Docker, npm/PyPI, or Nebius needs `dangerouslyDisableSandbox: true`. Host Python is 3.13 (project targets 3.12 via uv), host Node is 25 (containers pin node:22).
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
  providers/  base.py (Provider, completion_floor, aclose), nebius.py, mock.py, factory.py, capabilities.py (live probe), budget in ../budget.py
  evaluation/ verifier.py (INDEPENDENT), harness.py, runner.py, pilot.py (learn trials, oog trials, compare), episodes.py, oog.py, replay.py (offline evidence replay), report.py, metrics.py
  api/        app.py (lifespan, static web, headers), teach.py (live demo API), svg.py (SVG lane), svg_export.py, geometry.py, fixtures.py (scripted bindings, origin=fixture)
  svg/        safety.py (validator), document.py (byte-exact editing + inventory), patch.py (typed whitelisted patch), rule_apply.py, samples/*.svg (3 owner-authored assets + NOTICE.md)
services/engine/   Node + Playwright, real Konva and Fabric in a network-blocked Chromium; evaluator-only drift; /internal/svg/measure (browser-measured SVG world geometry)
apps/web/          React + TS + Vite: Home, recorded walkthrough (Learn/Reuse/Transfer/Challenge), Compare, Try it live (TryIt.tsx, DemoCanvas.tsx), Real SVG (SvgLane.tsx)
docker/demo.Dockerfile   single-container demo (API + web + engine); deploy/ + scripts/make_hf_space.sh for Hugging Face
```
Data flow for the UI: `scripts/build_demo_bundle.py` writes `apps/web/public/data/{demo,evidence}.json` from real engine runs and stored `results/` (not hand-typed). `tests/unit/test_ui_data.py` fails if the committed UI data drifts from `results/`.

## 5. Live-demo API (what judges will use)
`POST /api/teach` (`mode: reference|nemotron`, optional `demonstration`), `/answer`, `/run`, `/break` (40-input stress test), `/repair`, `/export.svg`, `/evidence.json`; `POST /api/replay` (offline package check);
`GET/POST /api/svg/{samples,inspect,apply,harmful-demo}`; `/health/live`, `/health/ready`. Safety: Nemotron mode **off unless `DEMO_MODEL_ENABLED=1`**, global cap `DEMO_MODEL_MAX_USD` (default 2), per-session 250k tokens/40 calls,
per-client limits (60 free, 8 model, 120 svg sessions/hour), security headers, in-memory sessions (max 20, TTL 30 min). Nemotron mode = **hybrid** (model proposals ∪ bounded symbolic search); a failed model call degrades to search-only and says so;
a failed model *native procedure* is replaced by a **labelled scripted fixture**. Scripted bindings carry `origin="fixture"` everywhere.

## 6. Results so far (all development split, small n — never claim more)
| Experiment | Result |
|---|---|
| Five-method pilot, dev eps 3–5 (reference / full_v1_2 / fresh / text_memory / structured) | reference 24/24; every model method commits wrong output often (full_v1_2 5 of 8 commits wrong). NOT a comparison. |
| Model alone (control), 48 trials | 34 committed, **15 wrong = 44%**, 9 abstained |
| Model + audit round | 10 committed, 4 wrong (40%), **30 abstained** — audit did NOT help (decisions #44) |
| **Hybrid** (model ∪ symbolic search), 24 trials | 20 committed, **1 wrong = 5%**, 3 abstained (decisions #46). Does NOT prove model value (search alone also solves these) |
| **Out-of-grammar battery** (6 rules search cannot express, 2 reps) | search 0/12 correct; model 5/12 (2 confident-wrong); hybrid 5 committed, **0 wrong** (11 trials; ceiling skipped 1). **First real evidence of model value** (decisions #47) |
Other facts: ~10–15% of model trials end in `TruncatedOutput` (reasoning runaway) even at a 32k completion floor; Nemotron-3-Ultra at `reasoning_effort=low` is the chosen model (Super was much worse); native-action allowance raised 24→48 and episode caps to 300k tokens/120 calls (decisions #33–#35); interpreter depth 4→8 (#34).
**Honest limits to keep stating:** the reference learner's grammar was built knowing the benchmark's rule families (it shows tasks are solvable inside a grammar, not "understanding"); hybrid's search keeps only the simplest few behaviours that fit the demo, so a harder in-grammar rule can lose (#45);
the live demo is **one concept (badge) and one scene family**; spacing/composition exist only in the evaluation harness; the SVG lane is experimental (no matched baseline pilot, no model-written patches); mypy has 84 dict-typing errors (decisions #43); phone layout, screen readers, Firefox/Safari unchecked.

## 7. Money (very tight — read `~/.claude/projects/-Users-aryanganju-Desktop-Code-Nvidia/memory/live-run-cost.md`)
Owner-reported balance: $21.14 → $19.95 → $6.96 → **$4.94** (2026-10-12). Cost per token is **not constant**: input-heavy runs ~$0.57/M, output-heavy reasoning runs **~$3–4/M**. I once under-estimated a run by 8× — estimate from the ledger's usd (rates in `.env`: 1 and 3 $/M, owner-entered, unverified) or assume ~$3.5/M, always pass a global ceiling (`--max-total-tokens`), keep **≥ $3 in reserve** for the live demo/recordings, ask for the balance after any big run. Owner said low-credit experiments are fine and they can top up if truly needed, but "be careful".
Measured: a full Nemotron demo session costs ~$0.09–$0.28; 24 teaching trials ≈ $1.5–2.

## 8. Open work, in priority order
1. **Owner decision pending: replay mode + tighter ceilings.** Plan: record ONE real Nemotron session (~$0.25) into a fixture and serve it as a clearly labelled **REPLAY (recorded <date>)** when the model cap is exhausted or Nemotron mode is off — so judges see the model at $0. Valid only for the default demonstration (disable custom placement in replay). Also lower public ceilings to ~120k tokens/24 calls per session and 3 model sessions/client/hour; public cap ≈ $1.5.
2. **Permanent live deployment (owner approved).** Recommended free host: **Hugging Face Space (Docker, CPU Basic: 2 vCPU/16 GB, sleeps after 48 h idle)**. The Space folder generates with `scripts/make_hf_space.sh` and **was built and run locally as UID 1000 on port 7860; layout flow and SVG lane pass**. Steps are in `docs/deploy.md` §3.
   The owner must run `! hf auth login` (first characters of a message; token typed in the terminal, **never in chat**). Then: create the Space, push, set Space variables/secret (list in deploy.md), **verify the live URL end to end**, and schedule a free keep-alive ping (GitHub Actions cron) for the judging window. Unverified until the first real HF build: build memory limits and Chromium on HF's runtime. Fallbacks: the static Vercel link, Oracle Always-Free ARM (cut in 2026; capacity issues).
   Public default: reference mode only; Nemotron mode only with a small cap.
3. **Static fallback link** (Vercel): a temporary anonymous deployment was **claimed by the owner** (60-minute expiry would have applied otherwise). If a permanent static copy is wanted, redeploy `apps/web/dist` after logging in (`! vercel login`); the Home/Compare/walkthrough work without a backend and "Try it live" shows a clear "needs the backend" message.
4. **Video** (≤3 min): run-of-show is in `docs/demo_script.md`; must show only real behaviour; the owner records it. Do not claim the method beats baselines.
5. **Submission polish:** README is accurate (re-read it before submitting); commit the final UI data after any new result; verify a **fresh `git clone` + README steps** again after big changes (it passed once: uv sync, npm ci, playwright, build:web, tests, lint-imports).
6. **Optional research/product items (only if time/credit allow):** matched baseline pilot for the SVG lane (spec 21.12) and Nemotron-written SVG patches; spacing/composition in the live demo; "Neither → enter a corrected example" in the UI (currently an honest dead end); `docker compose` (db/worker/web) is untested and the worker command is not implemented — not the demo path; reduce `TruncatedOutput` (retry/adjust); LangSmith opt-in tracing of Nemotron calls (key is set, nothing wired); mypy debt; phone-width check; keyboard/screen-reader audit.
7. **Never done and must not be faked:** the locked final study (§27.5 gates are NOT evaluated on any dev result); final split untouched; no user study (benchmark teacher answers are scripted); no live-vs-baseline comparison with confidence intervals.

## 9. What I would do first in the next session
1. Read this file, `docs/status.md` (tail), `docs/decisions.md` #44–#48, and the cost memory note. Run the test suite once to confirm the baseline (369 + 21).
2. Ask the owner for: (a) go/no-go on replay mode, (b) `! hf auth login`, (c) current Nebius balance.
3. If go: implement `ReplayProvider` (record via a wrapper around the real provider: role, raw text, usage, demonstration hash; refuse replay if the demonstration differs), UI label "REPLAY of a real Nemotron run (date)", budget-exhausted fallback, tests with the mock; record once with a hard cap.
4. Rebuild the Space folder, push once logged in, verify `/health/ready`, a full teach→run→repair→SVG pass on the live URL, and add the keep-alive.
5. Update README/status/decisions, commit (`&&` after tests), and tell the owner exactly what is verified vs unverified.

## 10. Where the truth lives
Numbers → `results/` (stored trial JSON, run `rows.jsonl`) and `scripts/analyze_audit_experiment.py`; UI numbers are generated from them. Deviations → `docs/decisions.md`. Tested vs untested → `docs/status.md`. Cost lessons → memory note. If this file and those disagree, trust them and fix this file.
