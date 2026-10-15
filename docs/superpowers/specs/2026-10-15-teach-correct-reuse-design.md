# Teach, clarify, correct, reuse: design specification

**Date:** 2026-10-15. **Status:** design approved section by section in conversation; this document consolidates the approved sections and their amendments.
**Inputs:** `docs/PROJECT_RECORD.md` (current state), the owner's plan `Open_Apprentice_Internal_Validation_Build_Plan.md` (15 Oct), the
earlier brief `docs/redesign_brief.md`. Where this spec deliberately deviates from the plan it says so (section 13).

---

## 1. Goal and promise

Build one complete, internally validated product workflow for technical-diagram annotations:

> Teach an editing convention, clarify what you mean, correct an exception, and reuse the resulting skill on unfamiliar diagrams without
> silently losing earlier instructions.

Initial label placement is the entry point; the centrepiece is a **correction whose scope is resolved and whose effects are visible**.
NVIDIA Nemotron-3-Ultra on Nebius Token Factory proposes and revises programs; deterministic code parses, executes, selects questions,
checks evidence, renders and measures. Validation is internal (deterministic simulated teacher, matched baselines, browser tests, owner
walkthroughs). No recruited users, interviews or demand claims.

**Decisions made with the owner (15 Oct):** substantial development availability, and budget available subject to approval (every paid run needs a written manifest and
approval); the submission deadline (30 Oct 2026 17:00 UTC) is a hard constraint; the native format is **`.drawio` only**; held-back validation is replaced by a **budgeted preview confirmation**; durable state
lives in **Google Cloud Storage** (local-folder backend for development); the new flow **becomes the product** and the badge demo moves to an
"Earlier prototype" tab, unchanged and deployed throughout; architecture is **event-sourced sessions with a pure step function**.

---

## 2. Architecture

```
apps/web  ──HTTP──>  api/labels.py (/api/v2; badge /api/* untouched)
                          │
     documents/        teaching/                      skills/ + storage/
     drawio.py         events.py   (typed event log)  versions.py (immutable, content-hashed)
     mapping.py        step.py     (pure: log -> Action)  store.py: GcsStore | LocalStore
                       teacher.py  (four request types)    (CAS manifests, durable ledger)
                       corrections.py (drafts, scope, supersession)
                       executor.py (runs Actions; Cloud Tasks worker / local queue)
     engine (existing locked Chromium): draw.io route renders with pinned viewer-static.min.js -> PNG + measured boxes
```

### 2.1 Pure step function
`step(events, config) -> Action`, where `Action ∈ {WaitForResult, RequestModelProposal, RequestMeasurement, AskTeacher, PresentPreview,
CommitVersion, Abstain}`. It performs deterministic filtering and question selection only; it never calls Nemotron, Chromium, storage or the
teacher. Workers execute actions and append result events. Each action has a stable ID derived from the log state that produced it; replay
never re-issues an action whose result is recorded.

### 2.2 Reused components and their required treatment
| Component | Treatment |
|---|---|
| Rule language + evaluator (`concepts/rules.py`, `rule_text.py`) | reused; draw.io geometry mapped into existing scene semantics; grammar version recorded |
| `fits` | reused; every revision replays **all** active constraints |
| constants guard | kept as a documented heuristic, applied identically to every neural system |
| oracle (`evaluation/labels.py`) | evaluation side only |
| checker | **changed**: remove the exclusion of layout defects the intended output also has; check final positions; intent and layout separate axes |
| import-boundary contract | extended to `teaching/`, `documents/`, `skills/`, `storage/` and new evaluator files |
| `SpendGuard` | same policy; durable atomic reservations (section 3.7) |
| `label_teaching.teach()` | split into `step.py` + helpers; **held-back validation removed** |

### 2.3 Day-one acceptance gate (before expanding implementation)
1. One real `.drawio` file rendered with the pinned local viewer (network blocked), every label located by cell ID, measured in document
   coordinates, patched, re-rendered with the **measured** displacement equal to the requested one, and re-opened with the draw.io CLI with
   the edit preserved.
2. One event-log replay that causes no duplicate effect (no second dispatch, no second paid attempt, no second constraint).
The CLI under Xvfb is an investigated fallback renderer, not an assumed drop-in.

---

## 3. Event log, actions and teacher protocol

