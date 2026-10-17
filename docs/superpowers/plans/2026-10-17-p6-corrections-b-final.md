# Corrections that work, B's own correction tools, and a final-ready battery (Plan 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the evaluation ready for the funded run on the final split. The live calibrations
(`docs/evaluation/calibration_results.md`) found four problems, and this plan fixes them:
1. Correction scope inference failed for both systems (0/2).
2. A forced-overlap convention was committed.
3. Running out of attempts was scored as a refusal.
4. B's corrections ran A's policy.

It also adds the final-split live path: committed hashes, parallel workers, the real-file episodes, and the funded
manifests. The plan stops before the funded run, which needs the owner's approval.

**Architecture:**
- Shared fixes go into `teaching/` (selector admissibility, the layout refusal in every commit path) and
  `prompts/correction_scope.md`, so A, B, C and D change alike.
- B's correction cycle becomes its own option-protocol agent (`learner/agent_b_correction.py`). It reuses the
  correction policy's request builders and commit predicate, which are factored out of `correction_step` without
  changing A's behaviour.
- The battery generator guarantees clean layouts everywhere except the forced-overlap episode, and both splits are
  re-frozen. No learner has run on the final split.

**Tech Stack:** Python 3.12; existing `teaching`, `learner`, `evaluation`, `drawio` packages; the engine for real files.

**Spec:** `docs/superpowers/specs/2026-10-15-teach-correct-reuse-design.md`: §4 (shared commit checks, B), §5
(corrections, scope selectors), §7 (battery, systems, outcomes, funded tier, real-file corpus).

## Global Constraints

- **Boundary:** learner code (`learner`, `teaching`, `concepts`, `providers`) never imports `open_apprentice.evaluation`
  (import-linter contract 2). The learner process audit hook stays as built.
- **Shared change:** every system gets the same filters, budgets and grammar text. A shared change is made in `teaching/` or
  a shared prompt, never in one system's code.
- **No final peeking:** no development code or test reads `benchmarks/final/`, except the evaluator's gated final-run
  path. Tests use `build_battery("final", TEST_FINAL_BASE)` and the dev draw.io corpus.
- **Budgets (spec 3.7, unchanged):**
  - learning: ≤ 3 ChooseOutput, ≤ 1 RequestDemonstration, ≤ 1 preview of ≤ 3 documents, ≤ 8 attempts;
  - correction: ≤ 2 clarifications (scope and ChooseOutput, shared), ≤ 1 affected-examples review, ≤ 1 revision
    preview of ≤ 3 documents, ≤ 4 attempts.
- **Money:** no paid call except Task 8's dev re-check (approved by the owner: about $1, cap $1.50). Every live run goes
  through the gate, under `caffeinate -s`, plugged in.
- **Commits:** conventional; full suite on 3.13 and 3.12 at the end; black, ruff, `PYTHONPATH=src lint-imports`.

## Review Focus

1. **A's behaviour does not change** from the `correction_step` refactor in Task 5. Every existing correction test
   passes unchanged, and a property test compares the action sequences of the old and new code on scripted logs.
2. **Layout refusal vs demonstrated overlap.** A rule whose output on a registered document puts a moved label off the
   page or over another object is never committed. The refusal reason names the document and label (Task 2 test).
3. **Re-frozen battery.** No non-forced-overlap episode has an off-page or overlapping truth output on any of its
   scenes; the forced-overlap episode does (Task 3 test).
4. **B's correction tools cannot bypass the correction commit predicate.** A `commit` option appears only when the
   predicate holds: scope authorized, supersessions approved, revision preview approved, 0 scope violations,
   0 unexplained regressions (Task 5 test).
5. **Final-run integrity.** A tampered final file gives a clean "refused: hash mismatch" from the CLI, not a traceback
   (Task 6 test). Real-file episode scoring never opens a final file outside the gated run (Task 7 test runs only on
   the dev corpus).

---

### Task 1: Scope selectors generalise (shared)

**Files:**
- Modify: `src/open_apprentice/teaching/correction_step.py` (`_admissible`)
- Modify: `prompts/correction_scope.md`
- Test: `tests/unit/teaching/test_scope_admissibility.py`

**Interfaces:**
- `_admissible(c, d)` returns None when `magic_condition(parse_selector(c["selector"]))` holds: a selector that
  compares raw geometry or an id with a non-zero constant, e.g. `object(o.attached).h == 80`. `magic_condition` comes
  from `concepts.label_teaching` and is the same filter learning rules get. Role and kind strings stay allowed.
