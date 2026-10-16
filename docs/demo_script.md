# Video run-of-show (target 2:50, hard limit 3:00)

Everything shown must be real. Label anything recorded or sped up on screen. Do not narrate numbers that are not on screen; the Home and Compare pages are generated from stored results.
Numbers on Home were re-checked against the running app on 2026-10-12 (15 of 34 = 44%; audit 4 of 10 = 40%, silent on 30 of 48; hybrid 1 of 20 = 5%; out-of-grammar: search 0 of 12, model 5 of 12 with 2 wrong, hybrid 5 committed and 0 wrong).

## Set up (live Nemotron on Nebius Token Factory)
- `DEMO_MODEL_ENABLED=1 DEMO_MODEL_MAX_USD=1.5 PYTHONPATH=src .venv/bin/python -m uvicorn open_apprentice.api.app:app --port 8000` with your Nebius key in `.env`; open `http://localhost:8000`, window 1440 wide. Dark mode follows the OS setting.
- The hackathon requires running on Nebius Token Factory with an NVIDIA model, so the model segment is **live**: one full story is about 5 Nemotron calls, 36k tokens, about $0.085 and 89 s (measured). Rehearse once, then record. Keep a recorded-run take (Nemotron replay, labelled REPLAY) as a backup if a live call truncates or Nebius is slow; about 10 to 15% of model calls end in a truncation on any given run.
- Before recording: `npm run build:web && npm run test:e2e` passes (10 browser tests, including the Apprentice journey); the badge story below is now under the *Earlier prototype* tab (open `http://localhost:8000/#home`), reload the page once so there is no stale session, check the Nebius balance.
- Do not speed up the story; if you cut, say "cut".

| Time | On screen | Say (one idea per line) |
|---|---|---|
| 0:00 | **Home**, hero | "Agents learn layout rules from a single example, and they are often confidently wrong. We built one that asks, proves, and can be re-checked." |
| 0:15 | Scroll **What we measured, including what did not work** | "Our own measurement of an open model teaching itself these rules: 44% of what it committed to was wrong, even after asking. An extra model round did not fix it. Adding a symbolic search cut it to 5%. And where the search cannot reach, the model is what finds the rule: search alone 0 of 12, the model alone 5 of 12 but with two wrong, the hybrid 5 committed and none wrong. Tiny samples, development split." |
| 0:45 | **Try it live**. NVIDIA Nemotron live on Nebius Token Factory is already selected; Start teaching. The **Model usage LIVE** meter (model, calls, tokens, dollars) stays visible | "Nemotron-3-Ultra, called live on Nebius Token Factory, proposes candidate rules. The meter is real: calls, tokens, dollars, under a hard cap. The graphics engines and the independent verifier are live." |
| 0:55 | First question: outcomes A / B / C / **Neither**, pick A; second question, pick A | "Several rules fit the one example. A solver found an input where they disagree. You answer by picture. Neither is always allowed. In the recording the answers were A then A." |
| 1:10 | **The rule is sealed**, sealed hash in the evidence column | "Your answer seals the rule with a hash. Nothing downstream may change it." |
| 1:15 | **Run** on Konva, then Fabric | "Same rule, two graphics engines. Nemotron wrote the native procedures and each was accepted only after the real-backend checks. The verifier recomputes the result from raw engine state." |
| 1:35 | Click **Watch the story with the free reference learner** (about 20 s), pointing at the repair, hash and stress-test steps (this version uses no model) | "Now the whole story in one click. The tool changes silently underneath and we reproduce the mismatch with numbers. In our live runs Nemotron's own repair attempt has not yet passed the checks, so a labelled scripted fixture repair is promoted, and the page says which. Only the native procedure changes: the rule hash is byte-identical, and 40 generated inputs pass. That is sampling, not a proof." |
| 2:05 | **Download editable SVG**, **Re-check this package offline**: every check passes; then **Check a package file…** with a copy where `verifier_passed` or `native_passed` is changed to false: FAIL | "Don't trust us: re-derive the hashes and geometry offline with no engine and no model. Change one value and it fails." |
| 2:30 | **Compare** tab, the three-arm audit table and the out-of-grammar table | "We also tested whether asking harder fixes it. It did not. That negative result is in the repo." |
| 2:45 | Home | "Open Apprentice: teach once, ask only when unsure, repair only the tool, prove it offline." |

Optional if time allows (cut first): **Real SVG** tab (experimental, no model): "The same learned rule moves a badge in a real SVG file, checked by measuring in the browser."

## Shots and claims to avoid
- Any claim that the method beats the baselines (it does not, and the pilots are small, development-split).
- Calling the replay "live". It is a recording of a real run; the on-screen label says so, and so should the narration. Use it only as a backup take, and say so.
- Calling the repair a model repair. In every live run so far Nemotron's own repair attempt failed the checks and a labelled scripted fixture was promoted (the page says which). Do not claim Nemotron repaired the tool unless a recorded run actually shows it.
- Reference-mode runs described as "the model". Reference mode uses no model.
- Showing `.env`, terminals with keys, or the Nebius console.
- Claims about the public demo beyond what was checked. A live backend runs on Cloud Run (https://open-apprentice-664860383135.us-central1.run.app, verified 2026-10-13): live Nemotron under an in-memory dollar cap that resets on cold start, then the labelled recording. The static Hugging Face Space is an older preview whose "Try it live" and "Real SVG" tabs say they are unavailable. Re-check the URL and the Nebius balance right before recording.
- Phone or other-browser claims: only desktop Chromium was tested.
