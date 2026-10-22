# Decisions and deviations

This file records every material departure from `Open_Apprentice_Claude_Code_Build_Spec.md`
(v1.3), per §0's instruction to "record material departures... including the reason and effect
on the research claim." Entries are append-only; append, never rewrite history.

## 2026-10-09 — initial assumptions and conflicts

1. **§24.5's CLI list predates v1.3.** It stops at `oa export-svg` (export only). §6.8/§21.12
   need asset import, element inventory, patch application and trial execution that no listed
   command covers. **Decision:** add `oa import-svg`, `oa svg-apply`, and `oa svg-trial` to the
   CLI surface. These are additions to the documented interface, not replacements. CLI help and
   README will be updated together per §24.2. **Effect on research claim:** none — these are
   plumbing for the v1.3 spike, which is itself explicitly experimental.

2. **Asset provenance is a hard gate, not a checklist item.** §21.12 + [S23]: Vector-Bench's own
   NOTICE.md excludes 20 scenic illustrations from its blanket code license because their
   provenance is unresolved. **Decision:** those 20 assets (and any derivative) will never be
   bundled into this repository, the public demo, or the submission video. Only owner-authored or
   independently provenance-verified assets ship publicly. If replacement assets are used instead
   of excluded ones, the resulting study is reported as an *adapted* evaluation, never as an
   original Vector-Bench benchmark score. **Enforcement:** a committed test will scan the asset
   directory for filenames/hashes against the excluded list before allowing them into the demo
   asset path. **Effect on research claim:** reduces external-lane task count if assets must be
   dropped; honestly reported per §21.12 ("report that instead of quietly simplifying tasks").

3. **Calendar slipped one day.** §23's suggested calendar starts 8 October 2026; implementation
   actually started 9 October 2026. **Decision:** shift every band by one day. Absorb the lost day
   from M5's optional breadth (e.g., fewer formative trials or a narrower v1.3 spike), not from
   the M6 locked study or the final submission buffer. **Effect on research claim:** none, if
   absorbed as planned; will be re-assessed honestly at the M4 gate if the slip compounds.

4. **Repository was not a git repository at start.** `git init` is required by §20 (every run
   needs a commit hash). **Status:** `git init` is currently blocked by this environment's
   sandbox, which denies writes to any path literally named `.git` (confirmed by direct test —
   `touch .git` under the project root fails with `Operation not permitted`, while ordinary file
   and directory writes succeed). The `dangerouslyDisableSandbox` escape hatch did not receive an
   auto-mode classifier verdict after two attempts. **Workaround:** the owner has been asked to
   run `git init` themselves (e.g. via `! git init` in the session). All other M0 work proceeds
   without git in the meantime; nothing here depends on commit history existing yet.

5. **Toolchain verified, with one deviation.** Confirmed via direct version checks: git 2.52.0,
   Python 3.13.5 (system), uv 0.7.13, Node 25.6.0, npm 11.8.0, Docker 28.3.2, Compose v2.39.1,
   arch arm64 (Apple Silicon). §3.4 specifies Python 3.12 and "Node 22.12 or newer within the
   supported Node 22 line." **Decision:** pin the Python *project* interpreter to 3.12 via
   `uv python install 3.12` + `.python-version` (uv manages this independently of the system
   Python 3.13.5, so no system change is needed). For Node: the host's global Node (25.6.0, an
   odd/non-LTS "Current" release, not a declared LTS line) exceeds §3.4's declared line, and no
   version manager (nvm/n/volta) is installed. Pin `compose.yaml`'s containers to `node:22-slim`
   so the *authoritative* runtime matches the spec exactly regardless of host Node. For the native
   dev fallback, declare `"engines": {"node": ">=22.12 <23 || >=24 <25"}` in `package.json` so a
   mismatch is a visible warning, not a silent substitution, and document that native-mode
   contributors should use Node 22 LTS via their own version manager. **Effect on research claim:**
   none — this only affects development ergonomics; the shipped/evaluated containers use Node 22.

6. **Provider facts unverified until a live probe runs.** §14.1 flags both the exact model ID
   (`nvidia/nemotron-3-super-120b-a12b`) and the `json_schema` vs `response_format` structured-
   output discrepancy as needing live verification; `WebFetch` was unavailable during planning.
   **Decision:** the provider adapter treats structured-output support as a *probed* capability
   recorded in `docs/capabilities.json`, never assumed from the model family name, per §14.1 and
   §14.5. No live claim is made until `oa provider probe --live` actually runs against a real key.

7. **No Nebius credential exists yet.** Per the owner's explicit choice, every live-provider gate
   in §23/§27 is implemented but will be reported **BLOCKED**, not passed, until a key is
   configured. `PROVIDER_MODE=mock` is the default; the UI shows a MOCK banner. See §19.3/§14.6.

8. **Full §21.11 matrix (12 episodes × 8 outputs × 3 reps × 4 methods = 1152 scored outputs, plus
   all teaching/probe/solver overhead) is credit- and time-dependent.** §21.11 explicitly permits
   "a smaller study... reduce all compared methods consistently." **Decision:** if final credits or
   time force a reduction, reduce repetitions before reducing episodes (preserving the 12-episode
   structural design), apply the same reduction to every method, and report the resulting
   uncertainty explicitly rather than silently shrinking the study. No decision needed yet — this
   is a pre-committed fallback rule, recorded before any run happens so it cannot be chosen after
   seeing results.

9. **`.claude/CLAUDE.md` was a placeholder template** (bracketed fill-in-the-blanks, no real
   content). It will be filled in per §5 with actual commands/invariants once the CLI and compose
   setup exist, preserving its existing section headers so it still reads as the project's own
   CLAUDE.md rather than being replaced by a copy of the spec.

