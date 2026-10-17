# Evaluation report — cal-7c5ebc6f173f450c-20261017T115319

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

- A: 0/1 runs
- B: 0/1 runs
- A − B: mean episode difference +0.000, 95% bootstrap n/a, 1 episodes; sign test +0 / −0 / ties 1, p = 1.0000

Note: system B's correction cycle runs A's correction policy (the shared correction executor and scope proposer), so the correction endpoint for A − B reflects acquisition only; it is not a comparison of correction policies.

Correction success given acquisition (denominator = runs that acquired the rule):
- A: 0/1
- B: 0/1

## Per stratum

| stratum | A | B |
|---|---|---|
| inconsistent | 1/1 | 1/1 |
| sequential | 0/1 | 0/1 |
| unsupported | 0/1 | 0/1 |

## Per behaviour spec

| spec_kind | A | B |
|---|---|---|
| catalogue | 1/3 | 1/3 |

## Terminal outcomes

- A: appropriate_refusal 1, unnecessary_abstention 1, wrong_commit 1
- B: appropriate_refusal 1, unnecessary_abstention 1, wrong_commit 1

## Diagnostics (sums)

- A: budget_exhausted 0, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- B: budget_exhausted 1, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 1, unsafe_proposal_blocked 0

## Cost per episode (every run, stopped ones included)

- A: mean $0.1287, mean tokens 47191, mean wall 193.7 s
- B: mean $0.2280, mean tokens 82849, mean wall 300.1 s

## Repeat-to-repeat variation

- A: r0 1/3
- B: r0 1/3

Intervals describe this task collection only.
