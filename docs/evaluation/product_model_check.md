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
