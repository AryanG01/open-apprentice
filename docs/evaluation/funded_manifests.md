# Funded tier T3 — manifests awaiting the owner's approval

Generated 2026-10-17 by `oa eval manifest --funded --ab-ceiling-usd 38.90 --d-ceiling-usd 3.20`. **Nothing has been
spent on them.** Machine-readable: `docs/evaluation/manifests/funded_T3_AB-e4ea884834edb06a.json` and
`funded_T3_D-0927857b4f1ea46b.json`. Run on the frozen final battery (hashes in `battery_final.md`), no peeking.

| | A and B (`e4ea884834edb06a`) | D ablation (`0927857b4f1ea46b`) |
|---|---|---|
| Episodes | 36 final + 3 real-file = 39 | 8 (4 catalogue clarification-required + the first 4 sequential by id) |
| Repeats | 3 | 3 |
| Runs | 234 (117 each for A and B) | 24 |
| Measured cost per episode | A $0.114, B $0.200 | $0.114 (A's policy and calls) |
| Estimate | $36.82 | $2.75 |
| Run cap (`--cap-usd` ceiling) | **$38.90** | **$3.20** |
| Protected reserve | $10 | $10 |

## Budget position

`budget.json`: authorized $100, funded $95.77, reserve $10; $43.58 logged → **$42.19 spendable**; owner-reported balance
$53.29 (before the last $0.92). The two caps total $42.10, so both can be approved without touching the reserve.

**Margin is thin:** the estimates use costs measured on 12 episodes (A $0.114, B $0.200). The A/B cap is 6% above the
estimate. If real costs run higher the run stops at its cap and keeps its partial results with the coverage reported
(`budget_stop` rows are left out of the endpoints). A top-up of $10 would remove that risk.

## Deviations from the spec's T3 text (recorded)

- Spec: A and B × 3 on all 36 episodes (216 runs) plus D × 3 on the 8 clarification-required episodes (24 runs).
  Here the 3 real-file episodes are added to A/B (234 runs), and "the 8 clarification-required" is read as the 4
  catalogue ones plus the first 4 sequential ones by id, because the battery marks 16 episodes clarification-required
  (4 catalogue, all 12 sequential). The rule is fixed before any final result.
- B's correction cycle may use more provider calls than A's; the report discloses it.

## How the run works

- `oa eval run --split final --systems A,B --repeats 3 --episodes <the 39 ids> --mode live --manifest e4ea884834edb06a
  --cap-usd 38.90 --workers 4`, then the D manifest the same way.
- The gate checks the approved copy, the run's shape and the budget before any provider call; the final files are checked
  against the committed hashes; the 3 real-file episodes are built through the engine from hash-checked files.
- Runs on this laptop, plugged in, lid open (`caffeinate -is`), about 5–8 hours with 4 workers; `--resume` continues.
- Approval = the owner says so in chat; then `docs/evaluation/approved/<id>.json` is written (the manifest plus
  `approved`, `approved_by`, `approved_at`).
