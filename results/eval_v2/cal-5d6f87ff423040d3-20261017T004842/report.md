# Evaluation report — cal-5d6f87ff423040d3-20261017T004842

Split `dev`, mode `live`, systems B.

Coverage: runs with an outcome: 1 of 1 (0 stopped by the dollar cap).

## Release-blocking checks

- boundary violations: 0
- accepted preservation violations: 0
- unexplained retention regressions: 0
- rows labelled live in a mock run: 0

## Primary endpoints

**learning success**

- B: 0/1 runs

**correction success (end to end)**

- B: 0/0 runs

Correction success given acquisition (denominator = runs that acquired the rule):
- B: 0/0

## Per stratum

| stratum | B |
|---|---|
| catalogue | 0/1 |

## Per behaviour spec

| spec_kind | B |
|---|---|
| catalogue | 0/1 |

## Terminal outcomes

- B: unnecessary_abstention 1

## Diagnostics (sums)

- B: budget_exhausted 1, parse_failures 2, preservation_violation_blocked 0, protocol_failures 0, provider_failures 1, unsafe_proposal_blocked 0

## Cost per episode (every run, stopped ones included)

- B: mean $0.2876, mean tokens 87946, mean wall 224.2 s

## Repeat-to-repeat variation

- B: r0 0/1

Intervals describe this task collection only.
