# Video run-of-show (target 2:50, hard limit 3:00)

Everything shown must be real. Label anything recorded or sped up on screen. Do not narrate numbers that are not on screen; the Home and Compare pages are generated from stored results.
Numbers on Home were re-checked against the running app on 2026-10-12 (15 of 34 = 44%; audit 4 of 10 = 40%, silent on 30 of 48; hybrid 1 of 20 = 5%; out-of-grammar: search 0 of 12, model 5 of 12 with 2 wrong, hybrid 5 committed and 0 wrong).

## Set up (no keys, no spend)
- `uv run uvicorn open_apprentice.api.app:app --port 8000` (or `PYTHONPATH=src .venv/bin/python -m uvicorn open_apprentice.api.app:app --port 8000`), open `http://localhost:8000`, window 1440 wide. Dark mode follows the OS setting (checked: the story panel and evidence render correctly in dark).
- Do NOT start with `DEMO_MODEL_ENABLED=1` for the take. Nemotron mode spends real credit (about $0.09 to $0.28 per session), 10 to 15% of model calls end in a truncation on any given run, and a first take should not depend on that. The model segment uses **Nemotron replay**, which is a recording of one real run (2026-10-12), costs nothing, and is labelled REPLAY on screen.
- Before recording: `npm run build:web && npm run test:e2e` passes (7 browser tests), reload the page once so there is no stale session.
- Both story buttons take real time (about 17 s for replay, 20 s for the reference learner). Do not speed them up; if you cut, say "cut".

| Time | On screen | Say (one idea per line) |
|---|---|---|
| 0:00 | **Home**, hero | "Agents learn layout rules from a single example, and they are often confidently wrong. We built one that asks, proves, and can be re-checked." |
| 0:15 | Scroll **What we measured, including what did not work** | "Our own measurement of an open model teaching itself these rules: 44% of what it committed to was wrong, even after asking. An extra model round did not fix it. Adding a symbolic search cut it to 5%. And where the search cannot reach, the model is what finds the rule: search alone 0 of 12, the model alone 5 of 12 but with two wrong, the hybrid 5 committed and none wrong. Tiny samples, development split." |
| 0:45 | **Try it live**, choose **Nemotron replay (recorded, free)**, Start teaching. The REPLAY text and, later, the **Model usage REPLAY** meter stay visible | "This is a recording of a real Nemotron run from today: no model is called now. The graphics engines and the independent verifier are live." |
| 0:55 | First question: outcomes A / B / C / **Neither**, pick A; second question, pick A | "Several rules fit the one example. A solver found an input where they disagree. You answer by picture. Neither is always allowed. In the recording the answers were A then A." |
| 1:10 | **The rule is sealed**, sealed hash in the evidence column | "Your answer seals the rule with a hash. Nothing downstream may change it." |
| 1:15 | **Run** on Konva, then Fabric | "Same rule, two graphics engines. The native procedure was written by Nemotron and accepted only after the real-backend checks. The verifier recomputes the result from raw engine state." |
| 1:35 | Switch to **Reference learner (free, no model)**, click **Watch the story** and let it play (about 20 s), pointing at steps 7 to 10 | "Now the free reference learner, no model, with scripted native procedures, to show the repair. The tool changes silently underneath. We reproduce the mismatch with numbers, only the native procedure is repaired, the rule hash is byte-identical, and 40 generated inputs pass. That is sampling, not a proof, and the page says so. In the recorded Nemotron run the model's procedure measured and corrected itself, so it survived with no repair; we do not show a model repair." |
| 2:05 | **Download editable SVG**, **Re-check this package offline**: every check passes; then **Check a package file…** with a copy where `verifier_passed` or `native_passed` is changed to false: FAIL | "Don't trust us: re-derive the hashes and geometry offline with no engine and no model. Change one value and it fails." |
| 2:30 | **Compare** tab, the three-arm audit table and the out-of-grammar table | "We also tested whether asking harder fixes it. It did not. That negative result is in the repo." |
| 2:45 | Home | "Open Apprentice: teach once, ask only when unsure, repair only the tool, prove it offline." |

Optional if time allows (cut first): **Real SVG** tab (experimental, no model): "The same learned rule moves a badge in a real SVG file, checked by measuring in the browser."

## Shots and claims to avoid
- Any claim that the method beats the baselines (it does not, and the pilots are small, development-split).
- Calling the replay "live". It is a recording of a real run; the on-screen label says so, and so should the narration.
- Calling the repair in the story a model repair. It uses the reference learner's **scripted fixtures** (the page says "scripted fixture, not model-generated"). There is no recorded Nemotron repair.
- Reference-mode runs described as "the model". Reference mode uses no model.
- Showing `.env`, terminals with keys, or the Nebius console.
- A claim that a live public demo exists. As of 2026-10-12 only a static preview is deployed (its "Try it live" and "Real SVG" tabs say they are unavailable there); record from the local server unless a verified backend URL exists.
- Phone or other-browser claims: only desktop Chromium was tested.