- **Prompt:**
  - the selector example `object(o.attached).w > 120` is replaced by `o.role == "warning"` and
    `o.w > object(o.attached).w` (a label wider than its node);
  - one added sentence: "Compare values of the diagram with each other (a label's or node's sizes and positions)
    rather than with fixed numbers; fixed sizes copied from the corrected diagram are rejected."
  - The battery's template selectors (`w <= h` of the node) are not shown.

- [ ] Tests:
  - `object(o.attached).h == 80` is not admissible;
  - `o.role == "warning"` and `object(o.attached).w <= object(o.attached).h` are admissible;
  - the existing correction tests still pass.

  RED → GREEN → commit `fix(teaching): correction scope selectors may not compare geometry with constants; scope prompt asks for relations`.

### Task 2: Refuse to apply a convention that leaves the page or overlaps (shared commit checks)

**Files:**
- Create: `src/open_apprentice/teaching/layout.py`
- Modify: `teaching/step.py` (rule 6, before `CommitVersion` and before a preview), `teaching/correction_step.py`
  (before `CommitCorrection`), `learner/agent_b.py` (`t_commit` and the `commit` option)
- Test: `tests/unit/teaching/test_layout_refusal.py`

**Interfaces:**
- `layout_problems(rule, scenes: dict[str, dict]) -> list[str]`: for each scene, the moved labels of `run_output(rule, scene)`
  whose box is off the canvas or overlaps any object other than the label and its own node. Entries look like
  `"b1: l3 leaves the page"` or `"d0: l2 overlaps n4"`. It is the same geometry as `labels._layout_violations`, written
  again in `teaching` because `teaching` may not import the evaluator.
- **Every commit path:** if `layout_problems(selected, ev.scenes)` is non-empty →
  `Abstain("refusing to apply: " + first 3 problems)`.
  - In `step`, this is checked before the preview, so no approval is asked for a refused rule.
  - In B, the `commit` option is not offered, and `t_commit` refuses with the same text.

- [ ] Tests:
  - a right-placement rule on a narrow page abstains with "leaves the page";
  - a clean rule still commits;
  - B's commit option is absent for the refused rule;
  - a correction whose revision overlaps abstains.

  Commit `feat(teaching): refuse to apply a convention that leaves the page or overlaps (all systems)`.

### Task 3: Clean battery layouts except the forced-overlap episode; re-freeze

**Files:** Modify `src/open_apprentice/evaluation/battery_v2.py`; Test `tests/unit/evaluation/test_battery_v2.py`

**Interfaces:**
- `_clean(spec, scenes) -> bool`: no off-page or overlapping truth output on any scene. It uses `labels._layout_violations`.
- Retry rules (`_Retry`):
  - every learning, inconsistent, unobservable, unsupported-structure and sequential episode must be clean on demo,
    batch and scoring scenes, for its base spec and, for sequential episodes, its corrected spec (target and scoring
    scenes);
  - the forced-overlap episode must have a demo whose truth output leaves the page.
- `GENERATOR_VERSION = "battery-v2.4"`.

- [ ] Tests:
  - every non-forced-overlap episode of dev and of the stand-in final (`TEST_FINAL_BASE`) is clean on all its scenes;
  - the forced-overlap episode is not clean;
  - 4 random final bases still build 36 episodes.
- [ ] Re-freeze both splits:
  - `oa eval freeze --split final` and `--split dev`;
  - regenerate `docs/evaluation/battery_final.md` and `battery_final.hashes.json` (no seed base in them);
  - note in the doc that the v2.3 freeze was replaced before any final run because its truth layouts were not clean.

  Commit `fix(evaluation): clean truth layouts except the forced-overlap episode; re-freeze (battery-v2.4)`.

### Task 4: Running out of attempts is not a refusal (scoring, both systems)

**Files:** Modify `evaluation/run_v2.py` (`score`), `evaluation/analysis_v2.py` (report); Test `tests/unit/evaluation/test_run_v2.py`, `test_analysis_v2.py`

