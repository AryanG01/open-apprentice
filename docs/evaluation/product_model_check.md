# Product model check: Nemotron-3-Ultra vs Nemotron-3-Super for live sessions (pre-registered)

**Written 2026-10-19, before any run.** The owner approved about $2–3 of spend (Nebius balance $12.61).

## Question

Which model should the public site use for live sessions? A demo session on 2026-10-18 with Ultra took 5 minutes to reach
its first question and then failed. This check is about the **product**. It is not a re-evaluation: the final results
(`final_results.md`, policy A, Ultra) stay as published.

## Setup (identical for both models)

- **Server and policy:** local server with `DEMO_MODEL_ENABLED=1`, policy `product-1` (`product_policy.md`), and a durable
  live cap of $3.00 in a fresh store.
- **Models:** `nvidia/Nemotron-3-Ultra-550b-a55b` and `nvidia/nemotron-3-super-120b-a12b`, both at `NEBIUS_REASONING_EFFORT=low`
  and `NEBIUS_COMPLETION_CAP=32000`.
- **Documents:** the demonstration is on `library/000-ai-factory-pipeline.drawio`, with every note placed left-aligned 8
  units below its box. The session also gets library documents 001–005.
- **Teacher:** a script, `scripts/live_product_check.py`, plays the person.
  - **Questions:** it picks the alternative whose output matches the intended rule (left-aligned, 8 below) on that
    document. If none matches, it answers "none".
  - **Previews:** it approves a document whose output matches the intended rule and rejects one that does not.
- **Repeats:** 3 sessions per model, run one after another.
- **Outcome of each session:**
  - **success** = committed, and the committed rule places every note of library documents 006–011 exactly as intended;
  - **wrong commit** = committed with any other placement;
  - **no commit** = abstained, failed or cancelled.
- **Time:** wall-clock time from creating the session to its end, excluding the scripted teacher's own time (under 1 s).
- **Cost:** the durable ledger's spend for the session. The ledger prices at the `.env` rates (Ultra's), so it overstates
  Super's cost.

## Decision rule (fixed now)

- **Adopt Super** for live sessions only if all three hold:
  1. at least 2/3 successes;
  2. 0 wrong commits;
  3. a median session time of 120 s or less.
- Otherwise, **keep Ultra**.
- If Ultra also gets fewer than 2/3 successes on this scenario, say so plainly. The video then needs a different
  demonstration, and the product page keeps saying a live run can abstain.

Either way, the results are written to this file, failures included.

## Results (2026-10-19)

Run with `scripts/live_product_check.py`, 3 sessions per model; raw rows in `results/product_model_check/rows.jsonl`.

**Scoring bug, fixed before this verdict.** The script first scored the receipt's `exact` values, which are the geometry
targets, instead of `measured`, the rendered note boxes. On these files the two differ by the notes' fixed 5-unit text
offset, so every commit at first showed as a wrong commit (0/6). I re-scored every stored run from its receipts against the
pre-registered definition and fixed the script. The table below is the corrected score.

| Session | Ended | Unseen diagrams placed as intended | Time | First question | Ledger spend |
|---|---|---|---|---|---|
| ultra-1 | committed | 6/6 | 57.8 s | 20.3 s | $0.066 |
| ultra-2 | committed | 6/6 | 57.7 s | 20.4 s | $0.066 |
| ultra-3 | committed | 6/6 | 45.2 s | 20.3 s | $0.054 |
| super-1 | committed | 6/6 | 22.4 s | 18.2 s | ≤ $0.014 |
| super-2 | committed | 6/6 | 27.3 s | 12.1 s | ≤ $0.018 |
| super-3 | abstained ("unresolved disagreement") | none | 18.3 s | none | ≤ $0.014 |

- **Ultra:** 3/3 successes, 0 wrong commits, median 57.7 s.
- **Super:** 2/3 successes, 0 wrong commits, median 22.4 s. The ledger prices Super at Ultra's rates, so its real cost is
  roughly a third of the figure shown.

**Verdict under the pre-registered rule: Super meets all three conditions (2/3, 0 wrong, median ≤ 120 s), so the rule
says adopt it for live sessions.** On this scenario Ultra is more reliable (3/3) and still about a minute per session. The
5-minute session of 2026-10-18 did not recur: both models reached their first question in about 20 s on this scenario.

This is one scenario with 3 sessions per model, so it is evidence about the demo flow, not about the battery. The
evaluated results stay as published.

Note added in review: the design spec's draft rule asked for Super's success to be at least Ultra's. The rule actually
registered above, committed before the run, asks for at least 2/3. Under the stricter draft, Super (2/3) would not have
beaten Ultra (3/3). We kept the registered rule. On this demo flow Ultra is the more reliable model, and Super is the
faster and cheaper one.