### 3.1 Storage layout and commit rule
```
sessions/<sid>/events/<event_id>.json   immutable {event_id, prev_event_id, seq, type, origin, caused_by?, payload, ts}
sessions/<sid>/manifest.json            authoritative mutable session manifest:
                                        {manifest_revision, intent_revision, head_event_id, status, documents, skill_ref, owner}
calls/<action_id>/<attempt_id>.json     reserved -> dispatched -> completed | failed | outcome_unknown
skills/<skill_id>/v<n>.json             immutable version (program, evidence set, retention report, hashes)
skills/<skill_id>/activations/<record_id>.json  immutable {record_id, operation_id, session_id, from_version, to_version, prev_record_id}
skills/<skill_id>/active.json           pointer {version, record_id, generation}; compare-and-set
ledger/manifest.json                    budget state; compare-and-set
documents/<doc_id>/..., runs/<run_id>/...  immutable artifacts + small manifests
```
Event write = write immutable event, then compare-and-set the manifest's `head_event_id` (GCS generation precondition). The event is committed
only if that update succeeds; losing writes are unreachable objects. Replay walks `head_event_id → prev_event_id`, never lists directories.
No multi-object transaction is assumed anywhere. **Authority:** for activation the pointer object is authoritative. An activation first writes an
immutable activation record (operation ID, originating session, from/to versions, predecessor record), then compare-and-sets the pointer
to reference it; records from failed compare-and-sets stay unreachable. The committed history is the record chain reached from the pointer.
Sessions append `VersionActivated` only after the pointer update succeeds; on load, reconciliation walks the committed record chain and
idempotently appends any missing `VersionActivated` events to the originating sessions, never moving the pointer. **Acceptance test:** two
successful activations (one a rollback) with crashes before logging both recover the full, correct history without changing the pointer. `VersionStored` is appended only after the
immutable version object exists.

### 3.2 Two revisions and result acceptance
`manifest_revision` counts every manifest write. `intent_revision` changes only on evidence, mapping, correction scope or active-version
changes. `ActionIssued{action_id, intent_revision, doc_hashes, mapping_hashes, constraints_digest, base_skill_version}`. A result is
accepted if its action is outstanding and those dependencies still hold; otherwise `StaleResultIgnored` is recorded **with its cost booked**.
Housekeeping events never invalidate work.

### 3.3 Event types
Setup: `DocumentImported`, `MappingRecorded`, `DemonstrationRecorded`. Actions/results: `ActionIssued`, `ModelProposalReturned{candidates,
rejections by reason, usage, cost}`, `ModelCallFailed{truncation|timeout|transport|format}`, `MeasurementReturned{boxes, profile}`.
Teacher: `RequestIssued`, `ResponseRecorded`. Outcomes: `VersionStored`, `VersionActivated{from, to, generation}`, `ActivationRejected`,
`Abstained{reason}`, `Errored{reason}`. Corrections: `CorrectionStarted`, `ScopeAuthorized`, `ReplacementApproved`, `CorrectionAbandoned`.
Housekeeping: `StaleResultIgnored`, `Cancelled`, `ConflictDetected{event_a, event_b}`.

### 3.4 Teacher request types (`teaching/teacher.py`, no evaluator imports)
| Request | Content | Responses |
|---|---|---|
| `ChooseOutput` | one registered scene, 2–4 alternatives | choose(X) / none / unsure / cancel |
| `ConfirmPreview` | `purpose ∈ {learning_preview, affected_examples, revision_preview}`; 1–3 identified outputs (affected examples: the displayed replacement outputs, ≤ 6 items) | approve / reject / unsure, **per item** |
| `ConfirmCorrectionScope` | 2–4 explicit interpretations, each with rendered consequences | select(i) / none / unsure / cancel |
| `RequestDemonstration` | one scene to edit | demonstrated output / decline |
A scene must be registered in the session and match its recorded hash (generated probes included once registered). Malformed requests are protocol errors
(`ChooseOutput`: fewer than 2 or more than 4 alternatives or alternatives not separated per 3.6; `ConfirmCorrectionScope`: fewer than 2
or more than 4 interpretations, or two with identical selectors and programs; `ConfirmPreview`: item count outside its purpose's range;
any request: an unregistered scene or hash mismatch); they are raised before the
teacher sees them; never counted as abstention. Every request and response is logged; `source ∈ {human, deterministic_simulator}`.

### 3.5 Constraint semantics (derived from committed events only)
| Event | Constraint |
|---|---|
| initial demonstration | positive: complete before/after on that document; recorded only when the user explicitly confirms "this whole document is right" after editing (untouched labels are then approved as they stand) |
| corrective edit (partial, default) | positive only for masked (moved) labels. Untouched labels receive **no new intent approval**; existing evidence about them stays active unless explicitly superseded; structural preservation (no resize, no text/style/attachment change) still applies, while their coordinates may change only as governed by the authorized scope and approved exceptions |
| choose(X) | positive: X's complete output on that scene (one labelled scene) |
| none | excludes every displayed alternative on that scene; no coordinates delivered |
| unsure / cancel | nothing |
| preview approve | positive on that document's output |
| preview reject | excludes that document's output only (never an aggregate "batch wrong") |
| scope select | `ScopeAuthorized`; predicted consequences are NOT truth |
| affected-example approve | replacement positive constraint for the displayed output (section 5) |
Mechanical feedback (parse, runtime, measured collision) is never intent.

