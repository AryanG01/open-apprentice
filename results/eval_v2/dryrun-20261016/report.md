# Evaluation report — dryrun-20261016

**Offline dry run — not a model result.** Rows are `origin=mock` with a fixture candidate source (`model=Fixture`): they check the pipeline, the scoring and the boundary, and say nothing about any model.

Split `dev`, mode `mock`, systems A, B, C, D.

## Release-blocking checks

- boundary violations: 0
- accepted preservation violations: 0
- unexplained retention regressions: 0
- rows labelled live in a mock run: 0

## Primary endpoints

**learning success** (fixture, not a model result)

- A: 4/8 runs
- B: 4/8 runs
- C: 4/8 runs
- D: 4/8 runs
- A − B: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 8 episodes; sign test +0 / −0 / ties 8, p = 1.0000
- A − C: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 8 episodes; sign test +0 / −0 / ties 8, p = 1.0000
- A − D: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 8 episodes; sign test +0 / −0 / ties 8, p = 1.0000

**correction success (end to end)** (fixture, not a model result)

- A: 5/6 runs
- B: 5/6 runs
- C: 5/6 runs
- D: 5/6 runs
- A − B: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000
- A − C: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000
- A − D: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000

Note: system B's correction cycle runs A's correction policy (the shared correction executor and scope proposer), so the correction endpoint for A − B reflects acquisition only; it is not a comparison of correction policies.

Correction success given acquisition (denominator = runs that acquired the rule):
- A: 5/6
- B: 5/6
- C: 5/6
- D: 5/6

## Per stratum

| stratum | A | B | C | D |
|---|---|---|---|---|
| beyond | 0/4 | 0/4 | 0/4 | 0/4 |
| catalogue | 4/4 | 4/4 | 4/4 | 4/4 |
| inconsistent | 2/2 | 2/2 | 2/2 | 2/2 |
| sequential | 5/6 | 5/6 | 5/6 | 5/6 |
| unsupported | 1/2 | 1/2 | 1/2 | 1/2 |

## Per behaviour spec

| spec_kind | A | B | C | D |
|---|---|---|---|---|
| catalogue | 12/14 | 12/14 | 12/14 | 12/14 |
| fallback_chain | 0/1 | 0/1 | 0/1 | 0/1 |
| gap_by_width | 0/1 | 0/1 | 0/1 | 0/1 |
| role_sides | 0/1 | 0/1 | 0/1 | 0/1 |
| size_side | 0/1 | 0/1 | 0/1 | 0/1 |

## Terminal outcomes

- A: appropriate_refusal 3, correct_complete 9, unnecessary_abstention 5, wrong_commit 1
- B: appropriate_refusal 3, correct_complete 9, unnecessary_abstention 5, wrong_commit 1
- C: appropriate_refusal 3, correct_complete 9, unnecessary_abstention 5, wrong_commit 1
- D: appropriate_refusal 3, correct_complete 9, unnecessary_abstention 5, wrong_commit 1

## Diagnostics (sums)

- A: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- B: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- C: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- D: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0

## Cost per episode

- A: mean $0.0000, mean tokens 0, mean wall 0.3 s
- B: mean $0.0000, mean tokens 11300, mean wall 0.4 s
- C: mean $0.0000, mean tokens 0, mean wall 0.7 s
- D: mean $0.0000, mean tokens 0, mean wall 0.3 s

## Repeat-to-repeat variation

- A: r0 12/18
- B: r0 12/18
- C: r0 12/18
- D: r0 12/18

Intervals describe this task collection only.

## Dry-run notes (offline dry run — not a model result)

- Command: `oa eval run --split dev --systems A,B,C,D --repeats 1 --mode mock` then `oa eval report`, 2026-10-16,
  on the re-frozen development battery (battery-v2.3, hash-verified before the run). Wall time 33.1 s for 72 learner
  processes, each talking to its own teacher process over inherited pipes. No provider call was made: A, C and D used
  offline candidate sources (the label enumerator; C the 24-program catalogue), B used `agent_b.scripted_policy`, a
  deterministic fixture standing in for the model.
- Every row is `origin=mock`, `model=Fixture`; the boundary check (imports, file reads under benchmarks/, private
  files, child processes) shows 0 violations.
- What the dry run exposed (pipeline facts, not model results): the offline enumerator cannot express beyond-catalogue
  behaviours, so every system abstains there; every system COMMITS the forced-overlap convention (dev unsupported
  episode 1) — the shared commit checks accept a demonstrated overlap, so "refuse to apply" is not implemented in the
  learning core and is scored `wrong_commit`.
- Token estimate for pricing (`token_estimate.json`, `analysis_v2.token_estimate`): prompt sizes are measured from what
  each system sent (conservative len/3 estimate); completion tokens are ASSUMED at 2000 per attempt until calibration
  measures them. Per episode: A ≈ 10.7k tokens (max 20.6k, 2.3 attempts), B ≈ 18.4k (max 34.5k, 2.6 turns). The
  fixture B stops early; a live B may use up to its 8 + 4 attempt ceilings, which the worst-case reservation covers.
