# Evaluation report — cal-3e42a9e799961d84-20261017T010307

Split `dev`, mode `live`, systems B.

Coverage: runs with an outcome: 2 of 2 (0 stopped by the dollar cap).

## Release-blocking checks

- boundary violations: 0
- accepted preservation violations: 0
- unexplained retention regressions: 0
- rows labelled live in a mock run: 0

## Primary endpoints

**learning success**

- B: 1/2 runs

**correction success (end to end)**

- B: 0/0 runs

Correction success given acquisition (denominator = runs that acquired the rule):
- B: 0/0

## Per stratum

| stratum | B |
|---|---|
| beyond | 0/1 |
| catalogue | 1/1 |

## Per behaviour spec

| spec_kind | B |
|---|---|
| catalogue | 1/1 |
| gap_by_width | 0/1 |

## Terminal outcomes

- B: correct_complete 1, unnecessary_abstention 1

## Diagnostics (sums)

- B: budget_exhausted 1, parse_failures 18, preservation_violation_blocked 0, protocol_failures 0, provider_failures 1, unsafe_proposal_blocked 0

## Cost per episode (every run, stopped ones included)

- B: mean $0.1878, mean tokens 67383, mean wall 138.8 s

## Repeat-to-repeat variation

- B: r0 1/2

Intervals describe this task collection only.
