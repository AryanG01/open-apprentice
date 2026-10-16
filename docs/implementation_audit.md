# Implementation audit: spec → code

Spec: `docs/superpowers/specs/2026-10-15-teach-correct-reuse-design.md`. Plans: `docs/superpowers/plans/`. Status values:
**implemented** (code + test in this repository), **planned** (named plan), **deviation** (recorded difference from the spec).
Updated at the end of Plan 4B (branch `p4b-tasks-probes`).

| Spec § | Requirement | Code | Status | Evidence |
|---|---|---|---|---|
| 2.1 | Pure `step(events, config) -> Action`; no model/browser/storage/teacher calls | `teaching/step.py` | implemented | `tests/unit/teaching/test_step.py` (7 tests) |
| 2.2 | Rule language + evaluator reused | `concepts/rules.py`, `concepts/rule_text.py` (unchanged) | implemented | existing suites |
| 2.2 | `fits` replays all active constraints on every step | `teaching/step.py:_filter` (calls `concepts/hypotheses.fits` for every derived constraint) | implemented | `test_step.py` |
| 2.2 | Constants guard kept as a documented heuristic, same for every system | `concepts/label_teaching.magic_condition` used by `_filter` | implemented (baselines: Plan 5) | `test_step.py` |
| 2.2 | Held-back validation removed from the new learning path | `teaching/` never calls the old `label_teaching.teach`; the old loop is kept only to reproduce earlier results | implemented | `teaching/` import graph; `test_isolation.py` |
| 2.2 | Checker change (no exclusion of defects the intended output shares; final positions) | `evaluation/labels.check_after` | planned (Plan 5, evaluation; the product-side final-position layout check is `drawio/publish.py`, Plan 3) | — |
| 2.2 | Import-boundary contract extended | `pyproject.toml` (2 contracts) | implemented | `lint-imports`: 2 kept, 0 broken |
| 2.3 (1) | draw.io round trip: render, measure, patch, re-open | `scripts/spikes/` | planned (Task 0 of Plan 1, needs the owner's download approval) | — |
| 2.3 (2) | Effect-free event-log replay | `teaching/executor.py` (claims by action id) | implemented | `test_executor.py::test_replay_is_effect_free` |
| 3.1 | Immutable events + manifest compare-and-set; replay walks the chain | `storage/store.py`, `teaching/events.py` | implemented | `test_store.py`, `test_events.py` (orphan event, concurrent writers) |
| 3.1 | Activation records and pointer | `skills/versions.py` (`SkillStore`: immutable versions, activation record chain, CAS pointer, history, reconcile) | implemented | `test_versions.py` (incl. two unlogged activations with a rollback recovered without moving the pointer; generation not version compared), `test_stateful.py::TestVersions` |
| 3.2 | `manifest_revision` vs `intent_revision` | `teaching/events.py` | implemented (storage); dependency-based acceptance of late results: Plan 4 | `test_events.py` |
| 3.3 | Event types | `teaching/events.py` (`INTENT_TYPES`), payloads in `step.py`/`executor.py` | implemented (learning subset); correction types Plan 2 | tests above |
| 3.4 | Request types + validation | `teaching/teacher.py` (ChooseOutput, ConfirmPreview with purposes, RequestDemonstration, ConfirmCorrectionScope) | implemented | `test_teacher.py`, `test_scope_request.py` |
| 3.5 | Constraint semantics from committed events | `teaching/constraints.py` (identified items), `teaching/evidence.py` (full/masked/excludes), `teaching/corrections.py` (corrective edit, scope authorization, replacements) | implemented | `test_constraints.py`, `test_evidence.py`, `test_correction_step.py` |
| 3.6 | Tolerance 0.5, separation > 1.0 for ChooseOutput | `teaching/teacher.py`, `evaluation/teacher_sim.py` | implemented | `test_teacher.py`, `test_teacher_sim.py::test_ambiguous_match_is_protocol_error` |
| 3.7 | Budgets (3 choose, 1 preview ≤ 3 items, ≤ 8 attempts) | `teaching/step.py:StepConfig` | implemented (RequestDemonstration budget enforced when the step issues it: Plan 4) | `test_step.py` |
| 3.7 | One retry for transient provider failures; retries count | `teaching/executor.py:_propose`, `step.py` attempt counting | implemented | `test_executor.py::test_one_transient_failure_is_retried_and_stays_in_the_accounting` |
| 3.7 | Exposure accounting, one state per attempt | `teaching/accounting.py` | implemented | `test_accounting.py` |
| 4 | Step policy rules 0–6, commit predicate, deterministic selection | `teaching/step.py` | implemented (batch documents only) | `test_step.py` |
| 4 | Generated probes: node resize, obstacle across a placement boundary, narrower canvas; ≤ 128 per round; 5,000,000-statement budget; usable = 2–4 groups separated > 1; score and tie-break per rule 3; incomplete search never commits | `teaching/probes.py`, `step.py` (`RenderProbe`), `concepts/rules.evaluate_rule_counted` | implemented (role flip and fresh arrangement deferred: spec 11 scope cut 3) | `tests/unit/teaching/test_probes.py`, `test_step_probes.py` |
| 4 | Generated probes are rendered and must match their selection geometry before display | `executor.py` (`probe_renderer`), `api/v2/service.make_probe_renderer` (probe documents, 0.5 tolerance) | implemented | `tests/unit/teaching/test_executor_probes.py`, `tests/unit/api_v2/test_probes_api.py`, `tests/integration/test_api_v2_probes.py` (real engine) |
| 4 | Error vs abstain accounting | `step.py` (`Error` on terminal provider failure) | implemented | `test_step.py::test_provider_failure_terminal_is_error_not_abstain` |
| 5 | Corrections, drafts, scope, supersession, retention, activation | `teaching/scope.py`, `retention.py`, `corrections.py`, `correction_step.py`, `correction_executor.py` | implemented (explicit ConflictDetected event: Plan 5; generated probes in corrections: Plan 4) | `test_scope.py`, `test_retention.py` (untouched-label acceptance), `test_correction_step.py` (scope→affected→revision within budget; scope-violating interpretation never shown; cancel leaves base untouched; override/accidental not learning), `test_correction_executor.py` (activation; concurrent second correction rejected; failure leaves the pointer) |
| 6 | Hardened import: expat, no DTD/entities, 2 MB upload, 4 MB decoded, UTF-8, unique IDs/valid parents, label-HTML allowlist | `drawio/parse.py` | implemented | `tests/unit/drawio/test_parse.py` |
| 6 | Cell statuses, editing rectangle, pageScale/page=0 refusals, 32/16 limits, font refusal | `drawio/classify.py` | implemented | `tests/unit/drawio/test_classify.py` |
| 6 | Engine render + measure: pinned viewer, bundled Liberation Sans as Helvetica, Range per text node, cell-state + element cross-check, PNG/SVG, network blocked | `services/engine/src/drawio.js`, `POST /drawio/render` | implemented | `services/engine/test/drawio.test.js`, `vendor.test.js` |
| 6 | Scene from measurements (1/64), offset d, single-line demotion, node mismatch block | `drawio/render.py`, `drawio/scene.py` | implemented | `tests/unit/drawio/test_scene.py`, `tests/integration/drawio/test_render_scene.py` |
| 6 | Mapping sidecar bound to document hash; proposed → confirmed; digest for intent_revision | `drawio/mapping.py` | implemented (intent_revision wiring: Plan 4 API) | `tests/unit/drawio/test_mapping.py` |
| 6 | Whole-unit serialization, byte-span patch, missing x/y insertion, compressed page rewrite, expected_old | `drawio/patch.py` | implemented | `tests/unit/drawio/test_patch.py` |
| 6 | Publication: separate conformance/preservation/layout axes, intent passed through, immutable artifact | `drawio/publish.py` | implemented | `tests/unit/drawio/test_publish.py` |
| 6 | Round-trip matrix | — | implemented | `tests/integration/drawio/test_roundtrip_matrix.py` (mutation-checked) |
| 6 | Drift report (draw.io CLI, real Helvetica) | `scripts/drawio/drift_report.py` | implemented for the dev corpus | `docs/corpus/drift_report.md` (max 0.00) |
| 7 | Simulator teacher in a separate process | `evaluation/teacher_sim.py`, `teaching/teacher.SubprocessTeacher` | implemented | `test_teacher_sim.py::test_subprocess_teacher_round_trip` |
| 7 | Learner-process isolation (audit hook) | `teaching/isolation.py` (refuses to install if evaluator modules are already loaded) | implemented as a guard; **not yet called** by any learner entry point — wired into the learner runner in Plan 5 | `test_isolation.py`, `test_review_fixes.py::test_guard_refuses_when_evaluator_already_loaded` |
| 7 | Baselines B/C/D, manifests, battery | — | planned (Plan 5) | — |
| 7 | Real-file corpus authored in draw.io, final three frozen | `tests/fixtures/drawio_corpus/dev/`, `benchmarks/final/drawio/` (git-ignored) | implemented (Plan 1) | `docs/corpus/drawio_provenance.md` |
| 8 | Anonymous owner: signed `HttpOnly` cookie; every resource owner-checked (other owners get 404) | `api/v2/identity.py`, `api/v2/records.py` | implemented | `tests/unit/api_v2/test_identity_records.py`, `test_guards.py` (mutation-checked) |
| 8 | `POST /documents`, preview PNG, `POST /documents/{id}/mapping` (→ `mapping_hash`), draft render | `api/v2/service.py`, `routes.py` | implemented | `tests/unit/api_v2/test_documents.py` |
| 8 | `POST /sessions`, `GET /sessions/{id}` (derived state, outstanding request + intent revision, budgets, recorded/reserved/uncertain spend, manifest revision, provenance) | `api/v2/service.py` | implemented | `test_sessions.py` |
| 8 | `POST /sessions/{id}/responses` (outstanding + current intent revision only; identical repeats idempotent), `POST /sessions/{id}/cancel` | `api/v2/service.py` | implemented | `test_responses.py` |
| 8 | `POST /skills/{id}/versions/{v}/apply`, `GET /runs/{id}`, `POST /runs/{id}/cancel`, `GET /runs/{id}/export` (.drawio / SVG / receipt) | `api/v2/service.py` | implemented | `test_runs.py`, `tests/integration/test_api_v2_engine.py` |
| 8 | `POST /skills/{id}/corrections`, `POST /skills/{id}/activate`, `GET /skills/{id}` | `api/v2/service.py` | implemented (request names doc/page + run instead of `output_artifact_hash`) | `test_corrections.py` |
| 8 | Paid mode server-side only; durable global cap; "Live inference is unavailable…" refusal, never a silent swap | `api/v2/context.make_v2`, `service.LiveUnavailable`; live proposers `providers/teaching_adapter.py` | implemented (no paid call made) | `test_sessions.py::test_live_requested_when_unavailable_is_refused_with_spec_wording`, `tests/unit/test_teaching_adapter.py` |
| 8 | Provenance Model × Teacher on sessions, runs, skills | `api/v2/service.py` | implemented (offline enumerator reported as Fixture) | `test_sessions.py`, `test_runs.py` |
| 8 | Offline learner for PROVIDER_MODE=mock and journeys | `concepts/label_enumerative.py` | implemented | `tests/unit/test_label_enumerative.py` |
| 8 | `POST /internal/tasks/{task_id}` (Cloud Tasks): OIDC audience + service account verified, task claim, duplicate delivery reports stored state, per-key lock | `api/v2/tasks.py`, `routes.post_internal_task`, `service.run_job` | implemented (fake client; not yet run on GCP) | `tests/unit/api_v2/test_tasks.py` |
| 8 | Preview shows blocked documents with reasons; approving a blocked item is refused | `api/v2/service.item_checks` (geometric layout check on the session's scenes), `submit_answer` 409 `BLOCKED_ITEM`; `apps/web/src/v2/Question.tsx` | implemented | `tests/unit/api_v2/test_screens_backend.py::test_blocked_preview_item_cannot_be_approved` |
| 8 | Screens: import and map, teach (drag + "This whole document is right" after the draft render), clarify (rendered alternatives + None / Not sure / Cancel), preview (Approve / Reject / Not sure), correct (partial / full approval), review revision, reuse and export, evidence panel | `apps/web/src/v2/*` | implemented | `tests/e2e/journey.test.mjs` |
| 8 | Overlay transform document → image → display, draft render on drop, keys 1 / 10 / 1/64, x/y fields | `v2/geometry.ts`, `v2/DocumentView.tsx`; scene + image offset route | implemented | `tests/e2e/geometry.test.mjs`, journey alignment check at 1280 and 800 px |
| 8 | Polling every 2 s, stale `manifest_revision` ignored, reload resumes | `v2/useSession.ts`, `v2/session.ts`, URL hash | implemented | `geometry.test.mjs` (stale revision), journey reload step |
| 8 | Provenance per session, run, skill; live-unavailable wording | `v2/provenance.ts`, `Teach.tsx` | implemented (no recorded v2 example exists yet; the message links to the prototype's replay and says so) | journey steps 4 and 8 |
| 8 | "Earlier prototype" tab keeps the badge flow unchanged | `App.tsx` | implemented | `tests/e2e/ui.test.mjs` (9 tests) |
| 9 B | Property and state-sequence tests | `tests/unit/teaching/test_stateful.py` (event log, ledger, versions; Hypothesis `ci` profile, derandomized) | implemented | mutation check: removing the activation generation check fails `TestVersions` |
| 10 | Staging and release deployment | `storage/gcs.py` (store contract over GCS, fake-bucket contract test); `docs/deploy_staging_proposal.md`, `oa staging-check` (race, survival, render, tasks) | staging: **created and checked 2026-10-16** (render, GCS race, Cloud Tasks OIDC dispatch, restart survival, forged-call refusal: all pass, `docs/staging_results.md`); release: Plan 6 | `tests/unit/storage/test_store_contract.py`, `tests/unit/drawio/test_cli.py` |

## Deviations
1. `.drawio` native format instead of SVG (spec 13.1). Recorded in the spec.
2. The real-file corpus is authored by Claude in draw.io (spec 13.2).
3. Preview confirmation replaces held-back validation (spec 13.3).
