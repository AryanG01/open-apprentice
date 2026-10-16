# Calibration manifest (Plan 5) — awaiting the owner's approval

Generated 2026-10-16 by `oa eval manifest` from the offline dry run (`results/eval_v2/dryrun-20261016/`). Machine-readable
copies: `docs/evaluation/manifests/calibration-76d79b2849370613.json` and the unapproved funded tier
`docs/evaluation/manifests/funded_T3-3b33b250cf5b7bda.json`. **Nothing has been spent; no provider call was made.**

## Calibration run `76d79b2849370613`

| | |
|---|---|
| Tasks | 5 development episodes, one per stratum: `e88727066d3` (catalogue), `e5a01549872` (beyond), `e7b523e24fc` (inconsistent), `ea5432e5dee` (unsupported), `e9bacad414c` (sequential) |
| Systems | A (apprentice) and B (same-model agent), 1 repeat: 10 runs |
| Attempt ceilings | 12 per run for each system (8 learning + 4 correction, spec 3.7) |
| Worst-case reservation | $0.088 per attempt ((16k prompt + 6k completion) tokens at SpendGuard's $4/M); $10.56 if every run used every attempt at worst case |
| Actual-cost estimate | about 145k tokens → **$0.51** (dry-run tokens per episode: A 10.7k, B 18.4k, at $3.5/M; completion tokens are an assumption of 2,000 per attempt) |
| Run cap ceiling | **$1.05** (2× the estimate, rounded up); `--cap-usd` may not exceed it |
| Stop conditions | the run cap (SpendGuard refuses a call whose worst case would pass it); the global ceiling (min(authorized, funded) − reserve, across all runs); any information-boundary violation |
| Protected reserve | $10 (never touched; the gate refuses a cap that would reach it) |
| What it can establish | whether A's and B's prompts parse and run end to end on the live model, and the real cost per episode. **Not an A-versus-B result.** |

## Budget position

`results/redesign/budget.json`: $50 authorized and funded, $10 reserve → $40 spendable; $38.60 already spent → **$1.40
remaining**. The calibration ceiling ($1.05) fits, leaving about $0.35. The estimate rests on an assumed completion size;
if real completions run long (output-heavy runs cost $3–4/M), SpendGuard stops the run at the cap and the partial rows
are kept and reported as partial.

## Funded tier T3 `3b33b250cf5b7bda` (generated, not approved)

240 runs (A and B × 3 repeats on the 36 final episodes, D × 3 on 8 clarification-required episodes). Dry-run-based
estimate about 3.4M tokens / **$11.9**; worst case $253. The spec's own estimate was $36–72. The dry-run figure is low
because the fixture stand-in for B stops after about 2.6 turns, where a live B may use all 12; it must be re-estimated
from the calibration run before approval. Either way it needs a top-up: it does not fit the $1.40 remaining.

## How approval works

1. The owner approves calibration manifest `76d79b2849370613` in chat and confirms the budget (and any top-up, which
   updates `funded_usd` in `results/redesign/budget.json`).
2. Only then is `docs/evaluation/approved/76d79b2849370613.json` written: the manifest plus `approved: true`,
   `approved_by` and `approved_at`. Its id is the hash of its terms, so an edited copy is refused. The file is a record
   of the owner's word in chat, not an access control.
3. `oa eval run --split dev --systems A,B --repeats 1 --episodes <the five ids> --mode live --manifest 76d79b2849370613
   --cap-usd 1.05` checks the gate before building any provider; a run whose split, systems, episodes or repeats differ
   from the manifest is refused. Today the gate refuses (no approval file); after approval it passes and stops with NOT_IMPLEMENTED, because
   the live learner wiring (provider and SpendGuard inside the learner process) is built only after approval.
4. Before the funded tier: system B needs its own correction tools (propose_scope, affected-example approval, revision
   preview). Today B's corrections run A's correction policy, so the correction endpoint cannot support an A-versus-B
   claim (rows carry `correction_policy="A"`, and the report says so).