### 3.6 Tolerance and separation
Answers match by maximum coordinate error over identical object identities, tolerance 0.5 document units. The separation rule applies to
`ChooseOutput` only: any two alternatives must differ by
more than 1.0 in at least one corresponding coordinate, so at most one can match. Exact output equality (never tolerance) is used for
grouping. The simulator raises a protocol error on any violation rather than choosing.

### 3.7 Budgets and accounting
Interaction budgets (identical for every system, enforced by `step` and re-checked by the executor):
- **Initial learning cycle:** ≤ 3 `ChooseOutput` interactions (any response), ≤ 1 `RequestDemonstration`, ≤ 1 `ConfirmPreview` of ≤ 3
  documents (documents and labels inspected reported), ≤ **8** provider attempts.
- **Each correction cycle:** the triggering edit is its one corrective demonstration; ≤ **2 clarification interactions in total**, shared
  between `ConfirmCorrectionScope` and `ChooseOutput` (output disambiguation inside the authorized scope); ≤ 1 `ConfirmPreview(affected_examples)`;
  ≤ 1 `ConfirmPreview(revision_preview)` of ≤ 3 documents; ≤ **4** further provider attempts. Benchmark acquisition-plus-first-correction episode:
  ≤ 12 attempts in total.
- Retries count; at most 1 retry per call, only for truncation/timeout/transport. Duplicate responses (same request ID) are idempotent.
Paid attempts: `reserved → dispatched → completed | failed | outcome_unknown`; a retry is a new `attempt_id`. Budget exposure is exactly
`settled charges + outstanding reservations + conservative exposure of uncertain dispatched attempts`; an attempt is in exactly one of those
categories at a time (settlement replaces its reservation). A crash after dispatch leaves `outcome_unknown`, charged at worst case and
counted. Exactly-once provider execution is NOT claimed; routine duplicate dispatch is prevented by execution claims.

---

## 4. Learning and clarification (apprentice step policy)

**Candidates.** Permanent deduplication only by identical canonical AST. Behaviour grouping is temporary, per searched scene set, by exact
output. Every distinct surviving program stays until evidence rejects it.

**Filtering (identical for every neural system):** parse and validate → limits (depth 8, 300k statements/program, ≤ 32 objects) → replay every
active constraint → forbidden effects (only mapped label x/y change) → admissibility heuristic. Rejections recorded by reason.

**Policy (first applicable rule):**
0. Outstanding action → `WaitForResult`.
1. No proposals → `RequestModelProposal(initial)`.
2. Pool empty → contradiction revision if unused this cycle, else `Abstain("no acceptable program found within the search limits")`.
3. ≥ 2 distinct programs → bounded disagreement search: batch documents first, then ≤ 128 generated probes per round, aggregate budget
   5,000,000 evaluator statements per round, cache keyed by program + scene + evaluator version + measurement profile (disposable).
   Probe families: obstacle across a placement boundary, narrower canvas, node resize (labels re-measured), observable role flip, small fresh
   arrangement; probes that change text are out of release 1. Usable probe: 2–4 exact output groups pairwise separated per 3.6; score = pairs
   separated by the question as shown; tie-break batch > fewer changed attributes > fewer objects > stable order. Generated probes are
   rendered and must match their selection geometry before display. → `AskTeacher(ChooseOutput)` if budget remains, else rule 5.
4. One program, or search found nothing → contrastive round if unused this cycle, re-filter, repeat 3; otherwise go to 6 with the search
   outcome recorded: `completed_no_disagreement | budget_exhausted | candidates_failed_on_inputs` (the last two are never "one behaviour").
5. Disagreement found, question budget exhausted → `Abstain("unresolved disagreement")`.
6. Final decision:
   ```python
   if can_commit:                                   return CommitVersion(selected)
   if approval_is_only_missing_condition and preview_unused: return PresentPreview(selected, docs)  # ≤ 3 unlabelled batch docs, different branches
   return Abstain(reason)
   ```
   `selected` is chosen deterministically among the surviving programs that are indistinguishable on the searched scenes: smallest
   canonical AST (node count), then lexicographically smallest canonical hash. **Acceptance test:** an approved preview yields exactly one
   `VersionStored`; replaying the log stores nothing further.

**Two layers of commit checks.** *Shared checks* (every system, enforced by the executor): valid program, consistent with all active
evidence, required approvals present (≥ 1 approved preview item, no unresolved rejection), dependencies current, preservation and layout
checks pass, and for corrections the correction authorization of section 5. *Apprentice policy* (A, C and D only): the bounded
disagreement search must have completed without finding a distinguishing question. B chooses its own questions and stopping behaviour
within the shared budgets and commits whenever the shared checks pass; any wrong commitment is exposed by held-out scoring.
**Acceptance test:** B can legally commit an approved, compliant program without invoking A's question-selection policy.

