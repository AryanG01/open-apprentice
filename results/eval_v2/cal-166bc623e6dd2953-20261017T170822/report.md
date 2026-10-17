# Evaluation report — cal-166bc623e6dd2953-20261017T170822

Split `dev`, mode `live`, systems A, B.

Coverage: runs with an outcome: 6 of 6 (0 stopped by the dollar cap).

## Release-blocking checks

- boundary violations: 0
- accepted preservation violations: 0
- unexplained retention regressions: 0
- rows labelled live in a mock run: 0

## Primary endpoints

**learning success**

- A: 0/0 runs
- B: 0/0 runs
- A − B: mean episode difference n/a, 95% bootstrap n/a, 0 episodes; sign test +0 / −0 / ties 0, p = 1.0000

**correction success (end to end)**

- A: 0/2 runs
- B: 1/2 runs
- A − B: mean episode difference -0.500, 95% bootstrap [-1.000, +0.000], 2 episodes; sign test +0 / −1 / ties 1, p = 1.0000

Correction success given acquisition (denominator = runs that acquired the rule):
- A: 0/2
- B: 1/2

## Per stratum

| stratum | A | B |
|---|---|---|
| sequential | 0/2 | 1/2 |
| unsupported | 1/1 | 0/1 |

## Per behaviour spec

| spec_kind | A | B |
|---|---|---|
| catalogue | 1/3 | 1/3 |

## Terminal outcomes

- A: appropriate_refusal 1, unnecessary_abstention 2
- B: correct_complete 1, error 1, unnecessary_abstention 1

## Refusals by kind

- A: refused_layout 1
- B: none

## Diagnostics (sums)

- A: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- B: budget_exhausted 1, parse_failures 0, preservation_violation_blocked 1, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0

## Cost per episode (every run, stopped ones included)

- A: mean $0.1181, mean tokens 43938, mean wall 134.4 s
- B: mean $0.1718, mean tokens 81375, mean wall 172.2 s

## Repeat-to-repeat variation

- A: r0 1/3
- B: r0 1/3

Intervals describe this task collection only.
