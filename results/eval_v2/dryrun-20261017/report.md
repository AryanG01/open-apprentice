# Evaluation report — dryrun-20261017

**Offline dry run — not a model result.** Rows are `origin=mock` with a fixture candidate source (`model=Fixture`): they check the pipeline, the scoring and the boundary, and say nothing about any model.

Split `dev`, mode `mock`, systems A, B, C, D.

Coverage: runs with an outcome: 72 of 72 (0 stopped by the dollar cap).

## Release-blocking checks

- boundary violations: 0
- accepted preservation violations: 0
- unexplained retention regressions: 0
- rows labelled live in a mock run: 0

## Primary endpoints

**learning success** (fixture, not a model result)

- A: 2/8 runs
- B: 2/8 runs
- C: 4/8 runs
- D: 2/8 runs
- A − B: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 8 episodes; sign test +0 / −0 / ties 8, p = 1.0000
- A − C: mean episode difference -0.250, 95% bootstrap [-0.625, +0.000], 8 episodes; sign test +0 / −2 / ties 6, p = 0.5000
- A − D: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 8 episodes; sign test +0 / −0 / ties 8, p = 1.0000

**correction success (end to end)** (fixture, not a model result)

- A: 5/6 runs
- B: 5/6 runs
- C: 5/6 runs
- D: 5/6 runs
- A − B: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000
- A − C: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000
- A − D: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000

Correction success given acquisition (denominator = runs that acquired the rule):
- A: 5/6
- B: 5/6
- C: 5/6
- D: 5/6

## Per stratum

| stratum | A | B | C | D |
|---|---|---|---|---|
| beyond | 0/4 | 0/4 | 0/4 | 0/4 |
| catalogue | 2/4 | 2/4 | 4/4 | 2/4 |
| inconsistent | 2/2 | 2/2 | 2/2 | 2/2 |
| sequential | 5/6 | 5/6 | 5/6 | 5/6 |
| unsupported | 2/2 | 2/2 | 2/2 | 2/2 |

## Per behaviour spec

| spec_kind | A | B | C | D |
|---|---|---|---|---|
| catalogue | 11/14 | 11/14 | 13/14 | 11/14 |
| fallback_chain | 0/1 | 0/1 | 0/1 | 0/1 |
| gap_by_width | 0/1 | 0/1 | 0/1 | 0/1 |
| role_sides | 0/1 | 0/1 | 0/1 | 0/1 |
| size_side | 0/1 | 0/1 | 0/1 | 0/1 |

## Terminal outcomes

- A: appropriate_refusal 4, correct_complete 7, unnecessary_abstention 7
- B: appropriate_refusal 4, correct_complete 7, unnecessary_abstention 7
- C: appropriate_refusal 4, correct_complete 9, unnecessary_abstention 5
- D: appropriate_refusal 4, correct_complete 7, unnecessary_abstention 7

## Refusals by kind

- A: no_program 2, refused_layout 1, unsupported_structure 1
- B: agent_abstained 3, unsupported_structure 1
- C: no_program 2, refused_layout 1, unsupported_structure 1
- D: no_program 2, refused_layout 1, unsupported_structure 1

## Diagnostics (sums)

- A: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- B: budget_exhausted 0, parse_failures 11, preservation_violation_blocked 2, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- C: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- D: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0

## Cost per episode (every run, stopped ones included)

- A: mean $0.0000, mean tokens 0, mean wall 0.3 s
- B: mean $0.0000, mean tokens 14396, mean wall 0.5 s
- C: mean $0.0000, mean tokens 0, mean wall 1.0 s
- D: mean $0.0000, mean tokens 0, mean wall 0.3 s

## Repeat-to-repeat variation

- A: r0 11/18
- B: r0 11/18
- C: r0 13/18
- D: r0 11/18

Intervals describe this task collection only.

## Dry-run notes (offline dry run — not a model result)

- `oa eval run --split dev --systems A,B,C,D --repeats 1 --mode mock`, 2026-10-17, on the re-frozen dev battery
  (battery-v2.5, score-v2.2); 39 s, 72 learner processes. No provider call. A, C, D use offline candidate sources;
  B and B's correction cycle use scripted fixture policies (`policy=scripted_fixture`).
- The forced-overlap episode is now `appropriate_refusal` (`refused_layout`) for A, C and D. The B fixture reaches it
  after its commit was refused. The rotated-label episode stays a refusal for every system.
- The sequential episodes with a conflict script end in a correct non-revision for A, C and D; with B's own
  correction cycle the offline fixture commits and corrects through the same checks.
- 0 boundary violations; every row `origin=mock`, `model=Fixture`.