**Interfaces:**
- **Terminal outcome:** an outcome whose terminal reason is attempt exhaustion is `error`, with diagnostic
  `budget_exhausted=True` and `failure="attempts_exhausted"`. The reasons are `budget exhausted: N provider attempts`
  (B) and `provider: attempt budget` (A's executor). This is consistent with A, whose executor already records it as
  `Errored`.
- **`refusal_kind` diagnostic** for `appropriate_refusal` rows: `no_program` (no acceptable program),
  `unresolved_disagreement`, `refused_layout` (Task 2), `unsupported_structure`, `agent_abstained` (B's own
  `abstain`).
- **Report:** a refusal-kind breakdown per system.

- [ ] Tests:
  - B's "budget exhausted: 8 provider attempts" on an inconsistent episode is `error`/`attempts_exhausted`, not a
    refusal;
  - A's "no acceptable program" on the same episode is a refusal with `refusal_kind=no_program`;
  - the report shows the breakdown;
  - re-scoring the kept calibration rows (`rescore`) changes only the affected rows.

  Commit `fix(evaluation): attempt exhaustion is an error for every system; refusals carry their kind`.

### Task 5: B's own correction cycle (option protocol)

**Files:**
- Create: `src/open_apprentice/learner/agent_b_correction.py`
- Modify: `teaching/correction_step.py` (factor out the request builders and the commit predicate; A unchanged),
  `learner/main.py` (`system_b` uses it), `prompts/agent_b_correction.md` (new; the same rule-language slice as the
  other prompts)
- Test: `tests/unit/learner/test_agent_b_correction.py`, `tests/unit/teaching/test_correction_step_refactor.py`

**Interfaces:**
- **Factored out of `correction_step`** (pure, deterministic; `correction_step` calls them and its action sequences
  are unchanged):
  - `admissible_candidates(events, d) -> list[dict]`;
  - `scope_request(events, d, chosen: list[dict]) -> AskTeacher` (the current `_ask_scope`, over the given 1–2
    candidates);
  - `inside_scope(d, cands) -> list[dict]`;
  - `affected_request(events, d, sel, config) -> Optional[PresentPreview | Abstain]`;
  - `revision_request(events, d, sel, config) -> Optional[PresentPreview | Abstain]`;
  - `commit_or_reason(events, d, sel) -> CommitCorrection | Abstain` (the correction commit predicate of spec 5, plus
    Task 2's layout refusal).
- **`run_b_correction(provider_factory, log, teacher, ledger, scope_proposer, worst_usd, config=CorrectionConfig()) -> str`**
  returns a `CorrectionExecutor` status string. It is an option-protocol loop like `agent_b`. Each turn B picks one id:
  - `propose_scope`: one call of the shared scope proposer (A's `correction_scope.md` call). It counts against the
    4 attempts.
  - `ask_scope:S1[,S2]`: `ConfirmCorrectionScope` over B's chosen 1–2 admissible candidates, plus override and
    accidental. Offered while no scope is authorized and clarifications remain.
  - `ask_choose:DOC:S1,S2`: after authorization, between in-scope candidates that disagree on DOC.
  - `affected:S1`: review of S1's affected examples. Offered when S1 has pending supersessions and the review is
    unused.
  - `revision_preview:S1`: offered when S1 has no pending supersessions and the revision preview is unused.
  - `commit:S1`: offered only when `commit_or_reason` returns `CommitCorrection` for S1.
  - `abstain`.
  - The teacher's override or accidental answer is recorded automatically, as in A: it is the teacher's choice, not
    B's.
  - Requests are delivered and recorded through the `CorrectionExecutor` methods (`_ask`, `_propose`, `_commit`), so
    validation, the ledger and activation are shared.
- `system_b`: after a learning commit and activation, the correction runs through `run_b_correction`. The rows' `correction_policy="B"`.

- [ ] Tests:
  - **Property test:** on 6 scripted correction logs (compatible, superseding, conflict, override, accidental, and
    none-then-revision), the refactored `correction_step` returns the same actions as before (expected sequences
    recorded from the current code before the refactor, as a fixture);
  - B with scripted choices commits a correct revision through scope → revision preview → commit;
  - B's `commit` option never appears before an approved revision preview, nor with a pending affected example;
  - a third clarification is not offered;
  - `propose_scope` runs the shared scope proposer and counts as an attempt;
  - the teacher's override is recorded without a B turn.

  Commit `feat(learner): system B's own correction cycle with the shared request builders and commit predicate`.

### Task 6: Final-split live path, parallel workers, funded manifests

**Files:** Modify `evaluation/run_v2.py` (`run_live_battery`), `evaluation/manifests_v2.py`, `cli.py`; Test `tests/unit/evaluation/test_run_v2.py`, `test_manifests_v2.py`

**Interfaces:**
- `run_live_battery(..., workers: int = 1)`:
  - **Split:** `split="final"` loads with `load_split(BATTERY_DIRS["final"], expected=committed hashes from
    docs/evaluation/battery_final.hashes.json)`. Dev runs as today.
  - **Workers:** run in a `ThreadPoolExecutor(workers)`, in the seeded alternating order. The submission loop stops on
    a boundary violation or when `cap - spent_for_run < MIN_CALL_USD × workers`, so in-flight runs can still finish
    under the cap.
  - **Rows** are appended under a lock.
- CLI: `oa eval run ... --workers N`. A `FrozenMismatch` becomes `refused: hash mismatch: <file>`, exit 2 (Review Focus 5).
- **Funded tier = two manifests** (the gate binds one run shape):
  - `funded_T3_AB`: A and B × 3 repeats on all 36 final episodes;
  - `funded_T3_D`: D × 3 on the clarification-required final episodes. The evaluator reads their ids from the
    private final manifest at manifest-writing time, through the gated final path.
  - Estimates come from calibrations 1–2 (A ≈ $0.11, B ≈ $0.19 per episode).

- [ ] Tests:
  - a tampered final file gives a clean refusal;
  - 4 workers produce one row per run and never exceed the cap (fake runs that spend);
  - a boundary-violation row stops new submissions;
  - the two funded manifests have the right run counts and task ids.

  Commit `feat(evaluation): gated final-split runs with committed hashes, parallel workers, funded manifests`.

### Task 7: Real-file final episodes (engine-backed)

**Files:** Create `src/open_apprentice/evaluation/real_files.py`; Modify `evaluation/run_v2.py`; Test `tests/integration/test_real_file_episodes.py` (dev corpus only, `OA_ENGINE_TESTS=1`)

**Interfaces:**
- `real_file_episode(files: list[Path], k: int, spec: VSpec, engine_url) -> Episode`:
  - each `.drawio` page goes through the existing pipeline: `load_drawio` → `classify` → `render_page` →
    `mapping.propose` → `build_scene`, giving its movable-label scene;
  - episode k's demonstration is file k's page with the spec's truth applied;
  - the batch is empty, and the scoring scenes are the other two files' pages, which are fresh to the learner;
  - stratum `real_file`; it is reported separately as within-family generalisation (spec 7).
- **Scoring** uses `score` on the scenes. In addition, `drawio/publish.py`'s preservation and overlap checks run on
  the committed program's output for each scoring file; a failed publish check counts as `wrong_commit`.
- **Final run only:** `run_live_battery(split="final")` builds the 3 real-file episodes from the hash-checked
  `benchmarks/final/drawio/f1–f3`, using the specs frozen in the private manifest. Dev tests build the same from
  `tests/fixtures/drawio_corpus/dev/d1–d3`.

- [ ] Tests (engine running):
  - dev real-file episodes build with ≥ 1 movable label per page;
  - a correct program scores `correct_complete`, and a wrong one `wrong_commit`;
  - a publish preservation failure counts as `wrong_commit`;
  - no code path opens `benchmarks/final/` outside the gated final run (static check on the call sites).

  Commit `feat(evaluation): real-file episodes through the draw.io adapter and publish checks`.

### Task 8: Offline dry run and the approved dev re-check (≈ $1)

- [ ] **Offline:** `oa eval run --split dev --systems A,B,C,D --mode mock` then `oa eval report`. Expected:
  - 0 boundary violations;
  - the forced-overlap episode now `appropriate_refusal` (`refused_layout`) for every system;
  - every row mock/Fixture.

  Commit the dry-run report as "offline dry run — not a model result".
- [ ] **Live:** manifest for A and B on 3 dev episodes (sequential, unsupported/forced overlap, inconsistent), cap
  $1.50. The owner approved about $1 for this in chat on 2026-10-17. Run it with `--workers 2` under `caffeinate -s`.
  Record the results in `docs/evaluation/calibration_results.md`, then **stop and ask the owner** to approve the two
  funded manifests.

## Final verification

- The full suite passes on 3.13 and 3.12. `lint-imports` keeps both contracts. Black and ruff are clean.
- Both splits are re-frozen, and the new hashes are committed.
- Spend is only Task 8's re-check, and it is logged under its run id.
