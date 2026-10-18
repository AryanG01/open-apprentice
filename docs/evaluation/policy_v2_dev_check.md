# Policy v2 (A2) — development check, 2026-10-18 (Plan 7, stage 1)

**Verdict: the pre-registered rule was not met. Policy v2 is not adopted and was not re-run on the final split.**

What was tested: `A2` = A with three revision rounds instead of one and truncation-tolerant rounds (`docs/decisions.md`,
"Policy v2"), same prompts, same 8-attempt budget. The rule, fixed before any result: go to the paid final re-run only if
learning success on the 8 catalogue + beyond development episodes is at least 6/8 and there is at most 1 wrong commit.

Run `cal-8056650661775e1a-…` (manifest `8056650661775e1a`, A2, 2 workers, cap $4.50). It was stopped by hand after the 8
learning episodes, because 6/8 could no longer be reached; 9 of 14 runs completed. Ledger spend **$2.38**.

| Episode | A2 | Cost |
|---|---|---|
| catalogue × 4 | 3 correct, **1 wrong commit** | $0.08–0.22 |
| beyond × 4 | 2 correct, 2 abstentions ("unresolved disagreement", "no acceptable program") | $0.12, $0.19, **$0.76, $1.10** |
| sequential (1 completed) | acquired; correction abstained | $0.10 |

**Learning success 5/8 against the 6/8 bar.** For comparison A scored 22/48 (46%) on the final learning episodes; the
development episodes are different and small, so 5/8 is a suggestive improvement, not evidence of one.

## What the check also showed

1. **v2 is expensive.** The 8 learning runs averaged about $0.34 each (A: $0.17 on the final split), and two "beyond"
   episodes cost $0.76 and $1.10 for 3 calls each: replies that ran to the completion cap, retried, and were then counted as
   rounds. The extra rounds spend the money A saved.
2. **One wrong commit** on a catalogue episode, the same failure kind as A's 3 on the final split.
3. The expected failure of the plain policy (every candidate rejected) is only partly fixed by extra rounds: 2 of the 4 beyond
   episodes still ended without a program.

## Consequence

The final-split results stand as published (`docs/evaluation/final_results.md`): A does not beat B on either primary
endpoint. v2 stays in the code, off by default (`A2`, `D2`), as an experiment that was tried and not adopted. Further
spending on A's accuracy is not justified by this check; the funded budget goes to the demo and its live cap.
