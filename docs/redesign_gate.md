# Redesign gate: result (provisional)

Gate (handoff section 4): at least 12 of 15 fresh applications correct with zero accepted preservation violations;
genuine learned conditional and scope behaviour; an honest same-model baseline; a real-file path; two external reactions.

## Verdict
**Capability criteria: met on the frozen gate set, one run. Gate as a whole: NOT yet met** (no real-file path, no external
reactions, no repeats, no held-out split run). Treat the numbers below as an early positive signal, not as the result.

## What was run
`gate-3` (live, Nemotron-3-Ultra via Nebius Token Factory, reasoning effort low): the frozen gate set from
`build_gate_set()` (manifest hash `0c8ff0b8971c`), 15 episodes = 5 fresh layouts x 3 intentions, each with 3 fresh scoring
documents. Two systems, same model, same documents: the **apprentice** (propose, filter on all evidence, question, validate,
commit or abstain) and a **same-model agent** (free-form ask/commit/abstain loop, up to 3 commit attempts with exact fit
feedback). Scoring is by the independent checker on fresh documents, separate axes. Cost of `gate-3`: $2.79.

| Intention | Apprentice | Same-model agent |
|---|---|---|
| relative (right of node) | 5/5 correct | 5/5 correct |
| conditional (right, else below if blocked) | 5/5 correct | 2 correct, 1 wrong commit, 2 abstained |
| scope (notes only, warnings untouched) | 5/5 correct | 5/5 correct |
| total | **15/15** (45/45 fresh documents; intent, preservation, layout all pass) | 12/15, 1 wrong commit |

The apprentice has zero preservation or layout violations on all 45 fresh documents. The agent's wrong commit is a
violation of the zero-wrong-commit bar even though it reached 12 of 15.

## What this does and does not show
- The apprentice learned a conditional program (a nested scan with a blocked-spot fallback) and a role-scoped program from
  1-2 demonstrations, and applied them correctly to fresh layouts. The agent baseline is weaker only on conditional
  (2/5 vs 5/5). Relative and scope were not discriminating.
- n is small (5 per cell, one run). A 5/5 vs 2/5 difference is suggestive, not significant. Run-to-run variance on this
  model is real (the same noisy episode flipped between wrong commit and abstain on re-run).
- The gate set is unambiguous by construction (the demonstrations pin one behaviour inside the 24-behaviour catalogue) and
  each demonstration was selected to *show* its intention. Two conditional episodes still asked one question. Ambiguity
  and noise are measured separately on the development split, not here.
- Behaviours outside the catalogue were not tested. Fresh documents come from the same generator family.

## Repeat on the same gate set, final protocol, and a correction to the agent figures
`gate-6` stopped early after consecutive provider errors (relative finished), so `gate-7` re-ran conditional and scope with the
identical code and protocol. Apprentice results, assembled: relative 5/5, conditional 5/5 (`gate-7`; `gate-6` had 4/5 plus one
transport error), scope 5/5 = **15/15, no wrong commits** (second independent 15/15 after `gate-3`).

**Retraction.** The agent conditional rows in `gate-6` and `gate-7` (and the "10/15" and "0/5" figures an earlier version of this
file reported) are INVALID: when the agent was given the compact evidence I removed an import it still used, so every agent
"ask" raised a `NameError` and was recorded as an error or abstain. Fixed (commit `42918df`, test added). `gate-8` reran the agent
on conditional after that fix and still got 0/5 (4 abstained, 1 error) because its prompt lacked the blocked-spot example and the
guidance on open dimensions that the apprentice prompt has; that was a handicap on the baseline, not a finding.
`gate-9` reran the agent on the 5 conditional episodes with the SAME language help as the apprentice (commit `fcffc31`): **1 correct,
4 abstained, 0 wrong** (the abstains are rules written in pseudo-English that the parser rejects, for example `for each label`,
quotes or colons; three commit attempts with exact feedback were allowed). Valid agent figures:
relative 5/5 and scope 5/5 (`gate-6`, `gate-7`, `gate-3`), conditional 2/5 (`gate-3`, system-turn protocol, old prompt) and
1/5 (`gate-9`, final protocol and equal prompt). So the conditional weakness of the same-model agent shows up in two valid runs,
at n=5 each, with no wrong commits. It is a direction, not a significant difference.

Between them the runs show large endpoint variance: `gate-2` and `gate-4` (before the compact-evidence fix below) lost many
episodes to echoed or malformed replies, and `gate-4` was stopped at 17 of 30 runs, unfinished and excluded. A fix was found after
seeing failures on gate episodes (post hoc): the model was echoing the full after-state, so evidence is now the scene once plus
the labels that moved, for BOTH systems.

## Things that changed after the development runs (disclosed)
1. Contrastive round, contradiction feedback, lenient parsing, agent format-error tolerance (after `dev-1`).
2. Parser accepts `else if` and double-escaped newlines; nesting limit 6 to 8; one retry on transient provider errors;
   a prompt example of a blocked-spot scan on an unrelated task; constants-in-comparisons guard (after `dev-2`).
