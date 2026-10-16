# Evaluation report — cal-73be473a2babd420-20261016T233138

Split `dev`, mode `live`, systems A, B.

Coverage: runs with an outcome: 3 of 10 (7 stopped by the dollar cap).

## Release-blocking checks

- boundary violations: 0
- accepted preservation violations: 0
- unexplained retention regressions: 0
- rows labelled live in a mock run: 0

## Primary endpoints

**learning success**

- A: 2/2 runs
- B: 0/1 runs
- A − B: mean episode difference +1.000, 95% bootstrap n/a, 1 episodes; sign test +1 / −0 / ties 0, p = 1.0000

**correction success (end to end)**

- A: 0/0 runs
- B: 0/0 runs
- A − B: mean episode difference n/a, 95% bootstrap n/a, 0 episodes; sign test +0 / −0 / ties 0, p = 1.0000

Correction success given acquisition (denominator = runs that acquired the rule):
- A: 0/0
- B: 0/0

## Per stratum

| stratum | A | B |
|---|---|---|
| beyond | 1/1 | – |
| catalogue | 1/1 | 0/1 |

## Per behaviour spec

| spec_kind | A | B |
|---|---|---|
| catalogue | 1/1 | 0/1 |
| gap_by_width | 1/1 | – |

## Terminal outcomes

- A: correct_complete 2
- B: unnecessary_abstention 1

## Diagnostics (sums)

- A: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- B: budget_exhausted 1, parse_failures 3, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0

## Cost per episode (every run, stopped ones included)

- A: mean $0.0368, mean tokens 14137, mean wall 31.5 s
- B: mean $0.1374, mean tokens 37948, mean wall 113.6 s

## Repeat-to-repeat variation

- A: r0 2/2
- B: r0 0/1

Intervals describe this task collection only.
