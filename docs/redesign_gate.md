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

## Things that changed after the development runs (disclosed)
1. Contrastive round, contradiction feedback, lenient parsing, agent format-error tolerance (after `dev-1`).
2. Parser accepts `else if` and double-escaped newlines; nesting limit 6 to 8; one retry on transient provider errors;
   a prompt example of a blocked-spot scan on an unrelated task; constants-in-comparisons guard (after `dev-2`).
3. Held-back validation: survivors must reproduce the teacher's answer on every batch diagram not already asked, else the
   system abstains (after `dev-3` / `dev-4`). It reads teacher answers on batch diagrams, never the fresh scoring documents.
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
`src/open_apprentice/svg/samples/NOTICE.md`). Each intention is taught from a demonstration made on ONE file (demo must pin the
behaviour alone and, for conditional, must show the fallback), and the learned rule is applied to every OTHER file as a
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

## Still required for the gate
- Browser-measured label boxes on the real files (the current boxes are estimates); real user-exported files.
- Two external reactions (record as unavailable if not obtained).
- Repeated runs (the gate set at least 3 times) and a frozen held-out split.
- Cost so far: $24.98 of $40 spendable (authorized $50, reserve $10), including discarded runs.