3. Held-back validation: survivors must reproduce the teacher's answer on every batch diagram not already asked, else the
   system abstains (after `dev-3` / `dev-4`). It reads teacher answers on batch diagrams, never the fresh scoring documents.
5. Compact evidence (`describe_compact`): scene once plus moved labels instead of the full after-state, both systems, after echoing
   failures in `gate-2`/`gate-4` (post hoc, found on gate episodes).
4. Live runs send instructions in the user turn: on 2026-10-14 the endpoint intermittently ignored the system turn and
   answered the evidence JSON as if it were the task (`gate-2` and a 3-episode probe, invalidated and excluded). Applies to
   both systems. The `dev-*` runs used the system turn.
All tuning used the development split (seed base 10000). The gate set (seed base 90000) was run before any tuning on it,
but `gate-1`, `gate-2` and a probe ran partially and were discarded for the provider fault above, so the gate set was
seen in aggregate by the developer during diagnosis (no prompt or code change was fitted to its content).

## Development evidence (not held-out; tuned on)
Apprentice, 8 ambiguous episodes: `dev-2` 4 correct / 4 wrong; `dev-4` 6 correct / 2 abstained / 0 wrong; `dev-5` (full
validation) 4 correct / 4 abstained / 0 wrong. Unsupported: no wrong commits after validation. **Noisy: unsolved**, the model
fits the displaced label with a special-case rule (2 of 4 wrong commits in `dev-4`, 1 wrong and 1 spurious "correct" in
`dev-5`). The catalogue reference scores 15/15 and is oracle-assisted by construction: a ceiling, not a result.

## Real-file path (`realfile-2`, live Nemotron, cost about $0.7)
Five authored SVG fixtures (boxes + `<text>` labels; NOT third-party or user-exported files, see
`src/open_apprentice/svg/samples/NOTICE.md`). Each intention is taught from a demonstration made on ONE file (for conditional, the demo
must show the fallback; for scope, contain a warning label. Demonstrations were NOT required to pin one catalogue behaviour: a
filter meant to do that was never applied in `realfile-1..4`, a silent script-edit miss found by lint on 15 Oct and now only
the opt-in `--require-pinned` flag. Some demos may therefore be ambiguous within the catalogue), and the learned rule is applied to every OTHER file as a
byte-exact patch of label `x`/`y` only; the patched SVG is re-parsed and judged by the checker (intent, preservation, layout).
Label boxes are estimated from font size, not measured in a browser.

| Intention | Applications | Correct | On targets that actually exercise it |
|---|---|---|---|
| relative | 20 | 20 | 20/20 |
| scope | 20 | 20 | 20/20 |
| conditional | 12 | 11 | 5/6 |
| total | 52 | 51 | |

0 unrelated byte changes in every patch. **One real failure, a layout violation:** a conditional rule taught on `tight-grid.svg`
tested only overlap, not the canvas edge, because that demonstration (and the synthetic batch, all 1200 wide) never showed an
off-canvas right-hand spot. Applied to the 560-wide `edge-cluster.svg` it pushed two labels off the canvas. Under the gate rule
(zero accepted violations) this is a miss. Possible fix (untested): vary canvas sizes in the teaching batch.
Also: the first real-file run (`realfile-1`, 14/14) is retracted. Its conditional targets never exercised the fallback, and
building the fuller set exposed an oracle bug (a hard-coded 1200x800 canvas instead of the scene's own), now fixed with a
regression test. The bug did not affect the synthetic development or gate results (all synthetic canvases are 1200x800).

### Real-file reruns after the off-canvas failure (post hoc, tuned on these same fixtures)
- `realfile-3` (teaching batches now include narrow canvases): 44/52 correct, 8 abstained (all conditional, "failed on a
  held-back batch diagram"), 0 violations. The old violation became a safe abstain.
- `realfile-4` (plus one revision round when validation rejects every survivor, the failed diagram becomes evidence):
  **52/52 correct**, conditional 12/12 (6/6 on targets that exercise the fallback), 0 abstained, 0 violations, 0 unrelated bytes.
- Caveat: both changes were made after seeing this failure on these five fixtures, so `realfile-4` is NOT independent evidence.
  A fresh set of fixtures (ideally exported from a real tool) is required before this is cited as generalisation.

### Regression check after the validation-revision round (`dev-6`, development noisy + unsupported, one run)
0 wrong commits in 8 (unsupported: 2 appropriate abstains + 2 truncation errors; noisy: 3 appropriate abstains + 1 spurious "correct"
commit whose rule contains a special-case clause the fresh documents did not trigger). So the revision round did not bring wrong commits back
here, but n is small and a revised rule only has to pass the remaining held-back documents, a weaker check.

## Still required for the gate
- Browser-measured label boxes on the real files (the current boxes are estimates); real user-exported files.
- Two external reactions (record as unavailable if not obtained).
- Repeated runs (the gate set at least 3 times) and a frozen held-out split.
- Cost so far: $38.60 (the last paid run; no more experiments without the owner's approval) of $40 spendable (authorized $50, reserve $10), including discarded runs.
