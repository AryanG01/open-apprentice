# Evaluation report — dryrun-20261018

**Offline dry run — not a model result.** Rows are `origin=mock` with a fixture candidate source (`model=Fixture`): they check the pipeline, the scoring and the boundary, and say nothing about any model.

Split `dev`, mode `mock`, systems A, A2, B, C, D, D2.

**A2 / D2: post-freeze policy v2 (designed after the final rows were seen).** More revision rounds and truncation-tolerant rounds, nothing else; their numbers are post-hoc and are shown next to the unchanged A, B and D rows, which stay published.

Coverage: runs with an outcome: 108 of 108 (0 stopped by the dollar cap).

## Release-blocking checks

- boundary violations: 0
- accepted preservation violations: 0
- unexplained retention regressions: 0
- rows labelled live in a mock run: 0

## Primary endpoints

**learning success** (fixture, not a model result)

- A: 2/8 runs
- A2: 2/8 runs
- B: 2/8 runs
- C: 4/8 runs
- D: 2/8 runs
- D2: 2/8 runs
- A − B: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 8 episodes; sign test +0 / −0 / ties 8, p = 1.0000
- A2 − B: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 8 episodes; sign test +0 / −0 / ties 8, p = 1.0000
- A2 − A: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 8 episodes; sign test +0 / −0 / ties 8, p = 1.0000
- A2 − D2: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 8 episodes; sign test +0 / −0 / ties 8, p = 1.0000
- A − C: mean episode difference -0.250, 95% bootstrap [-0.625, +0.000], 8 episodes; sign test +0 / −2 / ties 6, p = 0.5000
- A − D: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 8 episodes; sign test +0 / −0 / ties 8, p = 1.0000

**correction success (end to end)** (fixture, not a model result)

- A: 5/6 runs
- A2: 5/6 runs
- B: 5/6 runs
- C: 5/6 runs
- D: 5/6 runs
- D2: 5/6 runs
- A − B: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000
- A2 − B: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000
- A2 − A: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000
- A2 − D2: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000
- A − C: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000
- A − D: mean episode difference +0.000, 95% bootstrap [+0.000, +0.000], 6 episodes; sign test +0 / −0 / ties 6, p = 1.0000

Correction success given acquisition (denominator = runs that acquired the rule):
- A: 5/6
- A2: 5/6
- B: 5/6
- C: 5/6
- D: 5/6
- D2: 5/6

## Per stratum

| stratum | A | A2 | B | C | D | D2 |
|---|---|---|---|---|---|---|
| beyond | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 |
| catalogue | 2/4 | 2/4 | 2/4 | 4/4 | 2/4 | 2/4 |
| inconsistent | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| sequential | 5/6 | 5/6 | 5/6 | 5/6 | 5/6 | 5/6 |
| unsupported | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |

## Per behaviour spec

| spec_kind | A | A2 | B | C | D | D2 |
|---|---|---|---|---|---|---|
| catalogue | 11/14 | 11/14 | 11/14 | 13/14 | 11/14 | 11/14 |
| fallback_chain | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| gap_by_width | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| role_sides | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| size_side | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |

## Terminal outcomes

- A: appropriate_refusal 4, correct_complete 7, unnecessary_abstention 7
- A2: appropriate_refusal 4, correct_complete 7, unnecessary_abstention 7
- B: appropriate_refusal 4, correct_complete 7, unnecessary_abstention 7
- C: appropriate_refusal 4, correct_complete 9, unnecessary_abstention 5
- D: appropriate_refusal 4, correct_complete 7, unnecessary_abstention 7
- D2: appropriate_refusal 4, correct_complete 7, unnecessary_abstention 7

## Refusals by kind

- A: no_program 2, refused_layout 1, unsupported_structure 1
- A2: no_program 2, refused_layout 1, unsupported_structure 1
- B: agent_abstained 3, unsupported_structure 1
- C: no_program 2, refused_layout 1, unsupported_structure 1
- D: no_program 2, refused_layout 1, unsupported_structure 1
- D2: no_program 2, refused_layout 1, unsupported_structure 1

## Diagnostics (sums)

- A: budget_exhausted 0, correction_agent_turns 0, correction_proposer_calls 8, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- A2: budget_exhausted 0, correction_agent_turns 0, correction_proposer_calls 8, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- B: budget_exhausted 0, correction_agent_turns 20, correction_proposer_calls 6, parse_failures 11, preservation_violation_blocked 2, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- C: budget_exhausted 0, correction_agent_turns 0, correction_proposer_calls 10, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- D: budget_exhausted 0, correction_agent_turns 0, correction_proposer_calls 8, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- D2: budget_exhausted 0, correction_agent_turns 0, correction_proposer_calls 8, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0

## Correction effort (sequential episodes, mean per run)

- A: proposer calls 1.3, agent turns 0.0
- A2: proposer calls 1.3, agent turns 0.0
- B: proposer calls 1.0, agent turns 3.3
- C: proposer calls 1.7, agent turns 0.0
- D: proposer calls 1.3, agent turns 0.0
- D2: proposer calls 1.3, agent turns 0.0

B's correction cycle may use more provider calls than A's: every B decision is itself a model call, and B gets the
spec's 4 correction attempts plus whatever its learning cycle left unused (never more than 12 in all). A's policy runs
at most a scope round and one revision round. Read the correction comparison with that difference in mind.

## Cost per episode (every run, stopped ones included)

- A: mean $0.0000, mean tokens 0, mean wall 0.3 s
- A2: mean $0.0000, mean tokens 0, mean wall 0.4 s
- B: mean $0.0000, mean tokens 14413, mean wall 0.5 s
- C: mean $0.0000, mean tokens 0, mean wall 1.0 s
- D: mean $0.0000, mean tokens 0, mean wall 0.3 s
- D2: mean $0.0000, mean tokens 0, mean wall 0.4 s

## Repeat-to-repeat variation

- A: r0 11/18
- A2: r0 11/18
- B: r0 11/18
- C: r0 13/18
- D: r0 11/18
- D2: r0 11/18

Intervals describe this task collection only.
