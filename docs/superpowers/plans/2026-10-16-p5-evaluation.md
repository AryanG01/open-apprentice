# Evaluation Implementation Plan (Plan 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Measure whether the apprentice (A) learns and corrects label conventions better than the same model acting freely (B), on a
  frozen 36-episode battery. The battery is scored by an independent evaluator and a simulated teacher in separate processes, with a
  catalogue learner (C) and a random-question ablation (D).
- Everything up to the paid runs is built and verified offline. Paid runs start only after the owner approves a priced manifest.

**Architecture:**
- **Evaluator side** (`open_apprentice/evaluation/`, never importable by learners):
  - authors the battery: hidden specs, oracles, scenes, fresh scoring documents;
  - runs the simulated teacher as its own process;
  - spawns one learner process per episode;
  - scores the result after the episode ends;
  - analyses per-episode paired differences.
- **Learner side** (`open_apprentice/learner/`, new, under the "never import the evaluator" contract, with the audit hook installed at
  start):
  - reads only the learner-visible episode (scenes, demonstrations, batch documents);
  - talks to the teacher over JSON lines;
  - runs system A, B, C or D;
  - prints its outcome.

**Tech Stack:** Python 3.12; the existing `teaching` core, `evaluation.labels` oracle family, `evaluation.teacher_sim`, `evaluation.metrics.paired_cluster_bootstrap`, `evaluation.spend.SpendGuard`; `subprocess` for process separation.