**Commit predicate (A, C, D).**
```python
can_commit = (selected_valid and fits_all_active_constraints
              and search_outcome == "completed_no_disagreement"
              and approved_preview_count >= 1 and no_unresolved_rejection
              and dependencies_current)
```
An approval stays valid only while the selected program produces exactly the approved output. "Unsure" documents remain visibly unapproved
and grant no application authorization. After a preview rejection: the output becomes an exclusion, the contradiction revision runs if
unused, and control returns to rule 0 (no shortcut to commit). Commit claim: "consistent with all evidence; approved on N previewed documents;
no distinguishing alternative found over M searched scenes", never global equivalence.

**Allowances per cycle:** one initial proposal round, at most one contrastive round, at most one contradiction revision (shared by empty-pool
and rejected-preview cases); allowances are recorded events so replay cannot re-trigger them.

**Outcome accounting.** Recovered call failure (retry succeeded) ≠ candidate rejection ≠ terminal `error` (provider/format failure with no
retries left) ≠ `abstain` (completed search with no acceptable program, or unresolved disagreement).

**Prompts.** Text rule language; identical grammar documentation and examples for every neural system; each example's structure recorded in
the protocol. Structures used by final beyond-catalogue tasks are "not explicitly demonstrated in the prompt" (never "unseen"). If parse
failures dominate in calibration, a development-only sensitivity check with structured JSON output for both systems decides the frozen
representation; final tasks stay untouched.

---

## 5. Corrections

**Trigger.** The user edits a displayed application result, bound to `{run_id, output_artifact_hash}` from active version vₖ. A
`CorrectionDraft{base_version, base_pointer_generation, corrective_evidence, authorized_scope, proposed_supersessions, approved_replacements}`
holds everything; the active version's evidence is never touched; replay uses the draft constraint set.

**Three document states:** `original_input → output_from_vₖ → user_corrected_output`. Revised programs run on `original_input`.
Partial correction (default) uses a label mask; a complete demonstration requires an explicit per-document "this whole result is right".

**Scope.** Selectors are rule-language expressions over **role, attachment and original-input geometry**, evaluated on the original input
with the fixed mapping (never influenced by the candidate). Branch information is explanatory only; no `fallback_taken` language feature.
Clarification inside a correction uses the shared budget of two interactions (scope selection and, if programs still disagree inside the
authorized scope, one `ChooseOutput`). **Acceptance test:** scope selection → output disambiguation → affected-example approval → revision
preview completes within budget, and each response creates only its intended evidence (scope authorization never approves predicted outputs).
Interpretations: revised skill with selector (model-proposed, checked); one-document override (sidecar pin, no skill change); accidental
edit (dismissed). Only "revised skill" counts as learning. Each model interpretation must fit the corrective evidence and all active
constraints except its exactly computed conflict set (its proposed supersessions).

**Acceptance test (untouched labels):** correcting one warning label can update another warning label inside the approved scope, while an
unrelated note stays unchanged.

**Affected examples.** Reviewed with one `ConfirmPreview(affected_examples)`. Stored per approval: scene, mapping, changed label IDs, proposed outputs and hashes, approving event. A label may
change only if inside the authorized selector or covered by an explicitly approved per-label exception; anything else is a scope violation
and blocks. Approvals create **replacement positive constraints**; old constraints are marked superseded in the draft pointing to their
replacement; supersession requires a teacher event (never a model suggestion). Approval covers displayed outputs only.

**Revision preview** (≤ 3 documents): one where the correction applies, one unaffected, one boundary/fallback case where available.

**Retention report** (stored with the version, shown in the UI): retained (every active constraint checked, outcome), superseded (with
approving events), replacements, scope violations (must be 0), unexplained regressions (must be 0), coverage (scenes, branches, search
limits). Claim wording: "no unexplained regressions on the checked evidence and scenes".

**Correction commit predicate.** `can_commit` from section 4 evaluated over the draft constraint set (including the revision preview as its
approval), AND `scope_violations == 0` AND `unexplained_regressions == 0` AND every proposed supersession approved by a teacher event.

**Activation.** Each version stores its own evidence set. Activation is one compare-and-set against the pointer generation captured when the
correction began; if it moved (even back to k) → `ActivationRejected`, offer rebase. On any failure: "this correction does not change the
active pointer". Stored ≠ active ≠ applied, and the UI shows each. Rollback = activate any stored version by compare-and-set.

**Conflicts.** Definite only when the acceptable output sets (under tolerance) cannot intersect for identical complete learner-visible input
and context under the current instruction version; intentional changes become conflicts only without authorized supersession. A
leave-one-out diagnostic may propose a question; it never deletes evidence or blames the user. Duplicate corrections are detected by
idempotency key; content hashes only flag likely duplicates.

---

## 6. draw.io documents

