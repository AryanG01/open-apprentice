# Status

Living log: what works, what was tested, what is limited, next action. Updated at each gate (spec 23).
A blocked live check is reported blocked, never passed.

## 2026-10-09 — M0 (Python side) done; M0 gate not yet fully met

### Toolchain (real output)
git 2.52.0 · system Python 3.13.5 · uv 0.7.13 · Node 25.6.0 · npm 11.8.0 · Docker 28.3.2 · Compose v2.39.1 · arm64.

### What works (each verified by running it)
- `uv sync` resolved and installed the locked set; `uv.lock` written. Venv is Python 3.13.5 (decisions #10).
- `oa --help` lists the full spec 24.5 surface plus v1.3 additions; `oa <group> <sub>` forms work.
- `oa doctor` (offline) reads `.env`, never prints secrets, exits 0 or 5. Verified against a real generated `.env`.
- `oa config init` generated SESSION_SECRET + POSTGRES_PASSWORD, kept DATABASE_URL consistent, wrote `.env` mode 600, idempotent, preserves user values.
- Unbuilt commands exit code 2 `NOT_IMPLEMENTED`; none fakes success.
- `pytest`: **216 passed (incl. engine-backed integration tests, opt-in via OA_ENGINE_TESTS=1; stable across PYTHONHASHSEED values) + 18 node tests** (CLI contract, config/bootstrap secrecy, protocol config invariants).
- `lint-imports`: trust-boundary contract kept. Vacuous until those packages contain code.
- `docker compose config -q`: compose.yaml valid.
- 5 protocol configs (dev, pilot, counterexample, portable, final) with spec 19.2 budgets and 8.9 domain; `final` explicitly unfrozen.

- M1 started: restricted JSON-AST interpreter (`skills/interpreter.py`) with spec 7.2 limits; 13 tests cover allowlist, refs, proto keys, div-by-zero, non-finite, statement/depth/loop/action/expression budgets, assert.
- Independent verifier (`evaluation/verifier.py`): own affine composition from raw native state; gap_row checks (existence, sizes, order, gaps, left/top, unselected unmoved, styles, canvas, no-op). Golden flat + nested-scaled scenes pass; all six spec 12.4 faults rejected; rotation rejected, not approximated. 11 tests.
- Konva engine (`services/engine`): real Konva in headless Chromium, network blocked, static allowlisted dispatcher with the 12 spec 6.4 tools, monotonic revisions + stale-write conflicts, idempotent `action_id`, owner-scoped sessions, 4-session cap, per-action deadline, evaluator-only drift config (`move_frame: world`), constant public schema hash. 8 `node --test` tests pass.
- Cross-check (`tests/integration/test_konva_fixtures.py`): the same procedure run on real Konva passes the Python verifier without drift and FAILS under the private world-frame drift. This is the reproducible semantic-change failure; fixtures come from `services/engine/scripts/gen_fixtures.js` (fixture origin, not a learned skill).
- Provider layer: `Provider` interface (strict pydantic validation, extra fields forbidden, ONE charged schema-correction, distinct truncation/refusal/auth/rate-limit/timeout/wrong-model outcomes), deterministic scripted `MockProvider` (labelled MOCK, never improvises), `NebiusProvider` (httpx; backoff + Retry-After; timeouts not auto-retried and leave an *unresolved* reservation; unknown cost stays None, never 0; error bodies redacted). Tested against an in-process fake HTTP server (16 tests). **The Nebius adapter has never touched the real endpoint** (JSON mode and `max_tokens` vs `max_completion_tokens` are unconfirmed assumptions for `oa provider probe`).
- Budget ledger: reserve/reconcile/release, held capacity counts, USD ceiling requires a cost estimate, unknown-cost counter, per-category totals.
- Engine HTTP: agent surface cannot set private config (403); `/internal/*` needs `EVALUATOR_TOKEN` and is disabled without one; native state unreachable from the agent surface. 11 engine tests pass.
- Fresh agent (`agent/fresh.py`) + public operational checker + canonical task generator + evaluator harness. **Offline M1 e2e (opt-in `OA_ENGINE_TESTS=1`, real Konva + MOCK provider + independent verifier): 3 pass** - flat task solved cycle 1 and independently verified; naive program fails on a nested scene, agent corrects from feedback in cycle 2 and verifier agrees; a previously-correct program fails all cycles under the private world-frame drift. Mock replies are scripted *fixtures*, not learned behaviour and not evidence about Nemotron.
- M2 core (offline, MOCK provider + deterministic benchmark teacher; 53 new tests):
  - Pure rule language + concrete evaluator (exact rationals; no tools; floats rejected). Independent AST->Z3 compiler for the declared subset; variable*variable and variable divisors raise `Unsupported`. **Hypothesis property tests (550 generated rule/input pairs incl. tie-biased inputs) show concrete == symbolic**, and the first tie-biased run found and I fixed a real translator bug (clone-symbol size when created on only some paths). Mutation checks (min/max swap, branch-merge swap, lt->le, ge->gt, eq->ne, dropped clone size) are each caught.
  - Witness service: typed statuses (witness_found / no_witness_in_model / incomplete / timeout / unsupported), solver in a killable spawned process (z3 memory cap, 500 ms/call, 12 calls, 6 s total), unsupported rules spend no solver call, every SAT model is re-executed concretely before use (divergence raises `GroundingError`), SMT-LIB + solver version + domain/candidate hashes exported for UNSAT. Readability rounding is labelled "simple, not minimal". Killed-solver recovery tested.
  - Sealed concept hash (rule + schema + preservation + domain + ledger head; excludes summary/version), hash-chained append-only teaching ledger (tamper-evident; `source` records benchmark_teacher), four separate evidence enums, test that no aggregate confidence/verified field exists.
  - Query selection (entropy / effort, <=8 scenes, <=4 options + Neither, stale-answer rejection by candidate-set hash). Teaching session: <=2 queries, <=2 generation rounds, Neither never forces a pick, every candidate must satisfy the WHOLE ledger (incl. 'neither' exclusions), honest UNRESOLVED outcomes. Scenarios pass: ambiguity resolved by one question; omitted hypothesis recovered via Neither + counted corrected example without the formula appearing in any prompt; a candidate fitting only the newest correction is rejected; no-fit -> unresolved.
- M3 (offline; real Konva AND real Fabric 6.9.1 in the locked page; MOCK provider scripts the binding programs):
  - Fabric backend: same tool names, genuinely native behaviour (left/top, async clone, groups = explicit `UNSUPPORTED_CAPABILITY`), private `move_origin: center` drift; backend identity differs in the public schema hash but not across drift. 6 node tests.
  - Bindings: concept -> targets (pure) -> restricted-AST native program; metered 24-action native allowance; abstract documented-contract model; native check vs observe_geometry; immutable versions + active pointer + history; promotion verifies the sealed concept hash, validation + regression, and parent-unchanged (race => retained unpromoted); rollback = pointer move.
  - Verified on real engines: transfer validates on listed cases for both Konva and Fabric (<=24 native actions); under the private Fabric drift the SAME binding passes the abstract check but fails natively (reproduced mismatch, center offset exactly 10 px for a 20 px proto, abstract model marked untrusted); a hard-coded "fix" passes the drifted witness but is rejected by retained-case replay in the original environment; a probing repair is promoted as v2 with the **sealed concept hash and teaching ledger unchanged**, v1 retained, and the repaired binding is intent-correct on an unseen scene in BOTH environments per the independent verifier; failed repair quarantines and keeps history; a correct execution of a WRONG inferred rule fails the independent intent check; promotion rejects an edited rule, narrowed domain, changed ledger, failed validation.
- M4 core (offline; real Konva+Fabric; MOCK model replies where a model would be used):
  - Non-LLM enumerative reference learner (declared grammar, published constants pool, search limit, CPU time, coverage; deeper grammar only after a Neither). It runs through the SAME TeachingSession/question/ledger machinery. Observed on the clamped-badge latent: it hits a Neither, takes a counted correction, and still ends UNRESOLVED within 2 queries (identifiability limit, at candidate caps 4 and 64); on a proportional latent it learns the rule; on a target outside its grammar it reports not-expressible. Reproducibility bugs found and fixed on the way (set-order in the Z3 encoding; Z3 global-context history changing models).
  - Fixed two-concept composition on real Konva: correct order passes the independent verifier; reversed order passes every node-local check yet fails globally; out-of-scope node rejected; one shared native budget; cycles/recursion/unresolved refs/>4 nodes rejected; missing binding is an explicit error.
  - Episode manifests: template-disjoint dev/val/final splits, held-out size ranges, opaque ids, 4 no-change + 8 drift episodes balanced by backend direction, private latents/drift, freeze + tamper detection, deterministic across processes/hash seeds. Konva got an equivalent private drift (`move_anchor: center`).
  - Metrics/report: episode-clustered paired bootstrap (clustering widens intervals when episodes differ), abstentions/failures count in denominators, false-success rate, separate cost dimensions, learning-cost rows excluded from success denominators, report refuses empty/mock rows unless stamped MOCK and never evaluates the 27.5 gates on non-live rows.
  - Runner + policies: ReferencePolicy (no model), FullV12Policy (model proposes candidates and bindings; same flow), FreshFullContext / TextMemory / StructuredProcedure (shared synthesis loop, differ only in what persists; structured has a replay gate and program reuse). Verified on real engines: all methods get byte-identical task views, no prompt contains evaluator-only strings, reference gets no provider and reports $0, mock costs are UNKNOWN not zero, intent-agnostic baselines pass the public check yet are rejected by the private evaluator (false success is counted).
  - Batteries (disposable scenes, labelled): grounding ablation and target-omission (Neither + counted correction recovers an omitted affine rule; no correction needed when the fixture contains the truth).
  - **Measured so far (all NON-LLM, DEVELOPMENT split, harness checks, not a study):** reference on 2 dev episodes: 15/16 correct, 1 abstention, 0 false successes, 3 teacher interactions, 336 native actions. Grounding ablation on 1 dev drift episode, recovery tasks: grounded 1/2 correct, 0 false successes (other task abstained on the action-allowance finding); ungrounded 0/2 correct, 2/2 false successes.
- **LIVE (real Nemotron via Nebius), 2026-10-09 - first real evidence, DEVELOPMENT split only:**
  - `oa provider probe --live` PASSED: auth, model id returned as requested, `max_tokens`, `json_object` and strict `json_schema` (once the token budget was realistic; my first run misread a truncation as "unsupported"), `seed`, usage incl. `reasoning_tokens`, `reasoning_effort` (none/low honoured). Report: `docs/capabilities.json`; notes: `docs/provider_feedback.md`. Total probe spend < 2k tokens.
  - Teaching-only pilot question ("does the model propose useful candidate rules, and does a revealed disagreement lead to the hidden rule on held-out scenes?"), 12 trials = 6 dev episodes x {badge, spacing}, one run each:
    * reasoning_effort=low: **2/12 recovered**, 38.5k tokens, ~9 s/trial; 5 trials ended "INTENT_READY" on a WRONG rule (false resolution caught only by the held-out check).
    * provider-default effort: **3/12 recovered**, 98.5k tokens, ~35 s/trial, but **6/12 hit the 6,000-token cap** (hidden reasoning ate the budget) so the default is confounded by truncation.
    * Spacing (edge-gap) looks easier than badge margins in both runs (badge 0/6 recovered in both). n=12 single draws: this is a first signal and a debugging aid, NOT an estimate of ability or a comparison of effort levels.
  - **Prompt/loop tuning on dev (24 trials each, reasoning_effort=low) - decisions 27/28:** recovered 2 -> 2 -> 6 -> 6 (v2 -> v3 diversity wording -> v4 numeric correction turn -> v5 alternatives round) while confident-wrong ("ready" on a wrong rule) went 11 -> 8 -> 9 -> **2** and honest UNRESOLVED 11 -> 14 -> 9 -> 16. Spacing 6/12 recovered, badge 0/12 in v5. Frozen as the shared configuration; single draws, wide uncertainty, development data only.
  - v6 (computed geometric relations in the evidence) is a recorded NEGATIVE result: 6/24 recovered, badge still 0/12, +22% tokens -> disabled (decisions #29). Live smoke of 1 drift episode with all 5 methods: reference 7/8 correct; full_v1_2 0/8 (teaching never resolved both concepts, so it abstained); fresh/structured 0/8 (hit the 80k token cap); text_memory crashed on one malformed candidate (fixed: per-candidate leniency). Takeaway: model-based methods cannot act until teaching resolves BOTH concepts, and badge is the blocker.
  - **Model result (development, one draw per trial): Nemotron-3-Ultra-550B at low effort recovers 15/24 hidden rules (badge 9/12, spacing 6/12) vs 6/24 for Nemotron-3-Super with the same loop** (decisions #32). Prompt-only levers did not come close. `.env` now selects Ultra/low. Teaching costs ~20k tokens and up to ~2 min per concept; the spec's 80k-token episode cap no longer fits (decision #33, open). Ready-but-wrong outcomes: 5 of 24 (the failure the held-out check exists to expose).
  - What live failures forced me to fix (all recorded in decisions 22-26): nested-JSON structural slips -> text rule front-end; ids -> positional aliases; retry feedback now carries rejection reasons; a probe crash on error responses; a misleading "bad expression" message for a wrong `clone_place` key.
  - Spend so far: roughly 140k tokens total across probes and trials; dollars unknown (no rates configured), well inside the $5 ceiling by any plausible price.
- API `GET /health/live` exists (import verified; not served).

### Environment notes
- Chromium cannot launch inside the Bash sandbox (Mach port denied); engine tests/fixture generation were run with the sandbox disabled for those commands only.
- The e2e tests spawn the Node engine and need Chromium, so they run unsandboxed and are skipped by default.

### Not done / limitations
- `docker compose build`: **succeeded** (api, web, engine, worker images built; engine image installs Chromium via Playwright). Images were built but NOT run: `docker compose up`, health endpoints, and the `oa worker` command (not yet implemented, so the worker container will exit) are untested. `docker images` inspection was denied by the sandbox (daemon socket), unrelated to the build.
- npm workspaces installed (konva 9.3.22, fabric 6.9.1, playwright 1.64.0, fastify 5.12.5, react 18.3.1, vite 5.4.21, ts 5.9.3); Chromium headless shell downloaded; `npm run build:web` succeeds. Engine is a health-only placeholder; web is a MOCK-banner placeholder.
- `schemas/` empty. No DB, migrations, provider code, verifier, or any M1 content.
- No git repository (sandbox denies creating `.git`; user must run `! git init`). Run records cannot yet carry a commit hash.
- No live Nebius check of any kind (no credential). All live gates BLOCKED.
- Clean-checkout reproduction not yet performed.

### Gate status
- M1 offline gate (mock-driven run -> verifier-checked artifact; verifier rejects all six faults): **met in tests**. `oa run --mode mock` CLI is NOT wired yet.
- M1 live gate (real Nemotron task -> checked artifact): **BLOCKED** (no credential; adapter unverified).

### M2 limitations (read before trusting any claim)
- All of the above uses scripted MOCK candidate sets. It demonstrates the machinery, not that Nemotron proposes useful candidates; that is exactly what the 72-hour pilot must measure and is BLOCKED on a credential.
- The enumerative symbolic reference learner (spec 21.11) is not built. Without it, no claim that the LLM is necessary can be made.
- Symbolic results cover only the declared rectangle/linear subset; they say nothing about native Konva/Fabric behaviour (M3) or user intent.
- Teaching sessions are in-memory objects; no durable persistence/resume, HTTP routes, or UI yet.
- The syntactic duplicate check does not merge behaviourally identical candidates; entropy weights are per candidate (uniform), as the spec's heuristic states.

### M3 limitations
- The repair that succeeds is a scripted FIXTURE (a probing program). Whether Nemotron writes such a repair is unmeasured and BLOCKED on a credential. The drift is one artificial family; no claim about real Konva/Fabric releases.
- Only flat scenes and the badge rule are exercised end to end on the native backends; gap_row bindings, resize targets, and multi-concept composition are not yet run natively.
- The mock-provider flow is not yet wired to `oa transfer`, durable jobs, or the UI.
- Native allowance accounting is per-search (24 actions) and not yet merged into a single episode ledger across teaching + binding + repair.

### M4 limitations
- Of the model-based methods only the SHARED candidate-generation step has run live (teaching-only, dev). Binding generation, the synthesis baselines and full episodes have NOT run live. Previously: NO LLM method had been run on anything real: FullV12 and the three baselines were exercised only with scripted MOCK replies (plumbing, fairness, accounting). Their prompts for hypotheses/binding/synthesis are untested against Nemotron; baseline competence is therefore UNKNOWN and must be tuned on dev/validation (equal effort for every method) before any comparison means anything.
- Dev tasks are in the reference's grammar by construction, so its 15/16 says the harness works and that easy dev tasks are easy; it says nothing about the final split (not run; do not peek before the freeze).
- The 24-action native allowance fails row-task repairs (decisions #18) - unresolved protocol decision.
- Structured baseline's replay gate and the reference's template library are my implementations of the spec's descriptions, not reproductions of ContractSkill or any paper.
- Nesting is not held out (Fabric subset has no groups); one drift family only; composition plan is host-fixed (spec allows the model to propose it; not built).
- Not wired: `oa compare/benchmark/report` CLI, durable jobs, UI, v1.3 SVG lane, offline evidence replay export. git init and clean-checkout reproduction still open.

### Next
Obtain a Nebius credential and run `oa provider probe --live`, then the 72-hour pilot (4 dev episodes, all methods); wire the CLI (`oa run/compare/report`); resolve the native-allowance decision on dev data; M5 (UI, editable SVG, evidence replay, v1.3 spike).

## Live pilot on Nemotron-3-Ultra (low effort), development episodes 1-2, 2026-10-10 — NOT a result, a debugging record
Run `results/runs/development-ep1-2-20261010T132248` (all fixes of decisions #34-#37; dev split; single run, no repetitions):
reference 16/16; full_v1_2 1/16 (3 of 4 commits wrong); fresh_full_context 1/16; text_memory 1/16; structured_procedure 2/16;
~1.8M model tokens; dollar cost unknown (rates unset). Most failures are `unresolved_teaching` (the model never resolves the concept, so
the method abstains) and token-budget exhaustion for the baselines. These numbers must not be quoted as method comparisons.
- Open: full_v1_2 committed 4 times, 3 wrong. A re-run of episode 1 alone did NOT reproduce it (2/8 correct, 0 wrong; teaching is stochastic),
  so the cause (wrong learned rule vs. binding vs. verifier) is UNKNOWN. Rows now carry an evaluator-private `verdict` (failed checks) so the
  next occurrence is explained. A false-success rate is a headline metric; until explained, treat it as a possible defect.
- Earlier same-day run `development-ep1-2-20261010T123444`: full_v1_2 rows INVALID (pre-fix); marked in-place.
- 2026-10-10 later: full_v1_2 alone on dev episodes 3-5 (`results/runs/development-ep3-3-20261010T160334`): 6/24 correct, 0 wrong commits;
  failures = unresolved_teaching and binding_unavailable (+1 provider timeout during learning). Across both full_v1_2 re-runs 0/8 commits were wrong,
  so the earlier 3-of-4 wrong commits remain UNEXPLAINED (not reproduced). Binding fixes (decision #38) not yet re-measured end to end.

## UI (2026-10-11): recorded walkthrough + Compare view (apps/web) — first usable interface
Built: canvas-first workspace (task stepper | scene panels | evidence), Learn/Reuse/Transfer/Challenge/Compare modes, the real competing-outcome
question with a Neither option, four separate evidence chips (no combined score, no "Verified" badge), independent-verifier check list,
old/new native-procedure diff, binding version table, sealed-hash display, text equivalents for every canvas, keyboard-operable controls,
light/dark, reduced-motion respected. Data: `scripts/build_demo_bundle.py` (needs Chromium) writes `apps/web/public/data/{demo,evidence}.json`:
- demo.json is RECORDED: a deterministic offline story run on the real Konva+Fabric engines and the independent verifier. NO model is used;
  the candidate rules, teacher answers and the two native procedures are scripted fixtures, and the UI says so on every screen.
- evidence.json is rebuilt from stored live-pilot rows (development split), excluding runs that predate the binding fixes or are unfinished.
Run: `PYTHONPATH=src:. python scripts/build_demo_bundle.py && cd apps/web && npx vite build && npx vite preview`.
Checked: `tsc --noEmit` clean; viewed in Chrome at desktop width (steps 1, 2, 6, 7 and Compare). NOT checked: phone width (the browser tool
could not resize the viewport), screen-reader behaviour, Firefox/Safari.
NOT built: live teaching from the UI, HTTP API for runs, challenge mode with the user's own inputs, skill inspector, editable SVG export,
evidence-replay command. These are listed in the page footer.
Also found while building it: the engine-backed integration tests (OA_ENGINE_TESTS=1) had gone stale after #32-#38 and one research-integrity
test caught my own prompt wording (decision #39). All 274 tests (including engine-backed) pass.

## Five-method live pilot, dev episodes 3-5, Nemotron-3-Ultra low effort (run development-ep3-3-20261011T020702) — 2026-10-11
Single run, development split, n = 3 episodes; the 2M-token global ceiling stopped text_memory and structured_procedure on episode 5 (reported as NOT RUN).
NOT a method comparison and NOT evidence for the §27.5 gates. Model tokens ~2.1M. Dollar cost not computed (rates are user-entered, unverified).
| method | correct / scheduled | committed but wrong |
|---|---|---|
| non-model reference | 24 / 24 | 0 |
| full_v1_2 | 3 / 24 | 5 of 8 committed |
| fresh_full_context | 7 / 24 | 7 of 14 |
| text_memory | 3 / 16 | 2 of 5 |
| structured_procedure | 1 / 16 | 10 of 11 |
Reading (honest): (1) tasks and verifier are sound (reference 24/24). (2) EVERY model method commits wrong output at a high rate; full_v1_2 is
not better at avoiding it. The private verdicts show geometry mismatches against the evaluator's rule, i.e. the system committed from a rule that fit
the demonstrations but was not the intended one (the "ready on a wrong rule" mode seen in the teaching trials, now visible end to end). The earlier
"3 of 4 wrong" observation was therefore real, not noise. (3) Under spec 21.11's stopping rule this is the case "no separation": the claim to
test next must be narrowed (e.g. does asking about disagreements reduce wrong commits), not rescued with extra agent roles. (4) All of this used the
candidate-generation wording before decision #39 and without the 32k floor changes beyond #34-#38.

## 2026-10-11 later: export, one-process demo, audit experiment, cleanup
- Editable SVG + evidence-package export from the live demo (`/api/teach/{id}/export.svg`, `/evidence.json`). Tested: SVG parsed by an independent XML
  parser equals the engine's observed geometry; ids sanitised; no active content; provenance (rule hash, backend, binding hash, verifier result, model_used=none) embedded.
- The API serves the built web app at `/`: `uv run uvicorn open_apprentice.api.app:app --port 8000` is the whole product. README rewritten with verified commands.
- Measured cost: five-method pilot ~2.1M tokens = $1.19 (balance 21.14 -> 19.95), i.e. ~$0.57/M tokens (memory note live-run-cost).
- Cleanup: black + ruff clean, 292 tests pass (incl. engine-backed), import-boundary contract kept. mypy debt noted (decisions #43).
- Audit-vs-control experiment (decisions #40) launched on Nemotron-3-Ultra: 48 trials per arm, 12 dev episodes x 2 concepts x 2 reps. RESULT PENDING.
- Not yet verified: `docker compose up`, clean-checkout reproduction, phone-width layout, public-deployment hardening (no rate limiting; engine calls block the event loop; unauthenticated session creation is capped at 20).

## 2026-10-11 evening: Nemotron live mode, Break it, offline replay (all tested)
- Nemotron live mode (opt-in `DEMO_MODEL_ENABLED=1`, global cap `DEMO_MODEL_MAX_USD`, default $4): the model proposes candidate rules and writes/repairs the native
  procedure; outputs are accepted only after the real-engine checks, and a scripted fixture replaces a failed model output WITH a visible, reasoned notice. Measured on
  Nemotron-3-Ultra: start ~24 s, whole session about $0.09-$0.28. Two real runs of the same flow differed: Fabric native procedure failed once (labelled fallback) and passed
  once; under the silent tool change the passing model procedure survived without repair (it measures and corrects). Single runs, not rates.
- Break it: `/api/teach/{id}/break` (bounded sampling, deterministic per seed). Offline replay: `oa replay-evidence`, `/api/replay`; 8 tamper cases are detected.
- 309 tests pass (incl. engine-backed); fresh `git clone` + README steps verified (uv sync, npm ci, playwright, build:web, tests, lint-imports).
- Open: Vercel CLI is logged out (public deployment waits for `vercel login`); audit-vs-control experiment still running.

## 2026-10-11 night: audit experiment RESULT (negative) — see decisions #44
Control: 34 committed (19 correct, 15 wrong = 44%), 9 abstained, 5 lost to truncation. Audit: 10 committed (6 correct, 4 wrong = 40%), 30 abstained, 8 lost. The audit trades
correct answers for silence without improving precision. Spacing is the weak concept (control: 11 of 21 committed rules wrong; badge: 4 of 13). ~10-15% of model trials
end in TruncatedOutput in both arms. This is shown in the Compare tab. The research claim "asking/auditing more reduces false success" is NOT supported.

## 2026-10-11 night: deployable demo container VERIFIED
`docker build -f docker/demo.Dockerfile -t open-apprentice-demo .` (2.47 GB) then `docker run -p 8000:8000 open-apprentice-demo`: engine ready as a non-root user (Chromium with
`OA_CHROMIUM_NO_SANDBOX=1`, container is the sandbox), `scripts/live_flow_check.py --mode reference` passes end to end inside it (teach, run on both backends, tool change mismatch, repair with
rule hash unchanged), static web + data served, CSP/frame/nosniff headers present. Model mode inside the container NOT tested (needs --env-file and spends credit).
`docker compose` (db/worker/web) remains untested and is not the demo path (worker not implemented). Docs: docs/deploy.md, docs/demo_script.md.

## 2026-10-11 night: hybrid experiment RESULT (positive, limited) — decisions #46
Hybrid: 24 trials, 20 committed, 19 correct, 1 wrong (5%), 3 abstained, 1 error; 428k tokens. Model alone: 44% wrong. The non-model reference also solves these tasks, and the model's role is NOT shown by this
experiment. The `oa learn` process stalled while the laptop slept (3 s CPU in 2.5 h) but finished; results had been written only at the end, so per-trial saving was added (commit 3acc306).

## 2026-10-12: out-of-grammar RESULT (decisions #47) and teach-by-placing
Search only 0/12 correct; model alone 5/12 (2 confident-wrong); hybrid 5/11 committed-all-correct. First evidence that the MODEL adds value (outside the search grammar). Small n; two reps; one rule family.
Live demo now starts from the visitor's own badge placement (drag / number fields / arrow keys); an inexpressible placement ends unresolved in plain language. 334 tests pass.

## 2026-10-12: Real-SVG lane (experimental, no model)
Built and tested: validator (15 rejection cases), byte-exact editor (property-tested), typed patch with 7 harmful-patch rejections, rule applied to three authored SVGs with Chromium-measured verification (0.000 px on the samples),
inventory and coverage (rotated element refused with a reason), UI tab. NOT done: matched baseline pilot, model-written patches, paths/rotation/styles. See decisions #48.

## 2026-10-12: replay mode (decisions #49)
- Recorded one real Nemotron session (balance $2.57 before; ~$0.09 spent) to `docs/replay/nemotron_tape.json`; replayed it with the model disabled: same questions, rule and verifier results at $0. Tested: `tests/unit/test_replay.py` (scripted mock) plus the manual `scripts/live_flow_check.py --mode replay` run against the real engine.
- UI: third learner option "Nemotron replay (recorded, free)". Not yet checked in a browser, and not yet deployed anywhere.
- Browser check of the replay option (headless Chromium via Playwright against the local server, 2026-10-12): replay radio enabled, REPLAY label and meter ($0.000, original token counts), teach -> answer -> seal -> run on Konva with a model-generated binding, no page errors; all 8 tabs render with no console or network errors.
  It found a **real pre-existing bug**: a `useEffect` placed after the early returns in `TryIt.tsx` (added in 436ad10, the SVG lane) made React throw error #310 as soon as the backend answered, leaving "Try it live" BLANK whenever the API was up. Fixed by moving the hook above the early returns. Earlier "layout flow passes" claims for that tab were not browser-verified after that commit; this check is the first that was.
  Replay finding: answering B instead of A sealed a different rule (15% of height) yet still matched the tape, because the binding prompt carries the rule's target positions, not its text; the procedure was re-checked live. Wording in the UI, README and decisions #49 was corrected.
- Not checked: Firefox/Safari, phone width, screen readers. No ESLint rules-of-hooks lint exists in the repo, which is why the hooks bug was not caught earlier.


- Docker image built and measured (details in docs/deploy.md section 3): 512 MiB + 1 CPU runs the whole flow (peak ~335 MiB unlimited); 0.1 CPU makes the symbolic search time out and sessions end UNRESOLVED. The earlier macOS figure (~585 MB peak) double-counted shared pages and overstated memory.
- Browser check of Repair, Break and export (headless Chromium, reference mode, local server, 2026-10-12): teach, answer, seal; Konva run and Fabric run pass; Fabric + silent tool change shows "Reproduced native mismatch" (badge expected (368,112,20,20), observed (358,102,20,20)), Native axis "Reproduced mismatch", Independent verifier FAIL, Repair enabled; Repair -> "Repaired. Your rule and its sealed hash are byte-identical"; re-run after repair verifier PASS;
  "Try to break it (40 inputs)" -> "Could not break it: 40 of 40 inputs passed" (binding v2, scripted fixture, 3.8 s); SVG download (valid XML with oa: metadata, no script element) and evidence.json download work; "Re-check this package offline" -> "Every offline check passed" on the untouched package and "At least one offline check FAILED" after flipping verifier_passed/native_passed in the JSON. No page errors, no HTTP errors.
  Not checked in the browser: the same three actions in Nemotron live mode and in replay mode past the first Run (replay has no recorded repair), phone width, other browsers, screen readers. The ad-hoc Playwright scripts used for this are not committed (no repeatable UI test exists yet).
  UI nit seen: the learner box always shows the REPLAY and "not enabled" helper text, even when Reference is selected.
- Added repeatable guards (2026-10-12): `npm run lint` (ESLint 10 + react-hooks; rules-of-hooks is an error) and `npm run test:e2e` (`tests/e2e/ui.test.mjs`, Node test runner + the repo's Playwright, spawns its own server on port 8765 and a no-API static server on 8766, skipped unless OA_E2E=1): every tab renders with no page/network errors; learner box shows helper text only for the selected option; replay flow ($0.000, model-generated binding); repair + 40-input break + SVG/evidence download + offline re-check passing and failing on a tampered package; static-copy wording.
  Mutation check: with the original hooks bug reintroduced, lint reports `react-hooks/rules-of-hooks` and 4 of the 5 browser tests fail; restored, all 5 pass. Learner box fix: the REPLAY and "not enabled" helper text now shows only for the selected option. Still not covered: Nemotron live mode, phone width, other browsers, screen readers.
- Guided story (2026-10-12): "Watch the story" in Try it live drives teach -> answer -> seal -> Konva -> Fabric -> silent tool change -> (repair -> re-run) -> 40-input stress test through the real API, with a persistent step log whose text is built from the responses (reference: ~19-20 s; the recorded-Nemotron variant says plainly that there is no repair). Covered by two browser tests.
  Found and fixed on the way (both pre-existing, visible only after a repair): (1) the repair diff made the page ~73,000 px wide and 6,828 px tall: diff lines were inline-blocks of width 100% in a `<pre>` (one long row) and the screen-reader-only spans escaped the `<pre>`'s scroll box; now block lines and `position: relative`. Page after a full story: 1280 x 3131. (2) After a repair the run panel claimed "Survived the silent tool change ... no repair was needed"; it now says "Passes after the silent tool change" with the binding version when the binding is v2 or later. Both are asserted in `tests/e2e/ui.test.mjs`.

- Performance (2026-10-12): a reference `/start` takes ~0.2 s on this Mac; profile: ~0.36 s CPU in enumeration, of which ~0.27 s is `fits` -> `evaluate_rule`, half of that `validate_rule` re-checking each enumerated rule on every evaluation. Caching the behaviour-probe scenes was measured and made no difference (reverted). Possible later win: validate enumerated rules once. Not needed for correctness.

## 2026-10-12 (evening): improvement plan, Phases A and B done; Phase C gate checked
- **Phase A (security, honesty, correctness), each with a regression test, all committed:** script could run in the SVG-measuring browser (reproduced: an injected handler moved an element) -> JS disabled, processing instructions refused, 10 s timeout; engine session cap raced (7 parallel creates passed a cap of 4) and failed creates leaked contexts -> slot reserved before the first await, freed on failure, idle expiry, owner-checked delete, browser-crash detection, API readiness pings the engine; replay sessions were labelled LIVE in run/repair/evidence/SVG -> fixed; `BudgetExhausted` -> HTTP 500 -> 402; huge ints in model programs -> OverflowError -> ProgramError; leaving Try it live now aborts in-flight (paid) calls; skip link no longer jumps to Home; hybrid cap interleaves model and search candidates (decisions #50: 24 of 46 stored rounds reached the cap, none lost every search candidate; dropped candidates were not recorded); unknown-cost calls and held reservations are now charged at $4/M instead of $0; free sessions are evicted before paid ones.
- **Phase B (reliability, performance):** solver limit is now z3 `rlimit` (calibrated: max 1,984 units on the 24 dev tasks, limit 1,000,000), wall clock is a crash guard only, z3 pinned to 4.13.4.0 (decisions #51). Verified in Docker (512 MiB): at 0.1 vCPU the session now reaches INTENT_READY with the same rule (was UNRESOLVED), about 50 s per flow instead of 2 s; no OOM. Solver, enumeration and engine work run in worker threads (health-check latency during another visitor's `/run`: up to 70 ms -> 2 ms); `SolverPool` is thread-safe. Truncation retry is a different request (nudge to keep reasoning short; real-world effect not measured). GitHub Actions CI added (first run on GitHub not yet seen). A cache of probe scenes was measured as no gain and reverted.
- Tests now: 381 Python (with engine), 27 Node, 9 browser; lint, black, import contracts clean.
- **Phase C gate (free):** with the reference learner on the 12 development episodes x 2 concepts, 15 of 24 demonstrations are genuinely ambiguous (12 of 12 badge, 3 of 12 spacing; questions asked: 0 x9, 1 x11, 2 x4); the other 9 have exactly one fitting rule, so a calibrated agent should NOT ask there. Ambiguity here is defined relative to the declared rule grammar and the enumerative source's cap of 4.
- Not done yet: Phase C (NeMo Gym environment), D, E. Nothing from this evening has been pushed to GitHub.

## 2026-10-22: Plan 9A, campaign scene, fit observation, fixtures and verifier (branch `p9-promo-story-card`)

Spec `docs/superpowers/specs/2026-10-22-promo-story-card-design.md`; plan `docs/superpowers/plans/2026-10-22-p9a-campaign-scene-and-verifier.md`.
Development work only: no learner, no question, no UI, no Fabric yet (plans 9B-9D). Nothing here is a held-out or model result.

### What works (each verified by running it, on Python 3.12, by the agent outside the sandbox)
- Konva engine: `text`, `image`, `shape`, `artboard` nodes with role/link/asset/focal/format/safe/sequence metadata and explicit z;
  sessions load the vendored Liberation Sans and two authored SVG assets (hash-checked); unknown asset id fails `INVALID_SCENE`.
- `observe_fit` (read-only, Konva only): measured lines per text node on an unbounded clone, and `text_overflow`,
  `word_too_wide`, `outside_safe`, `below_minimum`, `overlap` violations against caller-given limits.
- `open_apprentice.campaign`: frozen limits, `role_map` (missing or doubled role stops with named problems), 9 development fixtures.
- Evaluator side: 9 authored gold outputs (one "not applicable"), `text_layout` (font-table widths via `fonttools`, Konva wrap rule,
  no kerning), `campaign_verifier.verify_story` with 15 named checks.
- Tests: Python **1356 passed** (`OA_ENGINE_TESTS=1`, whole `tests/`), engine **49/49**, `lint-imports` 2 kept, black clean.
  Engine and verifier agree on every line count in the fixtures and golds; every gold scene read back from Konva passes the verifier.

### Limits
- The verifier ignores kerning; a kerned line the browser fits can fail the verifier (tested deliberately). It reads the fonts from
  `services/engine/vendor`, so it runs from the repo, not yet inside the API image.
- Fabric has none of the new node types or `observe_fit`; its public schema hash is unchanged.
- Browser e2e and web build were not rerun (no web change in 9A).
- **9B prerequisite (from the 9A review):** the verifier reads fonts from `services/engine/vendor`; copy `fonts/`, `assets/` and
  `MANIFEST.json` into the API image (or make the path configurable) before any API route calls `verify_story`.
- Final review fixes: the verifier and `observe_fit` apply node and group scale to font sizes, image aspect and focal point;
  safe areas come from the frozen limits, not the result's own metadata; a no-break-space run counts as one word; `observe_fit`
  refuses incomplete limits; text must use Liberation Sans, normal or bold. Python 1362 passed, engine 53/53.