## Open items carried forward

- git init still needs the owner to run it (see #4). Nothing else is blocked by this.
- Node version mismatch (see #5) is a documented dev-ergonomics deviation, not a correctness risk,
  since containers pin Node 22.

## 2026-10-09 (later) — implementation-time findings

10. **Python 3.13.5, not 3.12.** `uv python install 3.12` could not complete in this environment, so the
    venv uses the host 3.13.5 (`requires-python >=3.12,<3.14`). Deviation from spec 3.4 (3.12). All locked
    deps installed on 3.13. Effect on research claim: none expected; revisit if a dep lacks 3.13 support.
11. **Dependency pin `click<8.2`.** typer 0.12.5 crashes `--help` on click 8.5 (`make_metavar() missing ctx`).
    Pinned in pyproject.toml; verified fix by running `oa --help`.
12. **macOS hidden `.pth` flag.** uv's editable-install `.pth` is flagged hidden and Python 3.13 skips hidden
    `.pth` files, giving `ModuleNotFoundError: open_apprentice`. Workaround after every `uv sync`:
    `chflags nohidden .venv/lib/python3.13/site-packages/*.pth`. Document in README setup.
13. **Package downloads need network outside the Bash sandbox.** The sandbox proxy denied `pypi.org` and
    `files.pythonhosted.org`; `uv sync` was re-run with the sandbox disabled for that command only (approved
    dependency set). Same expected for npm and Docker pulls.
14. **Added `pyyaml`** (config validation tests). Not in the user-approved list; trivial, noted here.
15. **Added a bounded `list` expression to the tool-program grammar (deviation from spec 7.2's expression list).**
    Binding programs must call `observe_geometry(node_ids=[...])` with a computed id, which the spec's grammar
    (literals, refs, field access, arithmetic, length/min/max, comparisons, boolean) cannot express. `list` builds
    an array of <=16 evaluated elements. It adds no new capability beyond data construction; found when a probing
    repair program failed with `node_id must be a string`.
16. **Fabric backend scope.** Real Fabric 6.9.1 UMD build in the same locked page; flat rect scenes only, grouping returns
    `UNSUPPORTED_CAPABILITY` (declared common subset gap_row/badge_attach, spec 6.7). Its private drift family is
    `move_origin: center` (move_node x,y become the object's CENTER) - an artificial intervention in the spirit of
    spec 6.6's coordinate-semantics family, not a claim about any real Fabric release. Konva keeps `move_frame: world`.
17. **Verifier refuses non-default object origin** instead of guessing, and adds `verify_expected_geometry` for held-out
    intent checks against the PRIVATE teacher rule's output.
18. **FINDING (dev, non-LLM reference): the 24-action native allowance (spec 8.7/19.2) is too small for a 3-card row repair
    with two retained cases.** In a drift episode the spacing repair stopped `incomplete` after exactly 24 actions (witness +
    2 retained replays + fresh case); the one-card badge repair needed 18. Not changed silently. Options for the pilot,
    to be chosen on development/validation data only: raise the allowance (e.g. 48) for EVERY method and publish it, or
    reduce retained cases to one. Until decided, row-task repairs under the shipped default will often be `incomplete`,
    and that is reported as a failure, not hidden.
19. **Reproducibility fixes found by tests:** (a) sorted iteration in the Z3 encoding (set order changed the query with
    PYTHONHASHSEED); (b) Z3's global context is reset per solve and seeds pinned, because the long-lived worker made the
    same query return different models depending on history. Teaching outcomes depended on this.
20. **Runner/closure facts:** learning costs are logged as a separate `stage=learning` row that counts toward COSTS but
    not success denominators; committed sessions are sealed, scored, then closed; the policy-facing EnvPort exposes only
    `open` and opaque `replay` (no epoch/drift labels).
21. .env/.env.example gained blank optional slots LANGSMITH_API_KEY, TAVILY_API_KEY, TOLOKA_API_KEY (names follow each vendor's usual convention and are UNVERIFIED; no code reads them). A deliberate, documented addition to the spec's verbatim 14.2 list.
22. **Rule text front-end (deviation from "Nemotron proposes rule ASTs", spec 7.4/8.5).** Live trials showed the model making
    structural slips when hand-writing a deeply nested JSON AST (merged statements, garbled arrays, 3-argument `add`). The model
    now writes a few lines of rule text; a closed-grammar parser (`concepts/rule_text.py`, no eval/exec, line-numbered errors)
    compiles it to the SAME restricted AST. The AST stays the only validated, hashed, symbolically compiled and executed artifact;
    raw-AST candidates are still accepted (fixtures). Parser behaviour is tested against the already verified fixture ASTs.
23. **Demonstration-id aliases.** Models refer to objects by the ids they see. The parser resolves names equal to the FIRST
    evidence scene's object ids to `objects[K]` by position, so compiled rules remain positional and generalise like any other.
24. **Live provider facts (probe, 2026-10-09).** Model id confirmed; `max_tokens` accepted; `json_object` and strict `json_schema`
    both work; `seed` accepted; `reasoning_effort` accepted and effective (none=0, low=7, default=23 reasoning tokens on a trivial
    task). The model is a reasoning model: hidden tokens share the completion budget, so token caps must be generous and
    truncation (`finish_reason=length`) is classified as inconclusive, never as "feature unsupported" (my first probe run
    got this wrong for json_schema; fixed and re-run). Nothing here measures rule-synthesis quality.
25. **`reasoning_effort` is a decoding setting that must be ONE value for all methods**, chosen on development data and frozen
    before the locked study. It is read from `NEBIUS_REASONING_EFFORT` and recorded in every pilot result.
26. **Candidate-generation prompt is tuned on DEVELOPMENT episodes only** (same prompt for every method that uses the shared
    teaching session). Any change is logged here with the dev result that motivated it; the final split is never run before the freeze.
    Iteration 1 (syntax: show the mapping scene.objects -> objects[K], one unrelated example, `clone` needs `proto`): 0 accepted
    candidates -> candidates reach the teacher. Iteration 2 (rule text + aliases + rejection REASONS fed back): see status.md.
27. **Shared candidate-generation configuration chosen on DEVELOPMENT data and frozen for the pilot** (24 trials = 12 dev episodes x
    {badge, spacing}, one live draw each, reasoning_effort=low; this is tuning evidence, not a study; final split never touched):
    | version | recovered | ready on WRONG rule | honest UNRESOLVED | tokens |
    | v2 text rules | 2 | 11 | 11 | 69k |
    | v3 + diversity wording | 2 | 8 | 14 | 82k |
    | v4 + one counted numeric correction turn when nothing fits | 6 | 9 | 9 | 164k |
    | v5 + one alternatives round when exactly one rule fits and nothing was asked | 6 | 2 | 16 | 190k |
    v5 is the configuration (`prompts/hypotheses.md`, copy in `prompts/hypotheses.FROZEN-dev-choice.md`). Chosen because it removes most
    confident-wrong outcomes (the failure the project exists to expose) at ~2.3x the tokens of v2; it does NOT improve recovery over v4.
    Known cost: the alternatives round uses the 2nd generation round, so a later Neither cannot get a correction round (ends UNRESOLVED).
    Badge-family rules were never recovered (0/12 in v5, 1/12 in v4) - an open capability gap, not a settled limit.
    The diversity wording names size-dependence and upper/lower limits generically; that is a hint toward the hypothesis space and is
    disclosed here and must be disclosed in the README. All model-based methods use it (shared TeachingSession).
28. **Cost/time of that choice** (per trial, low effort): median ~8k tokens, ~15 s; a 12-episode study teaches 24 concepts per method
    (~200k tokens) before any task executes. The spec's 80,000-token episode cap leaves ~55-65k for execution after teaching.
29. **NEGATIVE RESULT (kept on record): derived geometric relations in the evidence did not help.** v6 added computed gaps/ratios/shifts
    between rectangles to every evidence item (symmetric in all sides; public geometry only). Same 24 dev trials: recovered 6 -> 6,
    badge 0/12 -> 0/12, ready-but-wrong 2 -> 4, tokens +22% (190k -> 231k). The diagnosis that motivated it (the model could not do the
    subtraction) was therefore wrong or insufficient. Disabled (`INCLUDE_RELATIONS = False`); prompt text kept as
    `prompts/hypotheses.v6-with-relations.md`; the frozen choice stays v5.
30. **Live spend so far** is about 1.05M model tokens (probes, 6 development batches of 12-24 teaching trials, one 5-method smoke
    episode). Dollars are UNKNOWN: INPUT/OUTPUT_USD_PER_MILLION are unset, so the $5 `LIVE_RUN_MAX_USD` is not enforced against real
    prices (only token/call caps are). Live work is paused until real rates or the console balance are known.
31. **First lever that moved the badge concept: reasoning effort.** Same frozen v5 configuration, 12 badge development trials, completion cap
    16,000 (so truncation cannot confound): `low` 0/12 recovered (6k-14k tokens, ~15 s); `medium` **3/12** recovered (all three on
    constant-margin rules; ep 0, 3, 9), 2 ready-but-wrong, 6 honestly unresolved, 1 truncated; 191k tokens (~16k/trial), 13-110 s per trial.
    Single draws on development episodes; this shows effort matters for the badge family, not what the true rate is. The spacing
    counterpart at `medium` is pending; ONE value must then be chosen for every method and frozen (decisions #25).
32. **MODEL CHOICE (development evidence): `nvidia/Nemotron-3-Ultra-550b-a55b`, `reasoning_effort=low`, completion cap 32,000.**
    Same frozen v5 loop, 12 development episodes per concept, one live draw each (tuning evidence, not a study):
    | model / effort | cap | badge recovered | spacing recovered | ready-but-wrong | tokens (both concepts) |
    | Super / low | 6k | 0/12 | 6/12 | 4 | ~420k (v6 incl. relations) |
    | Super / medium | 16k | 3/12 | 4/12 (+2 read timeouts) | 2 | 349k |
    | Ultra / none | 12k | 1/12 | not run | 0 | 77k (badge only) |
    | Ultra / low | 12k | 4/12 (7 TRUNCATED, all 4 completed trials correct) | not run | 0 | 181k (badge only) |
    | **Ultra / low** | **32k** | **9/12** | **6/12** | 2 + 3 = 5 | 246k + 277k = 523k |
    Ultra/low = 15/24 recovered vs 6/24 for Super/low under identical prompts and loop. The earlier prompt-only levers (diversity wording,
    derived relations, the correction turn) moved nothing near this. Costs: ~20k tokens and 9-139 s per teaching trial; the heaviest
    trials used 44-50k tokens. Choosing the larger model for ALL methods is allowed by the spec (one fixed model for every role) but
    the README must say the headline numbers depend on it, and that a smaller model (Super) does far worse on this task.
    Provider read timeout raised 120 s -> 300 s (two medium-effort Super calls timed out; timeouts leave an unresolved reservation).
33. **OPEN PROTOCOL DECISION (needs the owner): the spec's 80,000-token episode cap no longer fits.** Teaching two concepts with Ultra
    averages ~40k tokens and can reach ~90k, before any task runs. Per spec 21.10 the cap may be expanded in development if published and
    applied to EVERY method. Proposal: episode_total_tokens 300,000; episode_provider_calls 64 -> 120; keep actions 800. With the study
    reduction rule (reduce repetitions before episodes) a 12-episode x 4-model-method x 1-rep study is ~48 runs x ~150-250k tokens ~ 7-12M
    tokens; dollar cost is UNKNOWN until INPUT/OUTPUT_USD_PER_MILLION are known.
34. **Tool-program nesting depth raised 4 -> 8 (deviation from spec 7.2).** Found by the first LIVE binding-generation diagnostic
    (`scripts/bind_trial.py`): both model candidates were rejected as "nesting too deep" because a correct binding naturally nests
    `for_each > if/else-if chain over target kinds > if (mismatch)`. This blocked EVERY full_v1_2 task in the first live pilot
    (`binding_unavailable` x8). The 64-statement, 500-expression and 100-action limits still bound execution; the depth limit guarded
    nothing the others do not. Prompts that quote the limit were updated. Applies to every method that runs tool programs.
35. **Native-action allowance for experiments/witness reproduction raised 24 -> 48 for EVERY method (resolves #18).** Evidence: the non-LLM
    reference's 3-card row repair stopped `incomplete` at exactly 24 actions, and a live model binding needs ~10 actions per candidate
    (calibration + confirmation), so even two honest candidates exceed 24. 48 still sits well inside the 800-action episode cap.
    Chosen on development data only; applies identically to every method and is frozen with the rest of the protocol.
36. **Live binding generation fixes (found by running it for the first time, `scripts/bind_trial.py`):** (a) nesting depth (#34);
    (b) the binding prompt gave tool names but not their return shapes (model wrote `locals.obs.0.left`; the shape is `obs.bounds.0.left`);
    (c) a model-driven transfer now gets ONE counted correction batch carrying the concrete failures (static rejection, simulator error,
    runtime error, or observed-vs-target geometry). After the fixes: spacing/Fabric and badge/Konva validated in a single call; badge/Fabric
    needed the correction batch and was then cut off by the old 24-action limit. Single trials, not rates.
37. **Program-writing rules added to EVERY prompt that asks a model for a tool program** (binding, synth_program, fresh_gap_row), identical text:
    arithmetic ops are binary, every tool call costs a native action (observe many nodes with one call), and a correction must be derived
    from observed-vs-target geometry rather than constants. Found by live diagnostics: a binding crashed with `add takes 2 args` inside a
    branch that only runs on mismatch, and a repair candidate used a constant-offset correction that failed on a fresh scene. Consequence to
    report honestly: with these rules a live binding can be robust to the private tool change and need NO repair (spacing/Fabric, one trial).
    That outcome is scored as correct, not as a repair; repair-specific claims therefore need episodes where the model binding did fail.
38. **Program-language usability fixes (found by `scripts/bind_trial.py` on badge/Fabric, episodes 3-5, before: 0/3 validated):**
    (a) interpreter errors now name the offending statement/expression and the valid options instead of `bad statement` / `bad field access` /
    `unknown expression op: None`, so the one counted correction batch can act on them; (b) every program prompt carries one worked example,
    and a test (`test_prompt_example_program.py`) proves the example validates; (c) a binding call that is truncated (hidden reasoning
    consumed the whole 32k allowance) is retried ONCE, both calls charged; a second truncation is reported as `provider_error`.
    After: badge/Fabric validated on the first call in episodes 3, 4 and 5 (3/3, n=3, single trials, dev split). Applies to all methods.
39. **Alternatives-round wording changed ("measuring from a different edge" -> "measuring differently") and engine-backed tests repaired.**
    The opt-in engine tests (OA_ENGINE_TESTS=1) were not run after decisions #32-#38 and had gone stale: the transfer correction batch and the
    alternatives round each consume one more scripted mock reply (fixtures updated). Re-running them also made the research-integrity test
    `test_no_prompt_contains_evaluator_only_information` fail: my own instruction text contained the word "edge", which is the evaluator's
    name for the spacing template, and it nudged the model toward the benchmark's actual ambiguity. Reworded neutrally; the test is unchanged.
    The v5 candidate-generation prompt was "frozen" in #28; this wording change is applied to every model-based method and any live number
    produced before this change used the old wording (all runs up to and including the pilot in flight on 2026-10-11).
40. **Audit round (experimental option, default OFF): `TeachingSession(audit=True)`, `oa learn --audit`.** Motivation: the five-method pilot showed wrong
    commits even after 2-6 teacher answers, i.e. a rule that fits all evidence but is not the intended one. The audit spends ONE extra generation
    round (a third; spec 8.6 allows two) asking for other rules that fit ALL evidence including answers; if one concretely disagrees the session asks
    (if a query is left) or ends UNRESOLVED (abstains). It is a deviation from the two-round limit, applied only when enabled. Controlled experiment:
    results/exp_audit_control vs results/exp_audit_on (dev split, same episodes, 2 reps).
41. **Interactive demo choices that differ from the evaluation:** `prefer_readable_queries` breaks score ties toward sampled scenes (the solver's simplest
    witness can be degenerate: tiny objects stacked at the origin), and the demo domain requires a 6 px visible difference instead of 1 px so a person can
    see the options differ. Both are demo-only; the evaluation path is unchanged and tested (`test_prefer_readable_query.py`).
42. **Scripted native procedures are labelled `origin=fixture` everywhere** (API, UI data, SVG metadata, evidence package). A test caught that the library
    default `origin="model"` would have recorded scripted programs as model-generated.
43. **Code quality pass (2026-10-11):** black on all of src/tests/scripts; ruff clean (per-file ignores for terse AST-builder lambdas and `l` in tests are
    explicit in pyproject.toml); added `Provider.aclose`. KNOWN DEBT: `mypy src` still reports 84 errors, almost all imprecise dict typing; not fixed.
44. **RESULT (negative): the audit round (#40) does not reduce wrong commits; it reduces correct ones.** Controlled experiment, dev split, Nemotron-3-Ultra low effort,
    12 episodes x 2 concepts x 2 reps = 48 trials per arm (results/exp_audit_control, results/exp_audit_on; `scripts/analyze_audit_experiment.py`):
    control committed 34 (19 correct, 15 wrong = 44%), abstained 9, 5 trials lost to truncation; audit committed 10 (6 correct, 4 wrong = 40%), abstained 30 (25 of them
    `ambiguity_remains`), 8 trials lost to truncation/timeout. The audit finds alternative rules that fit all evidence and genuinely disagree elsewhere, but with at most
    two questions they cannot be resolved, so the system abstains on most correct cases too. Wrong share of committed outputs is unchanged within noise (n small).
    Tokens: 1.08M vs 1.82M. Conclusion: more model-side hypothesis hunting is not the lever. Audit stays OFF by default and is kept as a documented negative result.
    Also: ~10-15% of model trials in BOTH arms end in `TruncatedOutput` even with a 32k completion floor (reasoning runaway): a reliability issue to report.
    Caveat to state with the non-model reference's 100%: its grammar was designed with the benchmark's rule families in mind (generic constants, but family-shaped), so
    it shows the tasks are solvable inside a declared grammar, not that the reference "understands" layout.
45. **Hybrid candidate source (`concepts/hybrid.py`, `oa learn --hybrid`): model proposals UNIONED with the bounded symbolic search.** Motivation: decisions #44 (omission, not
    under-asking, is the failure). The union keeps the teaching loop and the teacher as the only oracle; candidates are tagged [model]/[search]; a failing model call degrades
    to search-only. Known limit, found while testing: the search keeps only the simplest few behaviours that fit the demonstration, so an in-grammar rule beyond that cut-off
    (e.g. a clamped inset) can lose to a simpler rule that coincides on every asked scene. The benchmark's own templates sit inside the simple range, so on them hybrid
    should approach the non-model reference; that shows search coverage, NOT model value. Model value would need rules outside the grammar (not yet built).
    Cost lesson: output-heavy runs cost ~$3-4/M tokens (balance $19.95 -> $6.96 after the audit experiment + live sessions); `oa learn` now has `--max-total-tokens`.
46. **RESULT (positive, with a stated limit): the hybrid source cuts wrong commits from 44% to 5%.** Hybrid (model proposals UNIONED with bounded symbolic search, #45), dev split, Nemotron-3-Ultra
    low effort, 12 episodes x 2 concepts x 1 rep = 24 trials (results/exp_hybrid): committed 20 (19 correct, 1 wrong = 5%), abstained 3 (all badge `ambiguity_remains`), 1 trial lost to an
    error, 428k tokens. Control (model alone, same dev episodes, 2 reps, #44): committed 34, 15 wrong = 44%. Different n (24 vs 48) and one repetition: treat as a strong signal, not a precise rate.
    WHAT THIS DOES NOT SHOW: that the model adds value. The non-model reference also solves these tasks, and the origin tag overstates the model's role (behaviourally identical candidates keep the
    FIRST origin, which is the model's: 14 of the 19 correct rules are tagged [model] although the search proposed the same behaviour). The supported claim: closing the omission gap with symbolic
    coverage, while the teacher remains the only oracle, removes most confident-wrong commits. Model value needs rules outside the grammar (not yet built).
47. **RESULT: the model adds real value where the symbolic search cannot reach (out-of-grammar battery, development only).** Six badge rules the search provably cannot express (tests/unit/test_oog_battery.py):
    height-based inset, shorter-side inset, centred on the top edge, bottom centre, resized badge, (w+h)/20 inset; 2 reps each; Nemotron-3-Ultra low effort; results/exp_oog_{search,model,hybrid}.
    SEARCH ONLY (no model): 0 correct, 2 wrong (rule 5), 10 abstained. MODEL ALONE: 12 trials, 7 committed = 5 correct + 2 wrong (both rule 1), 2 abstained, 3 lost to errors.
    HYBRID: 11 trials run (the 280k ceiling skipped the last), 5 committed = 5 correct + 0 wrong, 4 abstained, 2 lost to errors. Rules recovered by the model arms: height-based inset, centred
    on the top edge, bottom centre; not recovered: shorter-side inset, resized badge, (w+h)/20. Hybrid vs model-alone (0 of 5 wrong vs 2 of 7) is a direction, not a significant difference.
    Together with #46: search supplies coverage and safety inside its grammar, the model supplies reach outside it, and the teacher stays the only oracle. Tokens 216k + 315k (~$1.9).
48. **Real-SVG lane built as an EXPERIMENTAL spike (spec 6.8), deliberately narrow and model-free.** `src/open_apprentice/svg/` (safety validator, byte-exact document editor, typed patch, rule-to-patch),
    `api/svg.py`, engine route `/internal/svg/measure`, "Real SVG" tab. Choices: (a) the learned BADGE rule is applied by MOVING an existing badge element (set x/y), because the spike forbids insertion and deletion; (b) edits are made on the ORIGINAL BYTES inside
    start tags only, with a byte-level proof that nothing else changed; (c) active content, external references, styles, images, entities, SMIL, foreign namespaces and unsupported elements are REJECTED, never sanitised; (d) only translate() transforms are supported, anything else makes an element
    non-editable and is shown in the coverage; (e) verification is the browser's own getBBox/getScreenCTM in a network-blocked context, independent of our arithmetic; (f) assets are three original owner-authored files (NOTICE.md); nothing from Vector-Bench's excluded illustrations.
    NOT DONE (so the lane stays experimental per the exit criteria): the matched baseline pilot of 21.12, and Nemotron-written patches. Exit criteria met: three assets import/export without unrelated changes (tests), one learned edit executed on assets not used in teaching, a deliberately harmful patch rejected (7 attempts).
49. **Replay mode: one real Nemotron session recorded to a tape and served at zero cost, always labelled REPLAY.** `providers/replay.py`: `RecordingProvider` (env `DEMO_RECORD_TAPE`, one-off) and `ReplayProvider`, which answers a call only when role + messages are byte-identical
    to a recorded one and otherwise raises `ReplayMismatch` (HTTP 409); it never improvises. API mode `replay` (default demonstration only, 422 otherwise) runs the normal model-mode pipeline with the tape as provider, skips the live budget, and the meter and labels say REPLAY.
    Recorded 2026-10-12 with Nemotron-3-Ultra low effort: 3 model calls, 32,279 tokens, ~$0.089 by the configured rates (unverified rates); the session reached INTENT_READY and the model procedures passed the real-backend checks on Konva and Fabric.
    Replaying it (model disabled) reproduced the same questions, rule, and verifier results, in about 0 s. LIMITS: the tape covers one demonstration (default badge position); requests are matched byte-for-byte, so another answer (checked in a browser: B then A sealed a different rule) still matches when the binding prompt is identical, because that prompt carries the rule's target positions, not its text, and the procedure is re-checked live against the rule taught; the recorded session contains no repair because the model's procedure survived the tool change, so replay does not demonstrate a model repair.
    Public ceilings tightened at the same time: 120k tokens / 24 calls per model session (was 250k/40), 3 live model sessions per client per hour (was 8), default global cap $1.5 (was $2).
50. **Hybrid candidate cap: interleave model and search after de-duplication (2026-10-12).** The union kept every model proposal first and then cut to `MAX_UNION = 6`, so a long model list could push search candidates (including a correct rule the model omitted) past the cap, undoing the coverage the search exists to provide. Now each source is de-duplicated (behaviourally identical rules count once; the first origin, the model's, wins) and the two are interleaved before the cap; `model_error` reports only the current round. Regression test: with two model proposals and a cap of two, a search candidate is kept.
    **Effect on stored results:** in the stored hybrid runs (`results/exp_hybrid`, `results/exp_oog_hybrid`), 24 of 46 recorded rounds reached the cap; in none of them did the cap remove every search candidate. Which candidates were dropped was not recorded, so whether a correct rule was ever cut cannot be checked from the stored rows. The published hybrid numbers (#46, #47) were measured with the old order and are labelled as such; re-running them costs model credit and has not been done.
51. **Solver limits are deterministic work units, not wall-clock time (2026-10-12).** Measured in Docker: at 0.1 vCPU the old per-call 0.5 s / per-session 6 s wall-clock budget made z3 report `incomplete` and sessions end UNRESOLVED, so outcomes depended on the host's CPU. Calibration on the 24 development tasks (reference learner, no model): 79 solver calls, 77 sat + 2 unsat, z3 `rlimit count` per call min 1,259 / median 1,409 / max 1,984, wall time median 11 ms / max 256 ms, 24 of 24 tasks reached INTENT_READY. Now each call is limited by `rlimit = 1,000,000` (about 500 times the largest measured use) plus the existing call cap; wall-clock values (30 s per call, 300 s per session) are crash guards only. z3 is pinned to `z3-solver==4.13.4.0` because rlimit counts are only reproducible on one build. The worker imports z3 at start-up and the API starts it before the first visitor. Every solve now reports `rlimit_used`.
    **Verified in Docker after the change (2026-10-12, 512 MiB, flows from `scripts/live_flow_check.py`):** at 0.1 vCPU the session now reaches INTENT_READY with the same rule ("top-right inset 12"; before the change it ended UNRESOLVED with `solver status=incomplete`), replay flow 3/3 verifier passes in 47 s and reference flow in 50 s (the one verifier FAIL in the reference flow is the deliberate silent tool change before repair); at 0.25 vCPU 9 s and 13 s; at 1 vCPU 2 s and 2 s; no OOM kills. CPU now changes speed, not answers.
52. **The public demo runs live Nemotron on Nebius Token Factory by default; the recording is only a labelled fallback (2026-10-13).** The hackathon requires projects to run on Nebius Token Factory (or AI Cloud) with an NVIDIA open model, and a demo that served only the recording and the free reference learner did not show that. `DEMO_MODEL_ENABLED=1` is now the public configuration; the learner defaults to live Nemotron when `/health/ready` reports `model.can_start`; "Watch the story with live Nemotron" runs the full flow; at the dollar cap the UI offers the recording, labelled. Verified live in a browser through Token Factory: 89 s, 5 calls, 36,384 tokens, $0.085 at the configured rates (unverified), no errors. In that run the tool change broke the model's Fabric procedure (a natural failure), Nemotron's repair attempt failed the checks (`witness_in_current_env`) and a labelled scripted fixture repair was promoted: that is NOT a model repair and the UI says so.
    Found on the way: after the A8 spend change, every model action required a whole new session's reserve, so a $0.50 cap refused a session that had spent $0.04; now only session START needs the full worst-case reserve and a running session needs one call's worth (`ONE_CALL_RESERVE_USD`), so the cap is enforced to within about one call.
53. **Calibrated-asking environment and scripted-policy results (2026-10-13; development split, no model, free).** `evaluation/asking_env.py` (`AskingEnv`) shows an agent ONE demonstration of a hidden rule (badge or spacing), lets it ask the teacher to show the true outcome on up to 3 new inputs, then it commits a rule in the closed text grammar or abstains. Verification is exact rational evaluation of the same rule language, against held-out scenes; no LLM judge. Reward components stay separate: `correct` (the named `reward`), `held_out`, `asking`, `not_confidently_wrong`, `economy`; they are never blended. Ambiguity is computed by the ENVIRONMENT (the reference teaching loop needed >= 1 question), so it is relative to the declared grammar and the enumerator's cap of 4; the agent's proposals never decide it. 15 of 24 development demonstrations are ambiguous.
    Scripted policies (`evaluation/asking_baselines.py`, `scripts/run_asking_baselines.py`, rows in `results/asking_baselines/`), n = 24 per policy: never_ask correct 0.50 overall (0.20 on the 15 ambiguous, 1.00 on the 9 unambiguous; confidently wrong on 12 of 15 ambiguous); always_ask correct 0.92 but asking 0.00 and economy 0.00 on the 9 unambiguous; calibrated correct 0.92 with asking 1.00 and economy 0.75 (0.60 on ambiguous, 1.00 on unambiguous); always_abstain correct 0.00. Neither asking policy is correct on 2 of the 15 ambiguous tasks; the cause was not investigated (possibly the enumerator's cap hides the hidden rule). These show that the components separate behaviours; they say nothing about language models.
    Related work checked: NeMo Gym 0.6.0 ships an `abstention` resources server (reward for answering correctly, a configurable reward for saying IDK, LLM-judged factual QA) and `arc_agi`; this environment differs in rewarding a targeted question to a teacher only when the demonstration is genuinely ambiguous, in computing ambiguity from the environment, and in verifying with exact evaluation instead of an LLM judge. Only the packages shipped in 0.6.0 were checked; no claim is made about other environments.

    **Gym stack findings (2026-10-13):** nemo-gym 0.6.0 requires Python >= 3.13.14, and its CLI (`gym list`, `gym env init`, `gym env start`) crashes on CPython 3.14.8 with an argparse "badly formed help string" error from a `LazyCompletionHelp` object in its Hydra parser; on a self-contained CPython 3.13.16 the CLI works and discovers `oa_calibrated_asking` next to the shipped environments. Gym starts one virtualenv per server (3 here) and installs ray and openai into each; three parallel installs stalled for several minutes, so the per-server environments are pre-built serially with `gym env prefetch`. Run artifacts (`gym/outputs`, results, per-server `.venv`) are git-ignored because Hydra saves resolved configs there.
54. **The Gym pipeline is verified end to end at zero cost with a scripted stub (2026-10-13); no model has been run through it yet.** `gym eval run` with a stub OpenAI-compatible endpoint (asks once, commits a fixed rule, says done): 4 of 4 rollouts completed, 0 failures, each model request carried the 3 tools, verification returned the separate components, and Gym's aggregate profiled each one (`mean/correct`, `mean/asking`, ...). The stub's single question scored `asking` 1.0 on the ambiguous tasks and 0.0 on the unambiguous ones, matching `ambiguity_label`. Findings: use `vllm_model` (chat-completions upstream) instead of `openai_model` (Responses API upstream) for Nebius Token Factory; rollouts return out of order so analysis must key on `_ng_task_index` (my first read zipped by position and looked inconsistent until corrected); the server's `requirements.txt` must list `nemo-gym`; per-server environments are pre-built serially with `gym env prefetch`. Token Factory lists four NVIDIA models (Nemotron-3-Ultra-550B, Nemotron-3-Super-120B, Nemotron-3-Nano-30B, Nemotron-3.5-Lightning), so a size comparison is possible; costs of the smaller ones are not known.
55. **RESULT (partial, development split, one model): Nemotron-3-Ultra through the calibrated-asking environment, 13 of 24 tasks (2026-10-13).** Run via NeMo Gym (`gym eval run`, `vllm_model` adapter over Nebius Token Factory, temperature 0, `max_output_tokens` 8000, default reasoning effort, concurrency 2). A spend watcher stopped it at the owner's $1.00 cap: 13 of 24 tasks completed (+1 killed in flight), estimated $1.025 at the configured rates ($1/M in, $3/M out, owner-entered and unverified; $3.03 at a conservative $4/M), 756k tokens (622k in, 134k out). The overshoot past $1.00 is one task finishing between the watcher's 10 s checks. The 13 are not a random sample of the 24 (completion order), so every number below is a small-n pilot, not a rate.
    Per axis on the 13 (8 ambiguous, 5 unambiguous): `correct` 0.385 (8 committed, 5 of them correct); `held_out` 0.465; `asking` 0.769, i.e. it asked on **all 8 ambiguous** tasks (so `not_confidently_wrong` 1.0) and on 3 of 5 unambiguous ones (over-asking); `economy` 0.28. On the same 13 tasks the scripted policies score correct: never_ask 0.615, always_ask 0.923, calibrated 0.923; those use a symbolic enumerator over the declared grammar and are NOT language-model comparisons.
    Failure modes (the main finding): 5 of 13 tasks ended with neither commit nor abstain, so they scored zero on `correct` for protocol reasons: one badge task repeated a refused `ask` 26 times after the 3-question limit (171k tokens), one spacing task made no tool call, the model called two tools that do not exist (`query`, `submit`), and several tasks burned tokens on invalid commits. Per-task cost ranged from 9k to 171k tokens, so a one-task smoke test (10.8k tokens, $0.015) badly underestimated the average ($0.08).
    **Environment fix made because of this run:** the refusal after the question limit said only "question limit reached (3)"; it now says to stop asking and call commit or abstain. The 13 completed rows were collected with the OLD message, so a rerun with the new message is not comparable with them. Rows: `results/gym_ultra/rows.jsonl`, summary `results/gym_ultra/summary.json` (raw rollouts stay local: they contain full prompts). Not run: Nemotron Super/Nano, the remaining 11 tasks, repeats; nothing here supports a claim about language models in general.


## Policy v2 for the apprentice (2026-10-18; Plan 7) — deviation from spec §4 "Allowances per cycle"

The funded final run (`docs/evaluation/final_results.md`) showed A's dominant failure: every proposal rejected after at most
three proposal rounds, using 2.5 of its 8 allowed attempts. Spec §4 allows "one initial proposal round, at most one
contrastive round, at most one contradiction revision". **Policy v2 (systems `A2` and `D2`) raises the revision allowance to
three and treats a reply cut at the completion cap as an empty round instead of a terminal error; nothing else changes**
(same prompts, same budgets: ≤ 8 attempts, retries counted). It was designed after the final rows were seen, so its
final-split numbers are post-hoc; the unchanged A, B and D rows stay published. A pre-registered go/no-go rule on development
episodes (`docs/superpowers/plans/2026-10-18-p7-policy-v2.md`) decides whether it is re-run on the final split.

56. **Campaign lane limits and evidence axes (2026-10-22, Plan 9A).** Story artboard 1080×1920, safe insets 220/72/220/72,
    minimums: headline/price/CTA label 40 px, legal 24 px, CTA height 96 px, hero width 432 px; gold geometry tolerance 2 px.
    Frozen before any evaluation (spec §10). Text frames have fixed heights so gold outputs are authorable by hand. The verifier
    measures text from the font tables with `fonttools` (new dependency) and ignores kerning; a line-count disagreement with the
    engine fails the result. The symbolic axis is not used for this lane (spec §7.9). Public fixtures are development only.

57. **Campaign lane: no offer group; origin vocabulary; preference scope (2026-10-22, Plan 9B).** Spec §2 says headline, price
    and CTA are "regrouped into one offer group"; the owner-approved 9A gold outputs keep them as direct children of the card,
    so the plan follows the gold (owner confirmed by approving Plan 9B). Every result carries origins: learned layout `search`
    or `model`, apply procedure `reference`, overflow outcomes `builtin`; nothing built-in is labelled learned or model.
    The overflow choice is a user preference (not a learned branch), versioned per `promo_card/9:16/overflow/<locale>`.

58. **Campaign API (2026-10-22, Plan 9C).** Preferences are namespaced per workspace (a public demo must not let visitors
    overwrite each other's choices). No engine session outlives a request: results and previews are snapshotted (PNG + native
    state) and closed, so a pending question costs no engine capacity. The commit gate is the independent verifier against the
    authored development gold; with no gold a result is `blocked`, so the lane only runs development fixtures until a
    gold-free product gate is designed.

59. **Campaign lane on Fabric (2026-10-22, Plan 9D).** Fabric scenes keep Fabric's own semantics: group children are stored
    in the group's centre frame and images at natural size with a scale; `nativeState` reports them raw with a `frame` tag
    and the independent verifier composes them. Cards use a layout that runs only at creation (a child's relayout must not
    move the card); the CTA group fits its content. Campaign mode switches on only for scenes with an artboard, so the badge
    lane's Fabric subset and drift are unchanged. Parity is measured on development fixtures only; the held-out set is
    owner-authored and sealed by hash before any run. Known divergence: Fabric text runs about 3-8% taller (its 1.13
    font-size multiplier), so a banner near a frame limit can be `ready` on Konva and `question` on Fabric. Adding the
    campaign tools changed the Fabric public schema hash for every Fabric session (recorded on bindings, never compared).

60. **Nemotron in the Campaign lane (2026-10-22, Plan 9E).** Nemotron-3-Super does three jobs, each behind a deterministic
    check with a labelled fallback: role proposals (owner confirms), overflow wording (numbers and elements must match the
    measured facts), and native procedures (accepted only through the independent verifier on a seen and two fresh
    banners). The procedure prompt deliberately omits the reference program so a copy cannot pass for Nemotron's work.
    Workspaces are metered like Try-it-live sessions under the server-wide demo cap. Measured once on development
    fixtures for $0.04 (see `docs/evaluation/campaign_nemotron.md`).

61. **Text cross-check compares fit verdicts, not line counts (2026-10-22).** GitHub CI (Linux Chromium) wrapped
    "Hear only what matters." in `short_a` onto one line where macOS Chromium and the verifier's font-table layout give
    two; the same platform drift showed earlier as 6 vs 7 legal lines on Cloud Run vs Mac. Near a wrap boundary exact
    line counts are not portable, and nothing downstream depends on them: the verifier decides on fit. The cross-check
    (`tests/integration/test_campaign_text_crosscheck.py`) now requires the engine and the verifier to agree on whether
    each text fits its frame and on `word_too_wide`. Checked that it still has teeth: scaling the verifier's font size
    by 1.4 fails it on both backends. Cost if wrong: a line-count bug that never changes a fit verdict goes unnoticed.