**Format and route.** Native input and primary output is the `.drawio` file (uncompressed or compressed pages). The SVG download is serialized from the same engine render (it may contain
`foreignObject` HTML labels; it is a convenience export, not the editing target); previews are PNG. (Deviation from the plan's SVG-first §8, see section 13.)

**Editing area.** One selected page; editing rectangle `(0, 0, pageWidth, pageHeight)` in document coordinates; requires `pageScale=1`.
`page="0"`, other page scales, or content outside the rectangle (including negative coordinates) are release-1 product limitations,
refused with a reason.

**Parsing.** expat; reject DTDs, entity declarations and external entities; allow predefined escapes and numeric character references;
upload ≤ 2 MB; decompression aborts above 4 MB decoded; limits on depth, cell count and value length; UTF-8 only; unique cell IDs and valid
parents; missing `x`/`y` means 0 and the patcher inserts the attribute (tested). `UserObject`/`object` wrappers: unsupported for moving in
release 1, kept as obstacles.

**Cell statuses.**
| Status | Treatment |
|---|---|
| supported movable label: `vertex=1`, style `text;`, parent is a layer, absolute geometry, rotation 0, rendered single line | mappable, editable |
| reliably measured fixed object: rectangular nodes, other shapes, unmapped/unsupported labels, group children (container not double-counted) | preserved; obstacle |
| unmeasurable relevant object | blocks application with a reason |
Edges are preserved; connector crossings are not checked (stated in every receipt). Limits: ≤ 32 objects, ≤ 16 movable labels.

**Mapping.** Proposed nearest node by box distance, role "note", marked proposed; the user confirms or edits; sidecar
`{doc_hash, page_id, labels:{cell_id:{node_id, role}}, confirmed_by_event}` bound to the document hash; changes raise `intent_revision`;
mapping time counts in task timings. Roles are free text, lower-cased.

**Rendering and measurement** (engine route, network blocked): pinned local `viewer-static.min.js` (hash recorded); scale 1; wait for
`document.fonts.ready` plus two animation frames. Bundled Liberation Sans (file hashes recorded) is mapped onto `Helvetica` locally and on
Cloud Run; the file keeps requesting Helvetica; other unbundled fonts → refusal. Primitives: HTML label in `foreignObject` = `Range` over its
text nodes (union of client rects) plus visible background/border/padding from computed style; SVG `<text>` = `getBBox` through its
transform; fixed shapes = draw.io cell-state bounds cross-checked with the rendered element. Elements are located through draw.io's
cell → state → node association. One composed document→screen transform, inverted once. Quantum 1/64. A node mismatch above 0.5 (after
stroke) blocks editing. Rendered single-line check from line rects. **Drift report:** each document is also measured under the draw.io CLI
export on the authoring Mac (real Helvetica) and the maximum box difference is reported; receipts say "measured under profile P; other font
environments may differ by up to Δ (measured)". The drift report needs the draw.io CLI, so it exists for the corpus files measured during development; for user
uploads in the deployed service the receipt says the drift is "not measured". Font normalization is out of release 1.

**Scene, targets and arithmetic.** A label's scene box is its measured box; offset `d = box − geometry` stored; target geometry =
`target_box − d`. Values kept separately: exact rational target, serialized coordinate (nearest 1/64, ties to even; error ≤ 1/128 added to
the conformance tolerance), measured result.

**Patching and publication.** Validate source hash, page, mapping and every `expected_old`; locate `<mxGeometry>` structurally; byte-span
replace or insert from the end backwards; write a **new artifact**; parse, render, measure, check; publish only if every check passes.
Uncompressed pages: bytes outside edited spans identical. Compressed pages: patch decoded XML, write that page uncompressed, preservation
claimed at model level; other pages' bytes identical. Preservation check also covers the edited cell's other content, page settings,
wrappers, ordering and metadata. Output must stay under the re-import limit.

**Output checks (separate axes, final positions):** conformance (measured final boxes vs program targets), preservation (only allowed
attributes on allowed cells), layout safety (inside the editing rectangle, no overlap with any other final box; axis-aligned, touching
allowed), intent (approved examples, or hidden truth in evaluation). Post-patch: position, width/height, offset `d`, text and style.

**Round-trip test matrix:** compressed and uncompressed pages; multi-page with untouched-page bytes; left/centre/right-aligned labels; HTML
and plain-text labels; nonzero viewer translate; font substitution; fractional target requiring rounding; missing coordinates (inserted);
explicit refusals for an unmeasurable object and out-of-rectangle content.

---

## 7. Evaluation

**Separation.** Learner runner (A/B/C/D) process: import-boundary contract + Python import audit hook raising on `open_apprentice.evaluation*`
+ spec files absent from its environment. Teacher simulator process: loads the hidden spec, speaks the section 3.4 protocol over JSON lines,
logs every exchange; `ChooseOutput` matched with tolerance and separation; `ConfirmPreview` per document; `ConfirmCorrectionScope` scored by
meaning: each selector evaluated on a predefined diagnostic set of label situations and matched against the intended scope exactly on that set
(a bounded check, labelled so); no match → "none", never nearest; accidental-edit and override choices follow the scenario script and never
count as learning; `RequestDemonstration` returns the spec's output. Evaluator process: holds fresh scoring documents and specs, scores after
the episode ends.

**Systems (same model, budgets, filters, grammar documentation and examples).**
- **A** apprentice.
- **B** same-model agent (shared commit checks only, section 4) with the same request types as tools: `register_probe(scene)` (same domain, limits, validation, render-match),
  `ask_choose(scene_id, programs[2..4])` (separation enforced), `preview(doc_ids ≤ 3, program)`, `request_demo(scene_id)`,
  `propose_scope(selector, program)`, affected-example approval, revision preview and commit through the same safety checks; all of A's
  mechanical feedback.
- **C** catalogue learner: A's policy with candidates from a permitted module `concepts/catalogue_programs.py` (24 programs as ASTs,
  no evaluator imports); abstention on beyond-catalogue tasks is legitimate; strata reported separately.
