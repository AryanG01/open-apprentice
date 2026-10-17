# Evaluation report — cal-06215ff627e60f06-20261017T113625

Split `dev`, mode `live`, systems B.

Coverage: runs with an outcome: 2 of 2 (0 stopped by the dollar cap).

## Release-blocking checks

- boundary violations: 0
- accepted preservation violations: 0
- unexplained retention regressions: 0
- rows labelled live in a mock run: 0

## Primary endpoints

**learning success**

- B: 2/2 runs

**correction success (end to end)**

- B: 0/0 runs

Correction success given acquisition (denominator = runs that acquired the rule):
- B: 0/0

## Per stratum

| stratum | B |
|---|---|
| beyond | 1/1 |
| catalogue | 1/1 |

## Per behaviour spec

| spec_kind | B |
|---|---|
| catalogue | 1/1 |
| gap_by_width | 1/1 |

## Terminal outcomes

- B: correct_complete 2

## Diagnostics (sums)

- B: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0

## Cost per episode (every run, stopped ones included)

- B: mean $0.1386, mean tokens 68178, mean wall 119.8 s

## Repeat-to-repeat variation

- B: r0 2/2

Intervals describe this task collection only.
