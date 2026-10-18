# Evaluation report — final-funded-20261018

Split `final`, mode `live`, systems A, B, D.

## Not run: refused by the draw.io adapter

- `e74e24dfbc3`: cell 'btscb2uyhEqkDoFNjr_6-9' lies outside the page (0, 0, 700, 450); release 1 edits only inside it
- `e8d706a6917`: cell 'btscb2uyhEqkDoFNjr_6-9' lies outside the page (0, 0, 700, 450); release 1 edits only inside it
- `ea8e1486ac8`: cell 'btscb2uyhEqkDoFNjr_6-9' lies outside the page (0, 0, 700, 450); release 1 edits only inside it

The product's adapter refuses these files, so no system was run on them; the refusal is the same for every system and is reported rather than worked around.

Coverage: runs with an outcome: 240 of 240 (0 stopped by the dollar cap).

## Release-blocking checks

- boundary violations: 0
- accepted preservation violations: 0
- unexplained retention regressions: 0
- rows labelled live in a mock run: 0

## Primary endpoints

**learning success**

- A: 22/48 runs
- B: 28/48 runs
- D: 1/12 runs
- A − B: mean episode difference -0.125, 95% bootstrap [-0.292, +0.042], 16 episodes; sign test +4 / −7 / ties 5, p = 0.5488
- A − D: mean episode difference +0.083, 95% bootstrap [-0.167, +0.333], 4 episodes; sign test +2 / −1 / ties 1, p = 1.0000

**correction success (end to end)**

- A: 18/36 runs
- B: 22/36 runs
- D: 7/12 runs
- A − B: mean episode difference -0.111, 95% bootstrap [-0.333, +0.111], 12 episodes; sign test +2 / −4 / ties 6, p = 0.6875
- A − D: mean episode difference +0.000, 95% bootstrap [-0.250, +0.250], 4 episodes; sign test +1 / −1 / ties 2, p = 1.0000

Correction success given acquisition (denominator = runs that acquired the rule):
- A: 18/30
- B: 24/30
- D: 7/10

## Per stratum

| stratum | A | B | D |
|---|---|---|---|
| beyond | 13/24 | 16/24 | – |
| catalogue | 9/24 | 12/24 | 1/12 |
| inconsistent | 12/12 | 6/12 | – |
| sequential | 18/36 | 22/36 | 7/12 |
| unsupported | 6/12 | 3/12 | – |

## Per behaviour spec

| spec_kind | A | B | D |
|---|---|---|---|
| catalogue | 45/78 | 43/78 | 8/24 |
| fallback_chain | 1/6 | 4/6 | – |
| gap_by_width | 3/6 | 5/6 | – |
| role_sides | 5/6 | 4/6 | – |
| size_side | 4/6 | 3/6 | – |
| unobservable | 0/6 | 0/6 | – |

## Terminal outcomes

- A: appropriate_refusal 18, correct_complete 40, error 11, unnecessary_abstention 36, wrong_commit 3
- B: appropriate_refusal 9, correct_complete 50, error 44, unnecessary_abstention 2, wrong_commit 3
- D: correct_complete 8, error 1, unnecessary_abstention 14, wrong_commit 1

## Refusals by kind

- A: no_program 12, refused_layout 3, unsupported_structure 3
- B: agent_abstained 6, unsupported_structure 3
- D: none

## Diagnostics (sums)

- A: budget_exhausted 0, correction_agent_turns 0, correction_proposer_calls 43, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 34, unsafe_proposal_blocked 0
- B: budget_exhausted 44, correction_agent_turns 139, correction_proposer_calls 41, parse_failures 60, preservation_violation_blocked 4, protocol_failures 0, provider_failures 7, unsafe_proposal_blocked 0
- D: budget_exhausted 0, correction_agent_turns 0, correction_proposer_calls 13, parse_failures 0, preservation_violation_blocked 0, protocol_failures 0, provider_failures 2, unsafe_proposal_blocked 0

## Correction effort (sequential episodes, mean per run)

- A: proposer calls 1.2, agent turns 0.0
- B: proposer calls 1.1, agent turns 3.9
- D: proposer calls 1.1, agent turns 0.0

B's correction cycle may use more provider calls than A's: every B decision is itself a model call, and B gets the
spec's 4 correction attempts plus whatever its learning cycle left unused (never more than 12 in all). A's policy runs
at most a scope round and one revision round. Read the correction comparison with that difference in mind.

## Cost per episode (every run, stopped ones included)

- A: mean $0.1702, mean tokens 39915, mean wall 282.4 s
- B: mean $0.2557, mean tokens 77032, mean wall 383.8 s
- D: mean $0.1197, mean tokens 38604, mean wall 129.4 s

## Repeat-to-repeat variation

- A: r0 22/36, r1 21/36, r2 15/36
- B: r0 21/36, r1 21/36, r2 17/36
- D: r0 2/8, r1 3/8, r2 3/8

Intervals describe this task collection only.
