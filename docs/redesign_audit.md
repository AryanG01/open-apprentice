# Redesign audit (first pass, 2026-10-13)

Source brief: `Open_Apprentice_Redesign_Claude_Code_Handoff.md` (outside the repo). This audit maps it onto the code as found. Nothing here is a result.

## Repository state
- Branch `master`, working tree clean at the start of this audit, HEAD `ad126cc` (README Live demo + Gym section, handoff rewrite). Not pushed.
- `docs/demo_script.md` line 33 said no live public demo existed; corrected to the verified Cloud Run URL with the cap and fallback caveats.

## What the existing language already covers (verified by reading `concepts/rules.py`)
- Statements `let | if | for_each | emit_target`; expressions with exact rationals; ops `add sub mul div min max lt le gt ge eq ne and or not get len`; `if` and comparisons are enough to write "place right of the anchor; if it leaves the canvas or overlaps an obstacle, place below".
- The symbolic (Z3) compiler rejects variable*variable `mul`; constant * variable is fine. That matches the handoff's section 7.5 restriction.
- Limits today: `MAX_STATEMENTS=64`, `MAX_DEPTH=4`, **`MAX_OBJECTS=8`** (handoff wants 32 active / 16 movable), `MAX_EXPR_NODES=500`.
- Objects carry only `{id,x,y,w,h}`. **No `role` or `attachedTo`**, so a rule cannot select by role or read a confirmed association. This is the one real language gap for the scope intention.
- `skills/interpreter.py` (restricted JSON-AST for engine procedures) is separate and stays untouched; the learned edit program is a `rules.py` rule, not an engine binding.

## What the enumerator covers (`concepts/enumerative.py`)
- Two hard-coded families only: badge (corner x margin expression of card width) and gap (equal edge gap or centre pitch). `max_candidates=4`, `SEARCH_LIMIT=200_000`.
- A relative-placement-with-fallback task is entirely **outside** its grammar. So "search alone 0 of N" on such tasks is a coverage fact, not evidence about symbolic methods in general (handoff 17.2).
- Consequence: for the new task family the fair symbolic reference needs its own small enumerated family, or it is reported as "no reference possible within the declared grammar".

## Teaching loop (`concepts/teaching.py`, `hypotheses.py`, `hybrid.py`)
- `MAX_QUERIES=2`, `MAX_ROUNDS=2`, `MAX_CANDIDATES=4`; filter is `hypotheses.fits` (tolerance 1/2) on every constraint. The model prompt is `prompts/hypotheses.md`; it is written around the badge and gap families and needs a generalised version.
- Questions come from `query_selection.py` and `witness.py` (rlimit-bounded Z3). Handoff 9.1 wants batch-first selection on real documents; today it is synthetic witnesses only.

## Provider
- Config default `NEBIUS_MODEL=nvidia/nemotron-3-super-120b-a12b`; the live demo overrides to `nvidia/Nemotron-3-Ultra-550b-a55b`. Identity mismatch is checked in `providers/base.py`.
- Measured cost (earlier runs): about $0.085 per full demo story, about $0.08 per Gym task at configured rates; input-heavy tool use is over-estimated by configured rates. Compound-program prompts are larger, so cost must be re-measured, not extrapolated.

## Not yet audited
- Checker independence on the new task family (`evaluation/verifier.py` vs engine geometry), SVG round-trip support, and whether the `calibrated` scripted policy reads labels unavailable to an agent (`asking_baselines.py` uses `env.fitting_candidates()` and the environment's probes: treat as oracle-assisted until checked).

## Planned three-day experiment (offline parts first)
1. Extend object records with `role` and `attached_to`; raise `MAX_OBJECTS` after measuring Z3 cost at 16.
2. Task generator `label_placement` with three hidden intents kept evaluator-side: relative placement, conditional fallback, scope exception. Fresh layouts vary object count, arrangement, obstacles.
3. Generalise the proposal prompt; run the hybrid learner on development episodes with the mock/replay provider first.
4. Hand-calculated conditional tests (both sides of the overlap threshold) and a protected-object mutation test.
5. Calibration run on live Nemotron after the spending cap is confirmed: 5 episodes, capped, to price the workload before any larger batch.
