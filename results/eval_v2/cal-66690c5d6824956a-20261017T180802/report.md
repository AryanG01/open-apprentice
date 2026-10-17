# Evaluation report — cal-66690c5d6824956a-20261017T180802

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

- A: 2/2 runs
- B: 1/2 runs
- A − B: mean episode difference +0.500, 95% bootstrap [+0.000, +1.000], 2 episodes; sign test +1 / −0 / ties 1, p = 1.0000

Correction success given acquisition (denominator = runs that acquired the rule):
- A: 2/2
- B: 1/2

## Per stratum

| stratum | A | B |
|---|---|---|
| sequential | 2/2 | 1/2 |
| unsupported | 1/1 | 0/1 |

## Per behaviour spec

| spec_kind | A | B |
|---|---|---|
| catalogue | 3/3 | 1/3 |

## Terminal outcomes

- A: appropriate_refusal 1, correct_complete 2
- B: correct_complete 1, error 2

## Refusals by kind

- A: refused_layout 1
- B: none

## Diagnostics (sums)

- A: budget_exhausted 0, correction_agent_turns 0, correction_proposer_calls 2, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0
- B: budget_exhausted 2, correction_agent_turns 10, correction_proposer_calls 4, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 0, unsafe_proposal_blocked 0

## Correction effort (sequential episodes, mean per run)

- A: proposer calls 1.0, agent turns 0.0
- B: proposer calls 2.0, agent turns 5.0

B's correction cycle may use more provider calls than A's: every B decision is itself a model call, and B gets the
spec's 4 correction attempts plus whatever its learning cycle left unused (never more than 12 in all). A's policy runs
at most a scope round and one revision round. Read the correction comparison with that difference in mind.

## Cost per episode (every run, stopped ones included)

- A: mean $0.1115, mean tokens 41354, mean wall 122.0 s
- B: mean $0.1877, mean tokens 87454, mean wall 188.7 s

## Repeat-to-repeat variation

- A: r0 3/3
- B: r0 1/3

Intervals describe this task collection only.
