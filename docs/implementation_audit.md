# Implementation audit: spec → code

Spec: `docs/superpowers/specs/2026-10-15-teach-correct-reuse-design.md`. Plans: `docs/superpowers/plans/`. Status values:
**implemented** (code + test in this repository), **planned** (named plan), **deviation** (recorded difference from the spec).
Updated at the end of Plan 1 (branch `p1-foundations`).

| Spec § | Requirement | Code | Status | Evidence |
|---|---|---|---|---|
| 2.1 | Pure `step(events, config) -> Action`; no model/browser/storage/teacher calls | `teaching/step.py` | implemented | `tests/unit/teaching/test_step.py` (7 tests) |
| 2.2 | Rule language + evaluator reused | `concepts/rules.py`, `concepts/rule_text.py` (unchanged) | implemented | existing suites |
| 2.2 | `fits` replays all active constraints on every step | `teaching/step.py:_filter` (calls `concepts/hypotheses.fits` for every derived constraint) | implemented | `test_step.py` |
| 2.2 | Constants guard kept as a documented heuristic, same for every system | `concepts/label_teaching.magic_condition` used by `_filter` | implemented (baselines: Plan 5) | `test_step.py` |
| 2.2 | Held-back validation removed from the new learning path | `teaching/` never calls the old `label_teaching.teach`; the old loop is kept only to reproduce earlier results | implemented | `teaching/` import graph; `test_isolation.py` |
| 2.2 | Checker change (no exclusion of defects the intended output shares; final positions) | `evaluation/labels.check_after` | planned (Plan 3, with the draw.io output checks) | — |
| 2.2 | Import-boundary contract extended | `pyproject.toml` (2 contracts) | implemented | `lint-imports`: 2 kept, 0 broken |
| 2.3 (1) | draw.io round trip: render, measure, patch, re-open | `scripts/spikes/` | planned (Task 0 of Plan 1, needs the owner's download approval) | — |
| 2.3 (2) | Effect-free event-log replay | `teaching/executor.py` (claims by action id) | implemented | `test_executor.py::test_replay_is_effect_free` |
| 3.1 | Immutable events + manifest compare-and-set; replay walks the chain | `storage/store.py`, `teaching/events.py` | implemented | `test_store.py`, `test_events.py` (orphan event, concurrent writers) |
| 3.1 | Activation records and pointer | — | planned (Plan 2) | — |
| 3.2 | `manifest_revision` vs `intent_revision` | `teaching/events.py` | implemented (storage); dependency-based acceptance of late results: Plan 4 | `test_events.py` |
| 3.3 | Event types | `teaching/events.py` (`INTENT_TYPES`), payloads in `step.py`/`executor.py` | implemented (learning subset); correction types Plan 2 | tests above |
| 3.4 | Request types + validation | `teaching/teacher.py` (ChooseOutput, ConfirmPreview with purposes, RequestDemonstration) | implemented; ConfirmCorrectionScope Plan 2 | `test_teacher.py` |
| 3.5 | Constraint semantics from committed events | `teaching/constraints.py` | implemented (learning rows); corrective-edit and scope rows Plan 2 | `test_constraints.py` |
| 3.6 | Tolerance 0.5, separation > 1.0 for ChooseOutput | `teaching/teacher.py`, `evaluation/teacher_sim.py` | implemented | `test_teacher.py`, `test_teacher_sim.py::test_ambiguous_match_is_protocol_error` |
| 3.7 | Budgets (3 choose, 1 preview ≤ 3 items, ≤ 8 attempts) | `teaching/step.py:StepConfig` | implemented (RequestDemonstration budget enforced when the step issues it: Plan 4) | `test_step.py` |
| 3.7 | One retry for transient provider failures; retries count | `teaching/executor.py:_propose`, `step.py` attempt counting | implemented | `test_executor.py::test_one_transient_failure_is_retried_and_stays_in_the_accounting` |
| 3.7 | Exposure accounting, one state per attempt | `teaching/accounting.py` | implemented | `test_accounting.py` |
| 4 | Step policy rules 0–6, commit predicate, deterministic selection | `teaching/step.py` | implemented (batch documents only) | `test_step.py` |
| 4 | Generated probes, aggregate evaluation budget | — | planned (Plan 4; `StepConfig.max_evaluations` declared) | — |
| 4 | Error vs abstain accounting | `step.py` (`Error` on terminal provider failure) | implemented | `test_step.py::test_provider_failure_terminal_is_error_not_abstain` |
| 5 | Corrections, drafts, scope, supersession, retention, activation | — | planned (Plan 2) | — |
| 6 | draw.io import, mapping, measurement, patching | — | planned (Plan 3) | — |
| 7 | Simulator teacher in a separate process | `evaluation/teacher_sim.py`, `teaching/teacher.SubprocessTeacher` | implemented | `test_teacher_sim.py::test_subprocess_teacher_round_trip` |
| 7 | Learner-process isolation (audit hook) | `teaching/isolation.py` | implemented | `test_isolation.py` |
| 7 | Baselines B/C/D, manifests, battery | — | planned (Plan 5) | — |
| 7 | Real-file corpus authored in draw.io, final three frozen | — | planned (Task 1 of Plan 1, needs the owner's download approval) | — |
| 8 | API and UI | — | planned (Plan 4) | — |
| 10 | Staging and release deployment | — | planned (Plans 2–3 staging, Plan 6 release) | — |

## Deviations
1. `.drawio` native format instead of SVG (spec 13.1). Recorded in the spec.
2. The real-file corpus is authored by Claude in draw.io (spec 13.2).
3. Preview confirmation replaces held-back validation (spec 13.3).
