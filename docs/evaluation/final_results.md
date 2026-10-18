# Final evaluation results — frozen battery (battery-v2.5, score-v2.2), live Nemotron, 2026-10-18

Funded tier T3 as approved: `funded_T3_AB` (`e4ea884834edb06a`, A and B × 3 repeats on the 36 synthetic final episodes = 216
runs, $38.71 of a $38.90 cap) and `funded_T3_D` (`0927857b4f1ea46b`, D × 3 on 8 clarification-required episodes = 24 runs,
$2.68 of $3.20). Model `nvidia/Nemotron-3-Ultra-550b-a55b` on Nebius Token Factory, low reasoning effort. Rows and the full
generated report: `results/eval_v2/final-funded-20261018/` (`rows.jsonl`, `report.md`). Every run completed; **0 boundary
violations, 0 accepted preservation violations, 0 unexplained retention regressions.**

**Intervals describe this task collection only.** The battery is synthetic label-placement layouts, 16 learning episodes and
12 correction episodes; nothing here is a claim about other tasks, models or people.

## Primary endpoints (both reported, as the plan fixed)

| Endpoint | A (apprentice) | B (same model, free agent) | A − B (per-episode mean) | 95% interval | Sign test |
|---|---|---|---|---|---|
| Learning success (16 episodes × 3) | 22/48 | 28/48 | −0.125 | [−0.292, +0.042] | +4 / −7 / 5 ties, p = 0.55 |
| Correction success, end to end (12 × 3) | 18/36 | 22/36 | −0.111 | [−0.333, +0.111] | +2 / −4 / 6 ties, p = 0.69 |

**Neither endpoint shows A ahead; the point estimates favour B, and neither is distinguishable from zero.** The
hypothesis that the apprentice's question-asking policy raises success over the same model acting freely is **not supported
by this run.**

## Where the differences are

| Slice | A | B | Note |
|---|---|---|---|
| Refusal strata (inconsistent + unsupported), appropriate refusal | **18/24** | 9/24 | +0.375 per episode, +4 / −0 / 4 ties, exact p = 0.125 |
| Inconsistent demonstrations (conflict surfaced) | **12/12** | 6/12 | B often runs out of attempts instead of surfacing the conflict |
| Catalogue, clarification-required (ambiguous demonstrations) | 2/12 | 0/12 | +2 / −0 / 2 ties, p = 0.50; B never succeeded here |
| Catalogue, identifiable | 7/12 | **12/12** | B is better when the demonstrations pin the rule down |
| Beyond catalogue | 13/24 | 16/24 | |
| Sequential (acquire, then correct) | 18/36 | 22/36 | acquisition 30/36 for both; correction given acquisition A 18/30, B 24/30 |

Cost and safety:
- **A is cheaper:** $0.17 per run against $0.26, 2.5 model calls against 4.2, and $0.32 per success against $0.47.
- **Wrong commits are equal:** 3 for A, 3 for B. Of the runs that committed, 94.5% (A) and 95.1% (B) were correct on fresh
  documents, so A is not safer on this measure, only more willing to abstain.
- **D (uniform random questions), 24 runs:** learning 1/12 and correction 7/12 on 4 episodes each; against A on the same
  episodes the differences are too small to read (n = 4 episodes).

## Why A loses where it does

- **A's dominant failure is "no acceptable program found within the search limits" (21 of its 54 non-successes),** plus
  7 sequential "no acceptable interpretation" and 4 "too many affected examples to review". A makes at most three proposal
  rounds and uses 2.5 of its 8 allowed attempts on average; every candidate it proposed was rejected by the shared filters.
  B, which chooses its own steps, simply proposes again (up to its 8 attempts) and eventually finds a fitting program,
  which is why it wins on identifiable rules.
- **B's dominant failure is not stopping:** 44 of its 72 non-successes are "budget exhausted: N provider attempts",
  including 9 of 12 unsupported runs where A refused at once, and it never succeeded on an ambiguous catalogue episode.
- **10 of A's runs ended in a provider truncation** (a reasoning-heavy reply cut at the completion cap), 6 of them on the
  unsupported episodes: a robustness gap, scored as errors.
- B's correction cycle needs more provider calls than A's (reported in the generated report's "Correction effort").

## What was not run, and what is not claimed

- **The 3 real-file episodes were not run.** The product's draw.io adapter refuses the frozen final file with "cell
  'btscb2uyhEqkDoFNjr_6-9' lies outside the page (0, 0, 700, 450)", so no system could be run on them (the refusal is the
  same for every system and was not worked around). The within-family generalisation result the plan reserved for them
  does not exist.
- The D set is 8 episodes by a fixed rule (4 catalogue + the first 4 sequential by id), not the spec's unspecified 8.
- Costs include about $2 of worst-case charges from stalls while the laptop slept; they are in the ledger and the totals.
- A post-freeze change to either system's policy would need a new version identifier and a re-run of the affected slices;
  the rows above would stay published (spec 7). Nothing was tuned on these rows.