- **D** ablation: A's own finite set of legal questions per step, selection uniform over that set with a manifest seed.

**Final battery (36 episodes, authored and frozen before any learner run).**
| Stratum | n | Definition |
|---|---|---|
| catalogue | 8 | 4 clarification-required, 4 identifiable; existing 24-spec family |
| beyond catalogue | 8 | ≥ 4 specs not demonstrated in prompts: gap `min(24, max(8, w/10))`, role-conditional sides, fallback chain right→below→left, size-dependent side |
| inconsistent | 4 | identical complete learner-visible inputs and context with incompatible required outputs; pass = conflict surfaced or confirmation requested, no invented exception |
| unsupported / impossible | 4 | unobservable condition (stress test: wrong commit fails, ask→abstain/refuse passes); convention forcing overlap or off-canvas (refuse to apply); unsupported draw.io structure (refuse with reason) |
| sequential corrections | 12 | 8 compatible or explicitly superseding, 4 intentional conflicts |
Clarification-required = ≥ 2 consistent behaviours across the declared space after the demonstrations, marked privately at authoring time.
Layout strata: jittered grid (new seeds), rows/columns, sparse clusters, narrow canvases; final seeds disjoint from development. Three fresh
scoring documents per learning episode; corrections scored on changed scope and unaffected retention separately.

**Real-file corpus.** Six diagrams authored by Claude in the actual draw.io editor (app.diagrams.net through browser automation, saved as
`.drawio`); if a specific editor step is impossible from this environment, the owner is asked for that concrete step early. Provenance per
file: author, editor version, steps, file hash, date. All six are authored on 16 Oct (WP0), before any import code exists. Three are development files; the three final files are hashed
and moved the same day to `benchmarks/final/drawio/` (git-ignored via `.gitignore`; evaluator-only; the learner-process audit hook and environment of section 7 keep it unreadable during runs) and are
not opened by any development code or by Claude until the WP5 frozen run; their hashes and provenance are committed. No tuning on the frozen three; results described as within-family generalization unless crossing sources or generators. Synthetic
parser fixtures are separate.

**Manifests.** Private manifest: episode IDs, generator version and seeds, spec hashes, category marks, evaluator paths, code commit, prompt
hashes, model ID and settings, budgets, tolerance, measurement profile, scoring version. Learner-projected manifest: opaque episode IDs only.
Full reproducibility artifacts are published after evaluation.

**Outcome record.**
```python
terminal_outcome: correct_complete | wrong_commit | appropriate_refusal | unnecessary_abstention | error
diagnostics: unsafe_proposal_blocked, preservation_violation_blocked, provider_failures, protocol_failures, parse_failures, budget_exhausted
```
Correction episodes report end-to-end success (including acquisition) and correction success given acquisition with its denominator.

**Analysis.** Unit = episode (36). Per episode `A_rate − B_rate` over the repeats; primary effect = mean episode difference within the declared
stratum; paired bootstrap over episodes keeping all repeats; exact sign test on positive vs negative differences, ties reported. Two primary
endpoints reported regardless of outcome: learning success (16 learning episodes) and correction success. Results also per behaviour spec.
Intervals describe this task collection only.

