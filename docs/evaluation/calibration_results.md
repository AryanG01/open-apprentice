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

## B with the option protocol (live, 2026-10-17)

Run `cal-3e42a9e799961d84-20261017T010307` (manifest `3e42a9e799961d84`, B only, catalogue and beyond, cap $0.70).
**Spent $0.437**, of which about $0.06 went to an attempt lost when the laptop slept mid-call (resumed under
`caffeinate -i`).

| Episode | B (option protocol) | B before (free tool calls) |
|---|---|---|
| catalogue | **correct_complete** — 4 calls, $0.063 | 8 calls, no commit, $0.30 |
| beyond catalogue | 8 calls, no rule parsed, $0.31 | 8 calls, no commit, $0.35 |

- **The protocol fix worked:** on the catalogue episode B proposed, previewed and committed a correct rule in half the
  calls.
- **On the harder episode the remaining failure is writing rules in the language.**
  - Its first call was cut off at the output limit.
  - It then wrote rules as English prose ("Nodes have fixed positions…") or pseudo-code ("for each label in labels:").
    That gave 18 unparseable rules, so no program ever fit.
  - A, with `hypotheses_labels.md` (the same grammar text plus a few more lines on how to answer), solved this
    episode in 2 calls.

Spend logged: $40.20 of $45.77 funded; **about $0.57 left above the $5 reserve**.

## B with A's proposal call available (live, 2026-10-17)

Run `cal-1532dedb366c7408-20261017T104126` (manifest `1532dedb366c7408`, B only, beyond episode, cap $0.40).
**Spent $0.244**; the run stopped at the dollar cap after 7 calls (scored `budget_stop`, not an outcome).
- **B never used the drafted proposals.** Every time it chose `propose`, it also wrote its own `rules_text`, so A's
  proposal call never ran.
- 4 of its 6 rules did not parse, all because of `&&`, which the prompt explicitly forbids. The other 2 parsed but
  contradicted the demonstrations.
- The cap check reserves $0.20 per call, so a $0.40 cap allows only about $0.20 of actual spend.

So far, across 5 B episodes (all on the same model), B committed a correct rule once (catalogue, option protocol).
The remaining blocker is that it writes its own rules and writes them badly. The next design would make `propose` always
use A's proposal call, with B choosing only when to propose. That needs about $0.50 of cap for one episode ($0.30 of
spend plus the $0.20 per-call reservation).

Spend logged: $40.44 of $45.77 funded; **about $0.33 left above the $5 reserve**.

## B with propose always running A's proposal call (live, 2026-10-17) — B is viable

Run `cal-06215ff627e60f06-20261017T113625` (manifest `06215ff627e60f06`, B only, catalogue and beyond, cap $1.00).
**Spent $0.277.**

| Episode | B | A (calibration) |
|---|---|---|
| catalogue | **correct_complete**, 4 calls, $0.133 | correct_complete, 2 calls, $0.066 |
| beyond catalogue | **correct_complete**, 4 calls, $0.144 | correct_complete, 2 calls, $0.118 |

- B now drives the protocol: propose → propose → preview on 3 documents (all approved) → commit.
- B committed while 3 proposed programs still fit the evidence, without asking a question. That is exactly the
  free-agent behaviour A's question policy is to be compared against; here the previewed choice was right on the
  fresh documents.
- **The frozen B design** for the funded tier:
  - the option protocol;
  - `propose` = A's proposal call;
  - B's own choice of questions, previews and stopping;
  - corrections on the shared executor.
- Cost per episode is about $0.14 for B and about $0.09 for A, on these two strata. The inconsistent, unsupported and
  sequential episodes have not been run live yet; nor have the correction calls.

Spend logged: $40.72 total.

## Calibration 2: inconsistent, unsupported, sequential (live, 2026-10-17)

Run `cal-7c5ebc6f173f450c-20261017T115319` (manifest `7c5ebc6f173f450c`, A and B, frozen B design, cap $2.50).
**Spent $1.070.** The laptop slept with the lid closed from 12:04 to 12:36. The call in flight timed out by itself
after wake, and the run continued.