**Spec:** `docs/superpowers/specs/2026-10-15-teach-correct-reuse-design.md` section 7 (Evaluation), 9 D/E, 3.7 budgets, 4 (A's policy), 5 (corrections).

## Global Constraints

- **Information boundary:**
  - Learner code (`open_apprentice.learner`, `teaching`, `concepts`, `providers`) never imports `open_apprentice.evaluation`. This is
    enforced by import-linter: add `open_apprentice.learner` to contract 2.
  - The learner process installs `teaching.isolation.install_learner_guard()` before importing anything else of ours.
  - The learner process is given only the learner-visible episode file, and runs in a temporary directory without `benchmarks/`.
  - The teacher process loads the private episode. The evaluator scores after the learner exits.
- **Frozen battery:** the final 36 episodes are authored and frozen before any learner run on them, with final seeds disjoint from
  development seeds.
  - The private manifest lives in `benchmarks/final/battery/` (git-ignored). Only its hashes and the learner-projected manifest
    (opaque ids) are committed.
  - No development code reads `benchmarks/final/` except the evaluator's final-run command.
- **Systems** share the model, budgets (spec 3.7), filters, and grammar documentation and examples:
  - **A** is the apprentice step policy.
  - **B** is a same-model agent with the same request types as tools and only the shared commit checks.
  - **C** is A's policy with a 24-program catalogue as its candidate source.
  - **D** is A's policy with uniform random selection among A's legal questions (manifest seed).
- **No paid call in this plan.** Live mode runs only through `oa eval run --live --cap-usd X` under `SpendGuard` and the owner-approved
  manifest.
  - The current budget (`results/redesign/budget.json`: $50 authorized, $10 reserve, about $38.60 already spent) leaves about $1.40
    spendable. The calibration and funded tiers therefore need the owner to authorize and fund more first.
  - Offline runs label every row `origin=mock` with `model=Fixture`, and are never reported as model results.
- **Outcome record** (spec 7):
  - `terminal_outcome ∈ {correct_complete, wrong_commit, appropriate_refusal, unnecessary_abstention, error}`;
  - diagnostics: `unsafe_proposal_blocked, preservation_violation_blocked, provider_failures, protocol_failures, parse_failures, budget_exhausted`.
- **Analysis:**
  - the unit is the episode, using per-episode `A_rate − B_rate` over repeats;
  - paired bootstrap over episodes, keeping all repeats;
  - an exact sign test, with ties reported;
  - two primary endpoints, always reported: learning success (16 learning episodes) and correction success (12);
  - intervals describe this task collection only.

## Review Focus

1. **Boundary leak:** a learner process that tries `import open_apprentice.evaluation.labels`, opens a file under `benchmarks/`, or
   reads an environment variable naming the private manifest gets an error, and the episode is recorded as `error` (a release-blocking
   failure is counted). (Task 4 test.)
2. **Teacher scoring by meaning:** a correction-scope answer is matched on the diagnostic set, never "nearest". With no match the
   teacher answers `none`; override and accidental choices follow the script and never count as learning. (Task 3 test.)
3. **Scoring on fresh documents:** a rule that reproduces the demonstrations but differs on a fresh scoring document is
   `wrong_commit`, not `correct_complete`. (Task 8 test.)
4. **Paid-run safety:** `oa eval run --live` without an approved manifest id, or with a cap above the manifest's ceiling, or when
   `SpendGuard` reports the reserve would be touched, refuses before any provider call. (Task 11 test.)
5. **Freeze integrity:** changing one byte of a frozen private episode makes `oa eval run --split final` refuse with a hash mismatch.
   (Task 2 test.)

---

### Task 1: Beyond-catalogue behaviour specs and scene strata (evaluator-only)

**Files:** Create `src/open_apprentice/evaluation/specs_v2.py`, `tests/unit/evaluation/test_specs_v2.py`

**Interfaces:**
- `@dataclass(frozen=True) class VSpec: kind: str; params: tuple` with kinds:
  - `catalogue` (wrapping a `labels.Spec`);
  - `gap_by_width` (gap = `min(24, max(8, w/10))` of the label's node, side right);
  - `role_sides` (notes right, warnings below, gap g);
  - `fallback_chain` (right → below → left, blocked = off the page or overlapping a non-anchor object);
  - `size_side` (right if node w > h, else below);
  - `unobservable` (a hidden per-label flag, as in `labels._unsupported_oracle`).
- `oracle_v(spec: VSpec, scene) -> dict[str, tuple[F, F]]`: plain Python, sharing no code with `concepts/rules`.
- `scene_v(stratum: str, seed: int) -> dict` with strata `grid` (the existing `labels.make_scene`), `rows`, `columns`, `sparse`, and
  `narrow` (canvas width 600). It is deterministic per seed.

- [ ] Tests:
  - each oracle on hand-built scenes (for example `gap_by_width` on a 140-wide node gives gap 14, and on a 50-wide node gives gap 8);
  - `fallback_chain` takes the left side when right and below are blocked;
  - strata are deterministic and keep every object inside the page;
  - oracles never move nodes.

  RED → implement → GREEN → commit `feat(evaluation): beyond-catalogue behaviour specs and scene strata`.

---

### Task 2: Battery authoring, freeze, and manifests

**Files:** Create `src/open_apprentice/evaluation/battery_v2.py`, `tests/unit/evaluation/test_battery_v2.py`; Modify `src/open_apprentice/cli.py` (`oa eval freeze`)

**Interfaces:**
- `@dataclass class Episode`:
  - `id` (opaque);
  - `stratum ∈ {catalogue, beyond, inconsistent, unsupported, sequential}`;
  - `spec: VSpec`;
  - `demo_scenes`, `demo_outputs`, `batch_scenes`, `scoring_scenes` (three fresh documents);
  - `clarification_required: bool`;
  - `correction: Optional[dict]` (for sequential: the corrected spec, the target document, the mask, the intended scope selector,
    the diagnostic scenes, and `kind ∈ {compatible, superseding, conflict, override, accidental}`);
  - `seed`.
- `build_battery(split: str) -> list[Episode]`:
  - The final split has the spec's 36 episodes:
    - catalogue 8 (4 clarification-required and 4 identifiable, marked by checking that ≥ 2 catalogue behaviours fit the
      demonstrations);
    - beyond 8 (≥ 4 distinct specs not in the prompt examples);
    - inconsistent 4 (identical learner-visible inputs with incompatible required outputs);
    - unsupported 4 (unobservable condition; a convention that forces overlap or off-page placement; and an unsupported structure,
      such as a rotated label in a synthetic scene, refused with a reason);
    - sequential 12 (8 compatible or superseding, 4 conflicts).
  - The development split has 18 episodes with the same strata at half size, and disjoint seed bases (development 110_000,
    final 170_000).
- **Real-file episodes** (spec 7, frozen real files): three extra final episodes on `benchmarks/final/drawio/f1–f3`.
  - Each gets a catalogue spec drawn at freeze time with a seeded choice that is recorded in the private manifest.
  - Their scenes come through the draw.io adapter and the engine; scoring publishes through `drawio/publish.py`, so every check
    applies.
  - They are read only by `oa eval run --split final` and reported separately as within-family generalisation. Before that run, the
    freeze command records only their hashes, which already match `docs/corpus/drawio_provenance.md`. It never opens their
    contents.
- `learner_view(ep) -> dict`: demo scenes with their demonstrated outputs and the batch scenes. No spec, no scoring scenes, no marks.
- `freeze(split, out_dir) -> dict`:
  - writes `episodes/{id}.private.json` and `learner/{id}.json` into `out_dir`;
  - writes `manifest.private.json` (episode ids, generator version, seeds, spec hashes, category marks, code commit, scoring version,
    tolerance) and `manifest.public.json` (opaque ids only);
  - returns the content hashes;
  - `verify_frozen(out_dir)` recomputes them.
- `oa eval freeze --split final` writes to `benchmarks/final/battery/` (git-ignored) and prints the hashes. The hashes and the public
  manifest are committed to `docs/evaluation/battery_final.md`. `--split dev` writes to `benchmarks/development/battery/` (committed).

- [ ] Tests:
  - stratum counts are exact (36 final, 18 dev);
  - dev and final seeds are disjoint;
  - the learner view holds no spec or scoring keys;
  - clarification-required marks are true exactly when ≥ 2 catalogue behaviours fit;
  - the inconsistent episodes really share inputs;
  - changing one byte of a frozen private file makes `verify_frozen` fail (Review Focus 5).

  RED → implement → GREEN.

- [ ] **Freeze the final battery** (`oa eval freeze --split final`). Commit only `docs/evaluation/battery_final.md` (hashes, public
  manifest, generator commit) plus the dev battery files. Commit `feat(evaluation): 36-episode battery, development split, freeze with hashed manifests`.

---

### Task 3: Teacher simulator for the battery

**Files:** Modify `src/open_apprentice/evaluation/teacher_sim.py`; Test `tests/unit/evaluation/test_teacher_v2.py`

**Interfaces:**
- `SimTeacher` accepts a `VSpec` (through `oracle_v`) and an episode's correction script. Its subprocess `main(private_episode.json, log.jsonl)` loads the private episode, so scope answers work in subprocess mode (fixing the gap where `main()` never passed `scope_intent`).
- **`ConfirmCorrectionScope`:**
  - for a `revise` interpretation, evaluate its selector on the episode's diagnostic scenes and match the intended scope exactly;
  - its consequences must match the corrected spec within the 0.5 tolerance;
  - no match gives `none`, never the nearest;
  - for an `override` or `accidental` script, select that kind.
- `RequestDemonstration` returns the spec's output. Inconsistent episodes answer with the conflicting output the script names.
- Every exchange is logged.

- [ ] Tests:
  - a near-miss selector gets `none` (Review Focus 2);
  - a script with the override kind picks override;
  - the subprocess round trip works through `teaching.teacher.SubprocessTeacher` on a sequential episode.

  RED → implement → GREEN → commit `feat(evaluation): battery teacher simulator with scope answers by meaning`.

---

### Task 4: Isolated learner process

**Files:** Create `src/open_apprentice/learner/__init__.py`, `src/open_apprentice/learner/main.py`; Modify `pyproject.toml` (contract 2 gains `open_apprentice.learner`); Test `tests/unit/learner/test_learner_main.py`

**Interfaces:**
- `python -m open_apprentice.learner.main --episode learner.json --system A|B|C|D --teacher-cmd "<argv json>" --mode mock|live --seed N --out outcome.json`:
  1. Install the isolation guard first.
  2. `chdir` into a fresh temporary directory.
  3. Refuse to start if a `benchmarks/` path is reachable from the cwd, or if the episode file sits under `benchmarks/final/`.
  4. Build a `LocalStore` in the temporary directory.
  5. Register the scenes and demonstrations as events.
  6. Run the system with a `SubprocessTeacher(teacher_cmd)`.
  7. Write `{"system", "status", "program", "evidence_summary", "events", "usage", "spend"}`.
- **Synthetic probes:** the probe renderer accepts the selection geometry as-is (`ProbeResult(ok=True, scene=probe.scene)`), because
  battery scenes are exact rational geometry with nothing to render. This is recorded in every outcome as `probe_render="synthetic"`.

- [ ] Tests:
  - the learner process imports no `open_apprentice.evaluation` module (checked through `sys.modules` in the child);
  - an injected `import open_apprentice.evaluation.labels` inside the child fails, and the outcome is `error` with
    `boundary_violation=true` (Review Focus 1);
  - an episode file under a `benchmarks/final` path is refused;
  - an offline A run on a dev episode reaches a terminal status.

  RED → implement → GREEN; `lint-imports` shows the contract kept. Commit `feat(learner): isolated learner process with the audit hook and a learner-only episode view`.

---

### Task 5: System C — catalogue learner

**Files:** Create `src/open_apprentice/concepts/catalogue_programs.py`, `tests/unit/test_catalogue_programs.py`

**Interfaces:**
- `CATALOGUE: tuple[tuple[str, list], ...]`: 24 `(name, rule AST)` pairs for side ∈ {right, below} × fallback ∈ {none, the other side} × scope ∈ {all, notes} × gap ∈ {8, 12, 16}.
  - Built in the rule text language and parsed, independently of `evaluation.labels`, which concepts may not import.
- `CatalogueProposer` with the `Proposer` protocol returns every catalogue program that fits the evidence, within the same tolerance
  as the learner.

- [ ] Tests: 24 distinct programs; each equals `evaluation.labels.rule_for_spec` on 30 probe scenes (the **test** may import the evaluator; the module must not); on beyond-catalogue evidence the proposer returns [] (abstention is legitimate). RED → implement → GREEN → commit `feat(concepts): the 24-program catalogue as an independent candidate source (system C)`.

---

### Task 6: System D — uniform question selection

**Files:** Modify `src/open_apprentice/teaching/step.py`; Test `tests/unit/teaching/test_step_uniform.py`

**Interfaces:**
- `StepConfig.question_selection: str = "best"` (or `"uniform"`) and `StepConfig.seed: int = 0`.
- With `uniform`, rule 3 collects every usable question (batch, then probes) and picks one by
  `codec.digest([seed, len(events)])`, interpreted as an integer modulo the count. That is deterministic for replay. Everything else is
  unchanged.

- [ ] Tests:
  - `best` reproduces today's choice;
  - `uniform` with two usable questions picks each for some seeds;
  - the same seed and log give the same choice.

  RED → implement → GREEN → commit `feat(teaching): uniform question selection for the ablation (system D)`.

---

### Task 7: System B — same-model agent with tools

**Files:** Create `src/open_apprentice/learner/agent_b.py`, `prompts/agent_b.md`; Test `tests/unit/learner/test_agent_b.py`

**Interfaces:**
- `run_agent_b(provider_factory, log, teacher, ledger, budgets, worst_usd) -> str` (terminal status). It is a JSON tool loop. Each
  model turn returns exactly one tool call:
  - `propose(rules_text[])` (parsed and filtered with A's filters, with mechanical feedback);
  - `register_probe(scene_edits)` (same domain, limits and validation as A's probes; synthetic render-match);
  - `ask_choose(scene_id, programs[2..4])` (separation enforced by `validate_request`);
  - `preview(doc_ids ≤ 3, program)`;
  - `request_demo(scene_id)`;
  - `commit(program)`;
  - `abstain(reason)`.

  For corrections it also gets `propose_scope(selector, program)`, affected-example approval and the revision preview.
- **Shared commit checks only:** valid program, consistent with all active evidence, ≥ 1 approved preview, no unresolved rejection,
  preservation and layout checks. B chooses its own questions and its stopping point.
- **Budgets (spec 3.7):** ≤ 3 ChooseOutput, ≤ 1 RequestDemonstration, ≤ 1 preview of ≤ 3 documents, ≤ 8 provider attempts. Every
  call goes through the durable ledger at worst case.
- **Prompt:** `prompts/agent_b.md` uses the same grammar documentation and examples as `prompts/hypotheses_labels.md` (imported by
  reference, so the shared part is the same text).

- [ ] Tests (MockProvider scripts):
  - B can legally commit an approved, compliant program without A's question policy (spec 4 acceptance test);
  - a commit failing the shared checks is refused with mechanical feedback;
  - a fourth ask is refused;
  - a malformed tool call counts as a parse failure, not a crash.

  RED → implement → GREEN → commit `feat(learner): system B, the same-model agent with the shared request types as tools`.

---

### Task 8: Evaluator orchestration and scoring

**Files:** Create `src/open_apprentice/evaluation/run_v2.py`, `tests/unit/evaluation/test_run_v2.py`; Modify `cli.py` (`oa eval run`)

**Interfaces:**
- `run_episode(ep, system, mode, seed, repeat, out_dir, cap) -> Row`:
  1. Write `learner/{id}.json` and the private episode into separate temporary folders.
  2. Start the learner subprocess with `--teacher-cmd` pointing at the teacher simulator on the private file.
  3. Wait, with a per-episode wall-clock limit.
  4. Score.
- **Scoring:**
  - **learning episodes:** run the committed program on the 3 fresh scoring documents with `concepts.rules`. The oracle is the
    episode spec via `oracle_v`.
    - `correct_complete` if all match within 0.5 and the preservation and layout checks of `labels.check_after` pass;
    - `wrong_commit` if any document mismatches;
    - for unsupported or inconsistent episodes, a refusal, abstention or surfaced conflict is `appropriate_refusal`;
    - abstaining where a correct program existed is `unnecessary_abstention`;
    - learner errors are `error`.
  - **sequential episodes:**
    - end-to-end success requires acquisition plus a correct correction (changed scope on the corrected documents, retention on
      unaffected ones), scored separately;
    - correction success given acquisition is reported with its denominator.
  - Diagnostics come from the learner's events and usage.
- Rows (reusing `metrics.Row` plus `stratum`, `terminal_outcome`, `diagnostics`, `origin`, `model`) go to
  `results/eval_v2/<run_id>/rows.jsonl` along with the run `manifest.json`.
- `oa eval run --split dev|final --systems A,B,C,D --repeats N --mode mock|live [--manifest ID --cap-usd X]`. The final split is
  verified frozen first.

- [ ] Tests:
  - a program that fits the demonstrations but not a fresh document is `wrong_commit` (Review Focus 3);
  - an inconsistent episode where the learner surfaced the conflict is `appropriate_refusal`;
  - a sequential episode scores acquisition and correction separately;
  - a mock run over the dev battery for A, C and D completes with every row labelled `origin=mock`, `model=Fixture`.

  RED → implement → GREEN → commit `feat(evaluation): episode orchestration across processes and outcome scoring`.

---

### Task 9: Analysis and report

**Files:** Create `src/open_apprentice/evaluation/analysis_v2.py`, `tests/unit/evaluation/test_analysis_v2.py`; Modify `cli.py` (`oa eval report`)

**Interfaces:**
- `episode_rates(rows, system) -> dict[episode, float]`.
- `paired(rows, a, b, stratum=None, draws=10_000, seed=0) -> {mean_diff, ci95, sign: {pos, neg, ties, p_exact}}`:
  - a paired bootstrap over episodes keeping all repeats (reuse `metrics.paired_cluster_bootstrap`'s resampling);
  - an exact two-sided sign test, `math.comb`-based binomial on non-tied pairs.
- `report(run_dir) -> markdown` contains:
  - **both primary endpoints:** learning success and correction success;
  - per-stratum and per-spec tables;
  - the terminal outcome breakdown, diagnostics, and cost per episode;
  - repeat-to-repeat variation;
  - the release-blocking checks: boundary violations, accepted preservation violations, unexplained retention regressions, and any
    `origin≠live` row presented as live;
  - the sentence "Intervals describe this task collection only."

- [ ] Tests:
  - the sign test on known counts (for example 7 positive, 1 negative gives p = 0.0703) matches hand computation;
  - all ties gives p = 1;
  - the bootstrap is deterministic per seed;
  - the report refuses to present mock rows as model results, and lists release-blocking failures first.

  RED → implement → GREEN → commit `feat(evaluation): paired episode analysis with bootstrap and exact sign test`.

---

### Task 10: Offline dry run of the whole pipeline

- [ ] Run `oa eval run --split dev --systems A,C,D --repeats 1 --mode mock`. A and D use the offline enumerator as a labelled stand-in
  for the model, and C uses the catalogue. B in mock mode uses a scripted MockProvider policy, labelled as a fixture.
- [ ] Then run `oa eval report`. Check every row's origin label, that the boundary check shows 0 violations, and the run time. Commit
  `results/eval_v2/dryrun-*/report.md` labelled **"offline dry run — not a model result"**, and record the per-episode token
  estimate used for pricing in Task 11.

---

### Task 11: Calibration manifest and paid-run gate (stop for the owner)

**Files:** Create `src/open_apprentice/evaluation/manifests_v2.py`, `docs/evaluation/calibration_manifest.md`; Modify `cli.py`; Test `tests/unit/evaluation/test_manifests_v2.py`

**Interfaces:**
- `calibration_manifest(dev_battery, systems=("A","B"), episodes=5, repeats=1) -> dict` contains:
  - the task ids;
  - attempt ceilings (A: 8 + 4 correction attempts; B: the same);
  - the worst-case reservation per attempt;
  - the actual-cost estimate from the Task 10 token estimate × $3.5/M (the output-heavy rate in the live-run cost note);
  - stop conditions: the per-run cap, the global ceiling, and any boundary violation;
  - the protected $10 reserve;
  - what the run can establish (prompt and parse viability and cost per episode, not an A-versus-B result);
  - a manifest id (a hash).
- `oa eval run --live` requires `--manifest <id>` naming an approved manifest (`docs/evaluation/approved/<id>.json`, written only after
  the owner approves in chat) and `--cap-usd ≤ manifest ceiling`. It runs under `SpendGuard` with the budget file, and refuses before
  any provider call otherwise.
- The funded-tier manifest (T3: 240 runs, re-estimated from calibration) is generated but not approved.

- [ ] Tests:
  - live without a manifest refuses;
  - a cap above the manifest ceiling refuses;
  - a `SpendGuard` reserve breach refuses before any provider call, using a provider double that fails if called (Review Focus 4).

  RED → implement → GREEN.
- [ ] Write `docs/evaluation/calibration_manifest.md` with the numbers, and the current budget position: about $1.40 spendable under
  the $50/$10 authorization. **Stop and ask the owner** to approve the calibration manifest, and to authorize and fund the budget it
  needs. Commit `feat(evaluation): priced calibration manifest and the paid-run gate`.

---

## Final verification

- The full suite on 3.13 and 3.12; `lint-imports` with four source packages in contract 2 (`teaching`, `storage`, `drawio`, `learner`).
- The offline dry run report committed. `benchmarks/final/battery/` exists locally, is git-ignored, and its hashes are committed.
- No provider call was made (the spend log is unchanged).
