# Open Apprentice

**Teach a layout rule once. It asks when it is unsure, reuses the rule across graphics backends, and repairs only the part that broke.**

You show it one example, such as a badge in a card's top-right corner. Several different rules fit that example equally well, so Open Apprentice
finds an input where they disagree, draws each outcome, and asks you which one you meant. The rule you pick is sealed with a hash. It is then
carried to a second graphics engine (Konva to Fabric) through a checked native procedure. When the tool underneath changes silently, the
mismatch is reproduced with real numbers and **only the native procedure is repaired. Your rule and its hash do not change.**

Built for the Nebius x NVIDIA Global AI Hackathon. Models: NVIDIA Nemotron through Nebius Token Factory (live runs); everything else runs offline.

## Try it (about 2 minutes)

```bash
uv sync                                   # Python deps (Python 3.12+; the venv here is 3.13)
npm ci                                    # JS deps (Node >= 22.12)
npx playwright install chromium           # the engine drives real Konva/Fabric in headless Chromium
npm run build:web                         # builds apps/web
uv run uvicorn open_apprentice.api.app:app --port 8000
```

Open <http://localhost:8000>. No account, no API key and no model call is needed for the interactive demo.

**Optional: let NVIDIA Nemotron drive it.** Put your Nebius key in `.env` (copy `.env.example`), then start the server with
`DEMO_MODEL_ENABLED=1 DEMO_MODEL_MAX_USD=4 uv run uvicorn open_apprentice.api.app:app --port 8000`. In *Try it live*, choose "NVIDIA Nemotron". It is
**off by default** so a public instance can never spend money by accident. Nemotron then proposes the candidate rules, writes the native procedure for each
backend and writes the repair. Every output is checked on the real engine before it is accepted; if it fails, a scripted fixture is used instead and the
interface says so. A live meter shows tokens, calls and estimated dollars, and the server refuses model sessions once the cap is reached.

| Tab | What it is | Source of what you see |
|---|---|---|
| **Try it live** (`/#live`) | Teach the badge rule yourself, reuse it on Konva or Fabric, silently change the tool, reproduce the mismatch, repair, then download the result | Real engines and the independent verifier, run on your clicks. Reference mode: non-model learner and scripted native procedures, **no language model**. Nemotron mode: live and metered (see above). Every response labels which produced what. |
| **Learn / Reuse / Transfer / Challenge** | A recorded, annotated walkthrough of the same story | Recorded from a real offline run; labelled RECORDED |
| **Compare** (`/#compare`) | Stored live-model pilot results against baselines | Rows from real Nemotron runs, development split, with their limits stated first |

**Export:** after a run, *Download editable SVG* gives script-free SVG 1.1 with every object id preserved and the rule hash, backend and
verifier result embedded as metadata. *Evidence package (JSON)* contains the teaching ledger, hashes and observed geometry so a layout can be re-checked
without trusting the interface.

## What is actually true (read this before judging)

We hold ourselves to the claims we can back with a command.

**Works, tested:**
- Concept/binding separation: a sealed concept hash (rule, domain, teaching ledger) that every native binding must carry; promotion with a different hash is refused.
- Independent verifier (recomputes world geometry from raw engine state, never uses the agent-facing measure tool; seeded-fault tests show it rejects broken results).
- Reproduced native mismatch when a tool changes silently while the abstract model still passes, and binding-only repair with retained-case replay (a hard-coded "fix" is rejected).
- Exact-arithmetic rule language, an AST-to-Z3 compiler with property-tested agreement, and typed witness search (`witness_found` / `no_witness_in_model` / `incomplete` / ...).
- Four evidence axes (intent, symbolic, native, held-out) are kept separate everywhere; there is no combined score and no single "Verified" badge.
- 280+ tests, including engine-backed end-to-end tests (`OA_ENGINE_TESTS=1`) and an import-boundary contract that keeps the evaluator out of agent code.

**Measured with a live NVIDIA model, and not flattering:** on development-split pilot runs (Nemotron-3-Ultra via Nebius, a handful of episodes), a
non-model reference solves every task, while every model-based method, including ours, often **commits output from a rule that fit the examples but
was not the intended one**. We report this in the Compare tab and `docs/status.md` instead of hiding it. These are pilot numbers, not the locked study, and
do not support any claim that our method beats the baselines.

**Not built yet:** your own scenes in Challenge mode, a skill inspector, SVG *import* of real documents, entering a corrected example after "Neither".

Every deviation from the specification is recorded in `docs/decisions.md`; the running log of what was tested is `docs/status.md`.

## Commands

```bash
uv run pytest tests/unit tests/contracts tests/evaluation              # offline, no browser
OA_ENGINE_TESTS=1 uv run pytest tests/integration                     # real Konva/Fabric (needs Chromium; run outside restrictive sandboxes)
uv run lint-imports                                                    # trust-boundary contract
uv run python -m open_apprentice.cli doctor                            # shows config without secrets
uv run python -m open_apprentice.cli learn --live --max-usd 3 --episode 0 --episodes 2 --concept both   # live model teaching trials (needs .env)
uv run python -m open_apprentice.cli compare --live --max-usd 5 --episode 3 --episodes 3               # five-method comparison (needs .env)
uv run python -m open_apprentice.cli report --run-dir results/runs/<run>                               # rebuild a report from stored rows
PYTHONPATH=src:. uv run python scripts/build_demo_bundle.py            # regenerate the UI's recorded data (needs Chromium)
```

Live runs read `NEBIUS_API_KEY` from a local `.env` (copy `.env.example`; the file is git-ignored and never printed). Without it everything above that
says "no model" still works, and live commands exit with `BLOCKED_NO_CREDENTIAL` rather than pretending.

## Layout

```
src/open_apprentice/   concepts/ (rules, witness search, teaching)  skills/ (restricted interpreter)  agent/ (policies)
                       providers/ (Nebius, mock)  evaluation/ (independent verifier, episodes, report)  api/ (HTTP + live demo)
services/engine/       Node + Playwright driving real Konva and Fabric in a locked browser
apps/web/              React + TypeScript interface
docs/                  status.md (what works), decisions.md (deviations), provider_feedback.md
```

## License

MIT, see `LICENSE`. Third-party notices: `THIRD_PARTY_NOTICES.md`.