| Episode | A | B |
|---|---|---|
| inconsistent | appropriate_refusal ("no acceptable program"), 2 calls, $0.135 | appropriate_refusal, but only by exhausting its 8 attempts; 5 turns, $0.481 |
| unsupported (forced overlap) | **wrong_commit**, 2 calls, $0.106 | **wrong_commit**, 3 calls, $0.076 |
| sequential (compatible, tall nodes → below) | acquired; correction abstained ("no acceptable interpretation"), 4 calls, $0.145 | acquired; correction abstained, 5 calls, $0.127 |

Findings:
1. **The correction cycle runs end to end live, and the teacher scores by meaning.** The intended scope was
   "nodes at least as tall as they are wide" (`object(o.attached).w <= object(o.attached).h`).
   - Both systems proposed selectors keyed to exact sizes seen in the one corrected document, e.g.
     `object(o.attached).h == 80` and `... w <= 70 and ... h == 80`.
   - On the diagnostic grid these differ from the intended scope, so the teacher answered `none`. Both then correctly
     left the active version unchanged; nothing wrong was committed.
   - Correction success here is 0/2 for both systems, and the shared scope proposer is the weak point.
   - Selectors that compare with constants are not filtered the way learning rules are. That is a candidate fix,
     applied to both systems alike, before the funded tier.
2. **Forced overlap is committed by both systems on the live model too**, as in the offline dry run. It is the known
   product gap: no system refuses to apply a demonstrated overlap.
3. **The refusals differ in kind.** A abstains because no program fits both contradictory demonstrations. B reaches
   the same score by running out of attempts, which is expensive ($0.48) and is not a surfaced conflict. The scoring
   cannot tell these apart, and the report should.
4. **Cost per episode on these strata:** A about $0.13, B about $0.23.

Spend logged after calibration 2: about $41.79.

## Plan 6 re-check (live, 2026-10-17)

Run `cal-166bc623e6dd2953-20261017T170822` (manifest `166bc623e6dd2953`, A and B, dev episodes: forced overlap, tall-nodes
correction, warning-labels correction). **Spent $0.869**, 2 workers, under `caffeinate -is`. Battery v2.5, score v2.2.

| Episode | A | B |
|---|---|---|
| forced overlap | **appropriate_refusal** (`refused_layout`), 2 calls, $0.074 | error: used all 8 attempts, never previewed, $0.208 |
| sequential, tall nodes → below | acquired; correction abstained, $0.162 | acquired; correction abstained ("rejected all scopes"), $0.176 |
| sequential, warnings → below | acquired; correction abstained, $0.118 | **correct_complete, correction activated and scored successful**, $0.131 |

Findings:
1. **The layout refusal works on the live model** (A). B did not benefit: it only meets the refusal at `commit`,
   which it never reached. Fixed after the run: B is now told which programs would be refused (`layout_problem`) and is
   not offered their preview or commit.
2. **Scope selectors are now relational**, as intended: none compared geometry with constants.
3. **The first live correction success** came from B's own correction cycle on the warnings episode.
4. **Why A's warning-labels correction failed** (offline replay of its stored candidates): `o.role == "warning"` was
   proposed, but its rule rewrote labels outside the scope (unexplained diff), so it was never shown. The other
   candidates failed to run on the corrected document. Fixed after the run (not yet run live): the shared scope
   proposer now asks for only the movement for the selected labels (`patch_text`) and composes
   *saved program, then the patch for the selector's labels*, so nothing outside the scope can change. Both A and B
   use this proposer.
5. **Tall nodes:** both systems proposed `role == "note" and w < h` variants, narrower than the true scope (all labels
   on nodes at least as tall as wide), so the teacher answered `none`. This is the genuine ambiguity of a one-document
   correction; clarification and more questions are the product's answer, within budget.

Spend logged: $42.66 of $95.77 funded; $37.34 spendable (authorized $90, reserve $10).
