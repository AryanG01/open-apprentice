# Video run-of-show (target 2:45, hard limit 3:00)

Everything shown must be real. Label anything recorded or sped up on screen. Do not narrate numbers that are not on screen; the Home and Compare pages are generated from stored results.
Set up first: `DEMO_MODEL_ENABLED=1 DEMO_MODEL_MAX_USD=2 uv run uvicorn open_apprentice.api.app:app --port 8000`, open `http://localhost:8000`, dark mode, window 1440 wide.

| Time | On screen | Say (one idea per line) |
|---|---|---|
| 0:00 | **Home** page, hero + the three cards | "Agents learn layout rules from a single example, and they are often confidently wrong. We built one that asks, proves, and can be re-checked." |
| 0:15 | Scroll to **What we measured**: 15 of 34 (44%) wrong | "This is our own measurement of an open model teaching itself these rules: 44% of what it committed to was wrong, even after asking. We show it, not hide it." |
| 0:30 | **Try it live**, pick **NVIDIA Nemotron**, Start | "Nemotron proposes candidate rules. The meter is real: tokens, cost, and a hard cap." (let the timer run; cut the wait, say "sped up") |
| 0:50 | The question: outcomes A / B / Neither | "Several rules fit the example. A solver found the input where they disagree. You answer by picture. Neither is always allowed." |
| 1:05 | Rule sealed, hash shown | "Your answer seals the rule with a hash. Nothing downstream may change it." |
| 1:15 | Run on Konva, then Fabric | "Same rule, two graphics engines. The independent verifier recomputes the result from raw engine state." |
| 1:35 | Tick **Silently change the tool**, Run: mismatch; (if it fails) **Repair** | "Fabric silently changes behaviour. We reproduce the mismatch with numbers. Only the native procedure is repaired; the rule hash is byte-identical. If the model's procedure measures and corrects, it simply survives, and we say so." |
| 2:00 | **Try to break it** | "40 generated inputs on the real engine: boundaries first. This is sampling, not a proof, and the page says so." |
| 2:15 | **Download editable SVG**, then **Re-check this package offline**; then change one number in the JSON and re-check: FAIL | "Don't trust us: re-derive the hashes and geometry offline with no engine and no model. Edit one byte and it fails." |
| 2:35 | **Compare** tab, audit experiment | "We also tested whether asking harder fixes it. It did not. That negative result is in the repo." |
| 2:50 | Home | "Open Apprentice: teach once, ask only when unsure, repair only the tool, prove it offline." |

## Shots to avoid
- Any claim that the method beats the baselines (it does not, and the pilots are small, development-split).
- Showing `.env`, terminals with keys, or the Nebius console.
- Reference-mode runs described as "the model". Reference mode uses no model.
