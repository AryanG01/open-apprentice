# Calibration run results (live, 2026-10-16)

Run `cal-73be473a2babd420-20261016T233138` under the owner-approved manifest `73be473a2babd420` (5 dev episodes ×
A, B; cap $1.05; reserve lowered to $5 by the owner). Model `nvidia/Nemotron-3-Ultra-550b-a55b` on Nebius Token Factory,
low reasoning effort. Rows and report: `results/eval_v2/cal-73be473a2babd420-20261016T233138/`. This is a calibration
run: it measures prompt viability and cost, **not an A-versus-B result** (3 outcomes cannot support one).

## Spend

- This run: **$0.871** (SpendGuard ledger, run id above), within the $1.05 cap. One diagnostic call: $0.0001.
- Owner-reported balance before the run: $7.17 → expected about **$6.30** now, if nothing else spent (to be confirmed).

## What ran

| Episode (stratum) | A | B |
|---|---|---|
| catalogue | correct_complete — 2 calls, $0.066 | unnecessary_abstention — used all 8 turns, $0.301 |
| beyond catalogue | correct_complete — 2 calls, $0.118 | stopped by the dollar cap after 8 turns, $0.345 |
| inconsistent | stopped by the dollar cap, $0 | stopped by the dollar cap after 2 turns, $0.041 |
| unsupported | stopped by the dollar cap, $0 | stopped by the dollar cap, $0 |
| sequential | stopped by the dollar cap, $0 | stopped by the dollar cap, $0 |

Runs with an outcome: 3 of 10. Boundary violations: 0.

## Findings

1. **A's prompts are viable.** All of A's proposal calls parsed; both A runs committed a rule that was correct on all three
   fresh scoring documents (including a beyond-catalogue behaviour). About $0.09 per episode, 2 calls, ~35k tokens.
2. **B, as built, is not viable.**
   - 5 of its 16 turns were not usable tool calls:
     - twice it put `rules_text` at the top level instead of inside `args`;
     - once it added an extra `turn` key;
     - once it wrote `&&`/`||`;
     - once a rule had a stray character.
   - It never called `preview`, so it could never meet the commit check. It kept re-proposing a program that already
     fit, until its 8 attempts ran out.
   - About $0.04 per turn, $0.30–0.35 per episode.
   - Spec 4 foresees exactly this: "if parse failures dominate in calibration, a development-only sensitivity check
     decides the frozen representation".
3. **Cost re-estimate for the funded tier T3 (240 runs).**
   - At the observed per-episode costs: A 108 × ~$0.09 + B 108 × ~$0.32 + D 24 × ~$0.09 ≈ **$46**. That is before the
     sequential episodes' correction calls, which no run reached.
   - Budget **$50–60**, in line with the spec's $36–72. It needs a top-up well beyond the current balance.
4. **Bugs found and fixed during the run (each with a failing test first):**
   - The learner subtracted the run's spend from a cap that was already net of it, so 7 runs were refused before any
     call ($0). They were re-run under `--resume`; the first rows are kept in `rows.superseded.jsonl`.
   - The CLI fell through to the offline runner after a live run.
   - Budget refusals were classified as "other" and lost their error text.
   - Runs stopped by the dollar cap were scored as outcomes, e.g. "appropriate_refusal" at $0. They are now
     `budget_stop` and are left out of the endpoints.
   - The runner's stop threshold ($0.13) was below the learner's per-call reservation ($0.20).

## Recommended next step (needs the owner)

A development-only revision of B's prompt and tool-call parsing:
- accept `args` given at the top level;
- state the preview → commit path;
- remind it of the `and`/`or` syntax.

Then a second, small calibration: B only, on the same 5 dev episodes, about **$1.6** at the observed $0.32 per
episode. A needs no change. The funded tier should wait for that, and for a top-up.

## B re-check after the fix (live, 2026-10-17) — stopped early

Run `cal-5d6f87ff423040d3-20261017T004842` (manifest `5d6f87ff423040d3`, B only, cap $1.25). **Spent $0.288.** I
stopped it after the first episode to save the remaining budget, because the failure was the same:
- The fixes worked mechanically: no flattened-argument parse failures, and no `&&`/`||`.
- B still never called `preview`. It re-proposed P1 four times, although each reply told it "P1 already proposed and
  still fits ... preview it and then commit".
- Twice it called `request_demo` / `ask_choose` without a document id.
- One call was truncated, and it ran out of its 8 attempts.

This makes three B episodes with the same pattern: with this prompt, the model does not follow the tool protocol's
stopping path. B as specified (same model, acting freely) is therefore a very weak baseline here. An A-versus-B result
would mostly measure B's inability to drive the tools, not the value of A's policy.

Spend logged so far: $39.76 of $45.77 funded; $1.01 left above the $5 reserve.