**Funded tier and gates (fixed before final execution).** Tier T3 (proposed): 3 repeats of A and B on all 36 episodes (216 runs) + D on the 8
clarification-required episodes × 3 (24 runs) = 240 runs, estimate $36–72, re-estimated after calibration. A smaller tier, if chosen, is chosen
before any final result. Zero-violation requirements apply across every final attempt; count thresholds (the plan's §12.2) apply in each
complete repeat; repeat-to-repeat variation reported; a missed gate is reported as missed (no best-repeat selection). A and B alternate in
seeded blocks. No early stop on good results; a budget stop keeps partial results and reports coverage. Release-blocking failures: any
information-boundary violation, any accepted preservation violation, any unexplained retention regression, any unlabelled replay/fixture
shown as live. A post-freeze fix gets a new version identifier; affected slices are re-run under it; the original rows stay published.

**Paid-run gating.** Calibration (5 development episodes × A, B) has its own manifest and needs the owner's approval before any spend; then the
funded tier's manifest needs approval. Every manifest states task IDs, attempt ceilings, worst-case reservation, actual-cost estimate, stop
conditions, the protected $10 reserve and what conclusion the run can establish.

---

## 8. API and UI

**Ownership.** Anonymous owner credential (random ID in a signed `HttpOnly` cookie); every resource records and checks its owner.

**Routes (`/api/v2`; a test asserts legacy routes do not shadow them).**
| Route | Notes |
|---|---|
| `POST /documents` | parse/validate now; support report; rendering continues as an operation |
| `POST /documents/{id}/mapping` | confirm/edit mapping → `mapping_hash` |
| `POST /sessions` | `{documents:[{doc_id, page_id, mapping_hash, measurement_profile_hash}], demonstrations:[{document_ref, before_scene_hash, edits, mask}], idempotency_key}` → `202`, `operation_id`, status URL |
| `GET /sessions/{id}` | derived state, outstanding request (`request_id`, `intent_revision`), budgets, recorded / reserved / uncertain spend, `manifest_revision` |
| `POST /sessions/{id}/responses` | accepted only if the request is outstanding and its intent revision current |
| `POST /sessions/{id}/cancel`, `POST /runs/{id}/cancel` | stop new authorizations; late usage still booked; late results cannot resume |
| `POST /skills/{id}/versions/{v}/apply` | `202`, creates a run |
| `GET /runs/{id}` | per-document application results |
| `POST /skills/{id}/corrections` | `{base_version, base_pointer_generation, run_id, output_artifact_hash, edit, mask, full_approval, idempotency_key}` |
| `POST /skills/{id}/activate` | `{version, expected_generation, idempotency_key}` |
| `GET /runs/{id}/export` | `.drawio`, SVG, receipt |
| `POST /internal/tasks/{action_id}` | Cloud Tasks only: verify OIDC token for the expected service account and audience; load action; take/check execution claim; re-check cancellation, dependencies, budget; duplicate delivery returns existing status |

**States** (derived): teaching `imported → mapped → teaching → (waiting_for_model | waiting_for_answer)* → preview_ready → committed`;
correction `draft → (waiting_for_model | waiting_for_answer)* → review → stored → activated | activation_rejected | failed`; errors and
cancellation are terminal. Polling every 2 s; responses carry `manifest_revision` and stale ones are ignored; reload resumes the stored session.

**Screens.** Import and map; Teach (drag labels, then an explicit "this whole document is right" confirmation records the demonstration); Clarify (2–4 rendered alternatives + None / Not sure / Cancel); Preview (per document Approve / Reject /
Not sure; blocked documents with reasons); Correct (partial by default; explicit per-document full approval); Review revision (scope options
with rendered consequences, per-item affected-example approval, behaviour diff, retention table); Reuse and export. Optional evidence panel
(programs, hashes, candidates, search outcome, event log). Scope/superseded/unexplained use text and icons as well as colour.

**Previews and overlays.** PNG from the same engine pass as the measurements, bound to `{scene_hash, render_revision}`; one composed
transform document → exported image → displayed image (crop, padding, scale, letterbox, zoom), inverse for pointer input; drag shows a marked
ghost; on drop a deterministic draft render (no model) replaces image and geometry together; a demonstration is recorded only after the user
has seen that render. Keys: arrow = 1 unit, Shift = 10, Alt = 1/64. Safety wording: "Previews are displayed in image context; uploaded
content is separately validated and rendered in the locked engine."

**Provenance** per run and artifact, two dimensions: Model {Live, Recorded, Fixture} × Teacher {You, Simulated}.

**Paid mode.** Enabled server-side for the deployed demo only; clients cannot override; global cap = durable ledger; per-session caps from
3.7; per-client rate limits. When the cap is reached: "Live inference is unavailable. Open the recorded example." (its own documents and
session; never a silent swap). The badge flow stays under "Earlier prototype", unchanged.

---

## 9. Testing

- **A. Offline (pytest):** hand-calculated oracle cases; teacher isolation (audit hook, monkeypatched oracle raising, spec files absent,
  "none" gives no free example, baselines offered the same request types); every invariant in sections 3–5; draw.io parser and patcher on the
  round-trip matrix (script-generated fixtures in `tests/fixtures/drawio/`, labelled synthetic).
- **B. Property and state sequences (Hypothesis):** generated teach / answer / preview / correct / activate / rollback / duplicate delivery /
  stale result / fault-injected crashes (before or after manifest CAS, after dispatch). Invariants: one committed chain; no active constraint
  lost without approved supersession; pointer changes only through CAS; budgets never exceeded; exposure accounting with each attempt in
  exactly one category, reservation acquired atomically and replaced at settlement, uncertain exposure retained after a crash and never
  silently dropped or retried without accounting; replay effect-free; duplicate delivery never dispatches an already-claimed attempt.
  Order/naming checks only where declared neutral. Profiles: `ci` (derandomized, 200 examples), `dev` (wider).
- **C. Browser-backed:** Node tests for the draw.io engine route (render, measure, PNG); Playwright journey with a scripted provider
  (import → map → teach → clarify → correct → activate → apply → export, plus reload, duplicate request, cancel, cap reached, legacy tab);
  pinned PNG snapshots as regression checks only.
- **D. Live evaluation:** section 7, after manifest approval.
- **E. Owner walkthroughs:** six task cards (import and map, teach, clarify, correct an exception, recover from an unsupported file, reuse and
  export) recording active and waiting time, mapping/answer/edit counts, mistakes, developer help; one card also done by hand in draw.io for a
  time comparison. Internal inspection, not a user study.
- **CI.** GitHub Actions on Python 3.12 runs the relevant checks per change; the complete applicable suite (property `ci` profile, draw.io
  engine tests, journey test) runs at integration and release gates. The full local suite runs before every push. Test output is always read
  before claiming success.

---

## 10. Deployment

- **Early staging integration (17–20 Oct):** on a staging Cloud Run service: render and measure one supported diagram with the pinned viewer
  and bundled font; one real GCS conditional update (and a lost-race case); one authenticated Cloud Tasks dispatch with a scripted provider;
  restart the service and verify persisted state. A concrete staging-resource proposal with a cost estimate is presented for approval first;
  offline work continues meanwhile.
- **Release (27–28 Oct):** production bucket, queue, service account and Cloud Run revision; cold-start timing; durable cap verified across a
  restart; badge prototype still served.

---

## 11. Schedule (Singapore dates)

| Dates | Work package |
|---|---|
| 15–16 Oct | WP0: implementation audit; real-file corpus authored in draw.io (final three frozen); round-trip test (gate 2.3); event store (local backend); step skeleton; teacher protocol; boundary tests; hidden validation removed |
| 17–18 Oct | WP1: versions, drafts, supersession, rollback; GCS backend; stateful tests; staging proposal |
| 19–20 Oct | WP2: draw.io import, mapping, measurement, patching, matrix; `/api/v2` core; teach/apply/export screens; staging integration |
| 21–22 Oct | WP3: clarify UI and probes; correction and review UI; Cloud Tasks; durable ledger |
| 23–24 Oct | WP4: journey tests; owner walkthroughs; calibration (approval); protocol and manifests frozen |
| 25–26 Oct | WP5: final battery at the approved tier; frozen real-file tests |
| 27–28 Oct | WP6: release deployment; cold start; durable cap; video draft |
| 29–30 Oct | WP7: README and claims aligned; owner makes the repo public, records the video, submits |

**Stop-or-change gates** (end of 18, 20, 22, 24 Oct) as in the plan's §14. **Scope cuts, in order:** (1) fewer optional repeats, the smaller
tier chosen before final results; (2) D reduced to a small predefined diagnostic subset; (3) fewer probe families and narrower search;
(4) generated probes removed entirely only if unreliable or if batch questions demonstrate the capability adequately. A matched A-versus-B
comparison is always kept; without D, the contribution of question selection is reported as unestablished. Never cut: the information
boundary, real rendering, preservation, retention, the complete flow.

**Owner actions:** approve the staging-resource proposal (by ~17 Oct); approve the calibration manifest, then the funded tier (~23 Oct);
approve production resources (before 27 Oct); make the repo public, record the video, submit (29–30 Oct); perform the walkthroughs (23–24 Oct).

---

## 12. Deliverables

`docs/implementation_audit.md`, `docs/internal_validation_protocol.md`, updated `docs/claims_and_limitations.md`, `docs/demo_script.md`,
`docs/PROJECT_RECORD.md`; private and public manifests; result tables and failure breakdowns; reproduction instructions; real-file provenance;
an example saved skill and receipt without secrets; this spec and the implementation plan under `docs/superpowers/`. A sanitized reproducible
evidence subset is committed (credentials and private data excluded; whether model transcripts are included is recorded).

---

## 13. Deviations from the owner's plan (recorded)

1. **Native format `.drawio`, not SVG** (plan §8). SVG is a download; previews are PNG. Reason: draw.io's SVG export renders labels as HTML in
   `foreignObject` with a fallback `<text>`, adds a DOCTYPE, an external link and style blocks, and exposes IDs only on wrapper groups; the
   `.drawio` model gives stable cell IDs and plain geometry. Users keep editable source.
2. **Six diagrams authored by Claude in draw.io** rather than by the owner (owner's amendment), with the owner asked only for concrete steps
   Claude cannot perform.
3. **Preview confirmation replaces held-back validation** (plan §2.2), as a budgeted, logged teacher interaction available equally to every system.
