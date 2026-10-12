# HANDOFF — read this first (written 2026-10-12; updated at the end of the second 2026-10-12 session)

You are continuing **Open Apprentice**, a solo project for the **Nebius x NVIDIA Global AI Hackathon**. **Deadline: 31 Oct 2026 01:00 SGT** (about 18 days from this note).
The owner is **Aryan Ganju** (rajeevganju0@gmail.com; NUS CS: AI + DB Systems). Authoritative spec: `Open_Apprentice_Claude_Code_Build_Spec.md` (v1.3, 2597 lines). Short operational pointers are in `.claude/CLAUDE.md`.
Living logs you must keep honest: `docs/status.md` (what works / what was tested), `docs/decisions.md` (numbered deviations and results, #1–#48), `README.md`.

Repository state: git, branch `master`, clean tree, **private GitHub repo `AryanG01/open-apprentice`** (`origin`, pushed once at `ce336de`; later local commits are NOT pushed until the owner asks: `git log origin/master..` shows them). Tests: **371 Python (`OA_ENGINE_TESTS=1 pytest -q tests`) + 21 Node pass**.
Deployed: only a **static preview** (HF static Space `AryanG01/open-apprentice-static`, built before the two web fixes below, so it needs a rebuild and re-push). **No live backend is deployed anywhere** (see "Open work").

**What changed in the second 2026-10-12 session (all committed locally):** (1) **Replay mode** (decisions #49): one real Nemotron session recorded to `docs/replay/nemotron_tape.json` and served free, labelled REPLAY; public ceilings tightened. (2) Browser check found and fixed a **pre-existing bug that blanked the whole "Try it live" tab** whenever the backend was up (a hook after early returns, React #310, from the SVG-lane commit). (3) The static copy now says plainly that live tabs are unavailable. (4) **Hugging Face Docker Spaces are NOT free any more** (402 Payment Required; PRO ~$9/month); the old plan is dead. (5) Docker image built and measured: memory is fine (512 MiB), **CPU is the constraint** (details in section 8 and docs/deploy.md).

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
Other facts: ~10–15% of model trials end in `TruncatedOutput` (reasoning runaway) even at a 32k completion floor; Nemotron-3-Ultra at `reasoning_effort=low` is the chosen model (Super was much worse); native-action allowance raised 24→48 and episode caps to 300k tokens/120 calls (decisions #33–#35); interpreter depth 4→8 (#34).
**Honest limits to keep stating:** the reference learner's grammar was built knowing the benchmark's rule families (it shows tasks are solvable inside a grammar, not "understanding"); hybrid's search keeps only the simplest few behaviours that fit the demo, so a harder in-grammar rule can lose (#45);
the live demo is **one concept (badge) and one scene family**; spacing/composition exist only in the evaluation harness; the SVG lane is experimental (no matched baseline pilot, no model-written patches); mypy has 84 dict-typing errors (decisions #43); phone layout, screen readers, Firefox/Safari unchecked.

## 7. Money (very tight — read `~/.claude/projects/-Users-aryanganju-Desktop-Code-Nvidia/memory/live-run-cost.md`)
Owner-reported balance: $21.14 → $19.95 → $6.96 → $4.94 → **$2.57** (2026-10-12); one ~$0.09 replay recording after that, so about $2.48 (unconfirmed; ask). Below the $3 reserve: do NOT run live Nemotron experiments; the replay tape exists so the public demo never needs the model. Cost per token is **not constant**: input-heavy runs ~$0.57/M, output-heavy reasoning runs **~$3–4/M**. I once under-estimated a run by 8× — estimate from the ledger's usd (rates in `.env`: 1 and 3 $/M, owner-entered, unverified) or assume ~$3.5/M, always pass a global ceiling (`--max-total-tokens`), keep **≥ $3 in reserve** for the live demo/recordings, ask for the balance after any big run. Owner said low-credit experiments are fine and they can top up if truly needed, but "be careful".
Measured: a full Nemotron demo session costs ~$0.09–$0.28; 24 teaching trials ≈ $1.5–2.

## 8. Open work, in priority order
1. **A live backend host (blocked on the owner, no deadline pressure yet).** The Hugging Face Docker plan is dead (402; Docker Spaces need PRO, ~$9/month, owner has not approved paying). Measured on the Docker image (`docker build -f docker/demo.Dockerfile -t open-apprentice-demo .`, 2.47 GB on disk):
   unlimited 205 MiB idle / 335 MiB peak; **512 MiB + 1 CPU passes everything**; 0.5 CPU fine (replay flow 5 s); 0.25 CPU fine (13 s); **0.1 CPU breaks it** (start 18 s, then the symbolic search times out, `solver status=incomplete`, session ends UNRESOLVED: results depend on CPU because the solver runs on a wall-clock budget).
   So: Render/Koyeb free (0.1 CPU) are out. **Plan in progress: Google Cloud Run** (1 vCPU, 512 MiB-1 GiB, `--max-instances=1`, scale to zero, free monthly allowance; needs an OPEN billing account = a card). Owner's billing account `019589-14D134-77B39F` is CLOSED; they emailed Google support to reopen it. Blocked until then. When open: owner sets a ~$1 budget alert; agent creates a dedicated project (e.g. `open-apprentice-demo`, ask first),
   re-checks Cloud Run's current free-tier numbers on cloud.google.com/run/pricing (the figures in the search were 2025-era), asks the owner to approve the first deploy, deploys the same image in reference + replay mode (no Nebius key, so no spend), verifies `/health/ready` and a full flow on the live URL with `scripts/live_flow_check.py --mode replay --base <url>`, and notes the cold start. Alternatives if it fails: Oracle Always Free (capacity unreliable), HF PRO, or a Cloudflare Tunnel from the owner's laptop during judging.
2. **Refresh the static preview.** `dist/hf-static` was built before the TryIt hooks fix and the static-copy wording fix. Rebuild (`cd apps/web && ../../node_modules/.bin/vite build`, copy `apps/web/dist/.` into `dist/hf-static/`, keep its `README.md` with `sdk: static`), then the owner runs `! cd .../dist/hf-static && git add -A && git commit -m ... && git push space HEAD:main` (one command per `!` message). The Space is public at https://huggingface.co/spaces/AryanG01/open-apprentice-static.
3. **GitHub.** Repo is private. Push the local commits when asked (`git push`). **Before the deadline the owner must make it public** (`gh repo edit AryanG01/open-apprentice --visibility public --accept-visibility-change-consequences`) unless the hackathon accepts private access; re-run the secret scan first (every `.env` secret value was absent from all history on 2026-10-12).
4. **Video** (<=3 min): run-of-show in `docs/demo_script.md`; must show only real behaviour (label REPLAY as a replay). The owner records it. Do not claim the method beats baselines.
5. **Submission polish:** re-read README for accuracy; verify a fresh `git clone` + README steps again after big changes (passed once earlier); commit final UI data after any new result.
6. **Optional (time/credit permitting; credit is the limit):** add ESLint `react-hooks/rules-of-hooks` (no lint caught the blank-tab bug); browser-test Repair, Break and export in the UI (only teach/answer/seal/run were driven); matched baseline pilot for the SVG lane (spec 21.12); "Neither -> enter a corrected example" in the UI (currently an honest dead end); `docker compose` (db/worker/web) untested, worker not implemented; reduce `TruncatedOutput`; LangSmith opt-in tracing (key set, nothing wired); mypy debt; phone-width, Firefox/Safari and keyboard/screen-reader audits.
7. **Never done and must not be faked:** the locked final study (spec 27.5 gates NOT evaluated on any dev result); final split untouched; no user study (benchmark teacher answers are scripted); no live-vs-baseline comparison with confidence intervals; **no live Nemotron result may be claimed from replay** (replay shows one recorded run; it contains no model repair because the model's procedure survived the tool change).
8. **Replay limits to keep stating:** one tape, one demonstration (default badge position); matching is byte-for-byte on role + messages, so a different teaching answer can still match when the model's prompt would be identical (verified in a browser: answering B then A sealed a different rule, "15% of height", and the recorded procedure was re-checked live and passed). Token counts in the replay meter are from the original run, cost shows $0.

## 9. What I would do first in the next session
1. Read this file, `docs/status.md` (tail), `docs/decisions.md` #44-#49 and the cost memory note. Run `OA_ENGINE_TESTS=1 PYTHONPATH=src:. .venv/bin/pytest -q tests` (needs Chromium, run unsandboxed; expect 371) and the Node tests (21).
2. Ask the owner: (a) has Google reopened the billing account (`gcloud billing accounts list`, OPEN must be True)? (b) current Nebius balance; (c) push local commits to GitHub? (d) approve the static Space refresh commands.
3. If billing is open: follow item 1 above (dedicated project, budget alert, approval before the first deploy). If not: do the static refresh, the video prep and the README re-read, and keep the Docker image numbers handy.
4. Verify every UI claim in headless Playwright, not by reading code. Update README/status/decisions, commit (`&&` after tests), and tell the owner exactly what is verified vs unverified.

## 10. Where the truth lives
Numbers → `results/` (stored trial JSON, run `rows.jsonl`) and `scripts/analyze_audit_experiment.py`; UI numbers are generated from them. Deviations → `docs/decisions.md`. Tested vs untested → `docs/status.md`. Cost lessons → memory note. If this file and those disagree, trust them and fix this file.
