# Plan 6 execution rulings and review outcomes

Copied from the execution ledger (git-ignored, deleted after the final review). Each ruling names its cost if wrong.

- Task 2: Ruling: the layout refusal checks only documents where the person placed labels by hand (demonstrations, requested demonstrations, the corrective edit), not every registered document or approved judgement — refusing whenever any batch/probe output collides would block valid rules (the API already blocks such preview items; obstacle probes make correct answers collide by design) — cost if wrong: an overlap shown only through choices/previews is not refused.
- Task 2/3: Ruling: Tasks 2 and 3 land together (3f53329) — Task 2's B tests need Task 3's clean battery — cost if wrong: none.
- Task 3: Ruling: clean truth layouts are required where hand placements can happen (base: demos + batch + corrective target; corrected: target), not on scoring/diagnostic documents (the scorer already excuses intended collisions) — requiring all scenes made sequential episodes unbuildable — cost if wrong: none for refusal fairness.
- Task 3: Ruling: sequential episodes draw only from the uncrowded layouts (columns, sparse; compatible tall-node demos from sparse) and drop the batch-separation requirement ("right" vs "right else below" never differ there; A can still probe) — otherwise "right, no fallback" could not be collision-free by hand — cost if wrong: less layout variety in the 12 sequential episodes.
- Task 4: Ruling: the earlier calibration rows are NOT rescored — the dev battery was re-frozen (same ids, new content), so they stay under battery-v2.3/score-v2.1 as history; the scoring version is bumped to score-v2.2 — cost if wrong: none.
- Task 5: Ruling: B's correction cycle gets 4 attempts plus its learning cycle's unused attempts (12 - learning attempts used, at least 4) — every B decision is a provider call, so a strict 4 cannot reach scope -> preview -> commit; the spec's episode total of 12 is kept — cost if wrong: B gets more correction calls than A uses.
- Task 5: Ruling: B gets an `ask_scope` option with no candidates (override / accidental only) once a proposal round has run and nothing is admissible — mirrors A's policy; without it the teacher's override answer is unreachable — cost if wrong: none.
- Task 5: Note: the scripted correction fixture policy's test was written after the policy (fixture code, mock-only).
- Task 6: Ruling: under parallel workers a row's cost is its learner's own settled ledger total (provider-reported, worst case for unknown), not the shared-ledger delta, which overlapping runs make unattributable — cost if wrong: none; the run total still comes from the shared ledger.
- Task 6: Ruling: `oa eval manifest` writes either a calibration manifest or (--funded) the two funded manifests; D's cost per episode is taken as A's (same policy and calls) until measured — cost if wrong: a re-estimate.
- Task 7: Ruling: a publish check counts against a committed rule only where the true behaviour passes it on that file (same excuse as the scorer's layout check); a page publish refuses (e.g. a label off the page) counts as failing every check — cost if wrong: none.
- Task 7: Ruling: real-file behaviours are drawn only from conventions with a fallback or a below placement (18 of 24); on the dev files "right, no fallback" cannot even be published, so it would make the publish check vacuous; re-frozen as battery-v2.5 without opening the final files — cost if wrong: less spec variety on 3 secondary episodes.
- Task 7: Ruling: the funded A/B manifest includes the 3 real-file ids; their episodes are built at final-run time from the hash-checked files (engine required) — cost if wrong: none.
- Task 8: Ruling: the live re-check replaced the inconsistent episode with a second sequential template (inconsistent was tested twice live, code unchanged) — cost if wrong: refusal on inconsistent not re-confirmed under battery-v2.5.
- Task 8: Note: after the live re-check two fixes landed offline and are NOT yet verified live: B's layout feedback, and the shared scope proposer's patch composition.
- Final: fixed C1 (real-file episodes had no batch, so no system could ever preview or commit) — test_a_real_file_episode_can_actually_be_solved_by_a_learner (mock A and B commit and score correct) RED→GREEN; episode k now demonstrates on file k, shows file k+1 as the batch and is scored on the remaining file only (1 scoring document for 3 files; freshness kept).
- Final: fixed I1 (scope patch spliced as text could break out of its selector) — test_a_patch_cannot_break_out_of_its_selector, test_a_patch_with_its_own_loop_or_object_scan_is_rejected, test_an_unusable_selector_is_dropped_before_composing RED→GREEN; composition now on the syntax tree.
- Final: fixed I2 (real .drawio files were not hash-checked in the final run) — test_a_changed_real_file_is_refused_not_silently_scored RED→GREEN; hashes checked on build and again on the publish check.
- Final: fixed I3 (a worker exception discarded finished, paid rows) — test_a_worker_exception_keeps_every_finished_row_and_still_writes_the_manifest RED→GREEN.
- Final: fixed I4 (run cap and reserve could be overshot by parallel learners) — test_concurrent_guards_cannot_both_start_a_call_that_only_one_budget_fits RED→GREEN; cross-process lock plus reserve/release rows counted as exposure.
- Final: fixed I5 (B's larger correction effort undisclosed) — test_correction_effort_is_recorded_per_row, test_report_discloses_correction_effort_per_system RED→GREEN; a per-system effort section and an explicit note in the report. B's proposer rounds are not capped (disclosure chosen over a cap: B's decisions are model calls).
- Final: Ruling: T7 real-file ids stay in the funded A/B manifest (the C1 fix makes them solvable) — cost if wrong: 18 runs on a secondary stratum.
- Final: Ruling: I5 — B's correction budget stays as ruled (4 plus unused learning attempts, at most 12) and is disclosed rather than capped — cost if wrong: the correction comparison favours B's effort.
- Final: minor (deferred): few paths in the correction trace fixture (ChooseOutput in scope, unapproved revision preview, clarification exhausted, layout refusal) and the `revise_preview_unsure` scenario name
- Final: minor (deferred): no tests that B's correction commit option is absent for a pending supersession, a scope violation, an unexplained regression or a layout refusal
- Final: minor (deferred): B can commit a candidate it never previewed (revision_preview_used is shared across candidates)
- Final: minor (deferred): B gets no feedback when its correction commit is refused for layout (the option just disappears)
- Final: minor (deferred): scope-proposer retries are not counted in B's attempts
- Final: minor (deferred): max(4, left) could exceed 12 if the learning cycle ever used more than 8
- Final: minor (deferred): final runs get a `cal-` run id and measured_episode_usd globs cal-* (final rows would feed later estimates)
- Final: minor (deferred): --resume does not check the run directory belongs to the same manifest
- Final: minor (deferred): the funded D manifest lists final clarification marks (note in docs/decisions.md)
- Final: minor (deferred): the correction layout refusal also checks unmasked labels (possible false refusal in the product)
- Final: minor (deferred): local import in teaching/step.py works around a cycle
