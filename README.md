# Open Apprentice

**Drop any banner. Nemotron sees its parts, you fix what it got wrong, and the apprentice turns it into a 9:16 story card, asks before it guesses, and checks every result independently.**

Nemotron-3.5-Super-VL (live, on Nebius Token Factory) looks at a 16:9 banner image and proposes its parts: logo, product image,
headline, and the price, button and small print when the banner has them. You check them in an editor (drag a box, or move it with the
arrow keys; boxes snap to the content they surround). The app rebuilds the banner as editable layers, adapts it to a story card with a
layout rule it learned from one worked example, and, when the copy does not fit (a long German headline), stops and shows two fully
rendered outcomes instead of squeezing. Every result is checked by an independent verifier (copy preserved, link kept, logo kept, image
proportions, safe areas, minimum sizes, text fits, no overlaps) before you see it. The same show, ask and check loop also fixes
`.drawio` diagrams (below).

Built for the Nebius x NVIDIA Global AI Hackathon (track: Best Apps and Agents; submission text in `docs/submission.md`).
Who does what: **Nemotron-3.5-Super-VL** reads the banner; **you** confirm the parts; **deterministic checks and the independent verifier** decide;
**Nemotron-3-Super** words the overflow question. Everything else runs offline.

**What it cannot do yet:** flat or simple backgrounds only; fonts replaced by Liberation Sans; 16:9 input; Latin scripts; logo and product must be
separate pictures; image content is judged only by Nemotron and then you. Reading quality: roles 6/6 and 83% of words exact on 6 development
banners, but boxes only partly accurate (median overlap 0.55), which is why you confirm them
([`docs/evaluation/campaign_vision_dev_run3.md`](docs/evaluation/campaign_vision_dev_run3.md)). Of 274 real 16:9 designs we scanned, none had all six
original parts, so price, button and small print are optional
([`docs/evaluation/real_world_coverage.md`](docs/evaluation/real_world_coverage.md)); that scan is our own measurement, not user research.

## Live demo

**https://open-apprentice-md76de375q-uc.a.run.app** (Google Cloud Run, state in Cloud Storage, long steps through Cloud Tasks).
Video: <YouTube link>. To try it: on the landing page, pick a sample banner (or drop a 16:9 image), check the parts, press
**Looks right: make the story card**, answer the question if it asks, and download the PNG. Your image is sent to Nebius Token Factory to be read
and kept in memory for 30 minutes; at most 10 vision reads per address per hour, under a durable spending cap.

The other lane, **diagrams** (Diagrams tab): press **Try a sample: Online order journey** and **Hiring process**, confirm which box each note describes,
drag the notes on one diagram under their boxes, tick *Use the live model* and press *This whole
document is right*. The apprentice's notebook shows what Nemotron proposed, how many rules still fit, the test diagram it drew and why it asks.
Then apply the skill to **the 100-diagram library** (`docs/corpus/library_provenance.md`) and to **The big one**, a 217-object platform map. Teaching works on pages of up
to 32 objects; a learned skill applies to pages of up to 400 objects and 200 notes. Every session and run states `Model: … · Teacher: …` (and `· Policy: product-1` for live sessions, a
disclosed difference from the evaluated policy: `docs/evaluation/product_policy.md`). Live use runs under a **durable** dollar cap
(`DEMO_MODEL_MAX_USD`, shared by all instances and surviving restarts) and 3 live sessions per visitor per hour. When the cap is reached the page says so
and offers the offline learner; it never silently downgrades. The first request after idle can take a few seconds.

The **Campaign** tab shows the learned rule, the teaching question and the other development banners; Nemotron-written
procedures are off in production (`CAMPAIGN_MODEL_PROCEDURES` unset).

## How well does it work? (read before judging)

Frozen, pre-registered battery (36 synthetic label-placement episodes, 3 repeats, live Nemotron, 240 runs, $41.4 in our ledger, about $47 of real model spend), scored by an
independent oracle on documents the learner never saw. The learner runs in an isolated process that cannot read the private manifests
(0 boundary violations). Full tables, intervals and failure analysis: [`docs/evaluation/final_results.md`](docs/evaluation/final_results.md).

| Question | Apprentice (A) | Same model acting freely (B) |
|---|---|---|
| Learns the rule (16 episodes x 3) | 22/48 | 28/48 |
| Corrects a wrong result end to end (12 x 3) | 18/36 | 22/36 |
| Refuses when the task is inconsistent or unsupported | **18/24** | 9/24 |
| Surfaces a conflicting demonstration | **12/12** | 6/12 |
| Ambiguous demonstrations (must ask) | **2/12** | 0/12 |
| Identifiable rules (no question needed) | 7/12 | **12/12** |
| Cost per run | **$0.17** | $0.26 |
| Wrong commits (of 108 runs each) | 3 | 3 |

**What this says, honestly.**
- The hypothesis that the asking policy beats the same model acting freely is **not supported**: both primary endpoints point to B and neither differs from zero.
- The apprentice wins where stopping matters (conflicting or unsupported demonstrations, ambiguous ones, cost). It loses on easy identifiable rules because it gives up after its
  proposal rounds where B just proposes again. 94.5% of the programs it committed were correct on fresh documents, so it is not safer per commit, only more willing to abstain.
- A second policy (v2: more revision rounds) was tried with a rule fixed in advance on the development split, did not meet it, and was **not adopted** ([`docs/evaluation/policy_v2_dev_check.md`](docs/evaluation/policy_v2_dev_check.md)).
- Scope: one synthetic task family (label placement), one model, small n. The 3 real-file episodes could not be run (the product's adapter refuses the frozen file), so there is no
  held-out real-file generalisation result. The live product can and does abstain.
- The four evidence axes (intent, symbolic, native, held-out) are reported separately everywhere; there is no combined score or single "Verified" badge.

## Run it locally

```bash
uv sync                                   # Python 3.12 (the project and image target 3.12)
npm ci && npx playwright install chromium # the engine renders real draw.io in a locked headless Chromium
npm run build:web
uv run uvicorn open_apprentice.api.app:app --port 8000     # http://localhost:8000
```

No key is needed: without `DEMO_MODEL_ENABLED=1` the offline learner is used and nothing is spent. For the live model copy `.env.example` to `.env`, add `NEBIUS_API_KEY`,
and start with `DEMO_MODEL_ENABLED=1 DEMO_MODEL_MAX_USD=5`. Deployment, rollback and cost controls: `docs/deploy.md`, `docs/HANDOFF.md`.

```bash
uv run pytest tests/unit tests/integration tests/contracts tests/evaluation   # OA_ENGINE_TESTS=1 for the real-engine tests
uv run lint-imports                                                           # the agent never imports the evaluator
npm test -w services/engine && npm run build:web && npm run test:e2e          # browser journeys (real Chromium)
uv run oa eval report --help                                                  # rebuild the evaluation report from stored rows
```

## Campaign lane: banner to story card (development, Konva and Fabric)

The "Campaign" tab teaches a compound layout change once: a layered 16:9 promo banner (logo, product image, headline, price,
CTA, legal line) becomes a 1080x1920 story card. Reused on other banners by role, not by coordinates. When the copy does not
fit, it stops and shows two **built-in** outcomes, already applied (shrink the product image, or split across two cards), and
saves your choice per language. Every result it applies passes an independent verifier (exact copy, link, logo, image
aspect, safe areas, minimum sizes, text fit measured from the font tables, and the authored expected output) first.

What is and is not shown:
- The layout is learned by search from one example, and the two overflow outcomes are fixed reference procedures,
  labelled as such. NVIDIA Nemotron-3-Super (Nebius Token Factory) does three checked jobs here (the third is off in the public demo), each with a labelled
  fallback: it proposes roles for banners that arrive untagged (the owner confirms them), words the overflow question
  (used only if every number and element matches the measured facts), and writes the native procedure for Konva and
  Fabric (used only if the independent verifier passes it on a seen banner and two unseen ones). Latest live
  measurement ([`docs/evaluation/campaign_nemotron.md`](docs/evaluation/campaign_nemotron.md), run 4 of 4 on
  development fixtures): roles 6 of 6 with opaque layer ids (a simple heuristic also gets 6 of 6, so no gain is
  shown there; on pre-registered sets of harder agent-authored banners the shipped hybrid gets 14 of 24 against the
  heuristic's 6, then 17 of 24 against 7 after fixing a checker that rejected correct sale-banner answers:
  [`campaign_roles.md`](docs/evaluation/campaign_roles.md), [`campaign_roles_v2.md`](docs/evaluation/campaign_roles_v2.md)); explanations 0 of 3 accepted in that run (wording not recorded), then 6 of 6 factually right and 5 of 6 accepted when re-measured with recording, the refusal being our checker misreading a curly apostrophe (fixed); procedures accepted on
  both engines (first and second attempt), but they follow the prompt's input contract almost verbatim, so this shows
  contract-following, not procedure design. A procedure request can cost about $0.25 because the model's reasoning is
  not bounded by its token limit.
- The same learned rule runs on real Konva and real Fabric through the same restricted procedure:
  [`docs/evaluation/campaign_parity.md`](docs/evaluation/campaign_parity.md) (16 of 16 verifier rows pass).
- Those are **public development fixtures, not held out**. A private sealed set was then written by a fresh agent from
  the written rules only (not by the owner), and its hashes were committed before the run. On it, **22 of 22 rows pass
  on both engines**, and the question was asked exactly when it should be (16 of 16 cases): 8 banners in 4 new locales
  ([`docs/evaluation/campaign_sealed.md`](docs/evaluation/campaign_sealed.md), with its limits).

## Earlier work in this repository

The sections below describe the earlier badge/Konva-Fabric prototype, the NeMo Gym environment and the label-program research line. They are still true of the code
they describe but are not the current product.

## Also in this repository: a NeMo Gym environment

`gym/` packages a *calibrated asking* task as a [NeMo Gym](https://docs.nvidia.com/nemo/gym) environment: an agent sees one demonstration of a hidden layout rule, may ask a teacher for the true outcome on a few new inputs, then commits a
rule or abstains. It is scored by exact evaluation on held-out scenes (no LLM judge) on separate reward components, and the environment itself decides when a question was needed. Results so far are a small development-split pilot
(scripted policies, and Nemotron-3-Ultra on 13 of 24 tasks); see `docs/decisions.md` #53 to #55 and `gym/README.md`.

## Research result: teaching compound conditional edit programs (label placement; not yet in the live demo)

A second line of work asks whether the same teach-ask-commit loop can learn a *compound* program, not one rule: place an attached label to the right of its box, move it below when that spot is blocked or off-canvas, and
leave warning labels alone. Nemotron-3-Ultra (live, Nebius Token Factory) proposes programs in a small exact-arithmetic language; an independent oracle and checker (intent, preservation and layout kept separate) judge them on documents the learner never saw.
Everything here is one model, small samples and single runs; the full evidence, every failure and every retraction are in `docs/redesign_gate.md`, `docs/claims_and_limitations.md` and `docs/PROJECT_RECORD.md`.

- **Frozen gate set (15 episodes: relative, conditional, scope; 5 fresh layouts each):** the apprentice got 15/15 in two assembled runs with no wrong commits. A same-model agent given the same evidence, tools and language help got conditional 2/5 and 1/5 in two valid runs (no wrong commits in the last).
- **Held-out split (24 episodes, never tuned on, one run):** 8/8 unambiguous, 8/8 ambiguous (asked, then committed). Unsupported: 2 correct abstains and 2 provider errors. Noisy demonstrations: 3 correct abstains and **1 wrong commit**; fitting a displaced demonstration with a special case is an unsolved failure.
- **Real SVG files:** learned rules are applied as byte-exact patches of label `x`/`y` only (0 unrelated bytes changed). 52/52 on five authored fixtures in the last run, but that run followed fixes made after seeing a failure on those same fixtures, so it is not independent evidence; label boxes are estimated from font size, not measured in a browser.
- **Not shown:** external user reactions, other models or task families, a held-out run of the baseline.

```bash
uv run python scripts/run_label_experiment.py --mode mock --system reference --split gate --run-id gate-mock   # free, oracle-assisted reference (a ceiling, not a result)
uv run python scripts/run_realfile_check.py --reference --run-id realfile-ref                                  # free, same for SVG files
uv run python scripts/run_label_experiment.py --mode live --system apprentice,agent --split gate --cap-usd 6 --run-id gate-N   # live, needs .env; costs about $3
```

## Try it (about 2 minutes)

```bash
uv sync                                   # Python deps (Python 3.12+; the venv here is 3.13)
npm ci                                    # JS deps (Node >= 22.12)
npx playwright install chromium           # the engine drives real Konva/Fabric in headless Chromium
npm run build:web                         # builds apps/web
uv run uvicorn open_apprentice.api.app:app --port 8000
```

Open <http://localhost:8000>. No account, no API key and no model call is needed for the interactive demo.

**Apprentice tab (the new flow, on real `.drawio` files).** Add two or more `.drawio` files, confirm which node each label
describes, drag labels on one document (or type their x/y; arrow keys nudge 1, Shift 10, Alt 1/64), wait for the engine's
render and press *This whole document is right*. Answer the questions on rendered alternatives, approve the preview (documents
that would break the layout are shown as blocked and cannot be approved), then apply the skill to other documents and download
the `.drawio`, SVG or receipt, or correct a result. Without `DEMO_MODEL_ENABLED=1` it uses an offline learner and spends nothing;
every session and run shows `Model: … · Teacher: …`. The earlier badge demo is under *Earlier prototype*, unchanged.

**Live NVIDIA Nemotron on Nebius Token Factory (the intended public configuration).** Put your Nebius key in `.env` (copy `.env.example`), then start the server with
`DEMO_MODEL_ENABLED=1 DEMO_MODEL_MAX_USD=1.5 uv run uvicorn open_apprentice.api.app:app --port 8000`. *Try it live* then defaults to **Nemotron-3-Super called live through Nebius Token Factory**: it proposes candidate rules
(unioned with a bounded symbolic search so a rule the model omits can still be found; the teacher alone decides), writes the native procedure for each backend and attempts the repair. Every output is checked on the real engine before it is accepted;
if a model procedure or repair fails, a scripted fixture is used instead and the interface says so (in a real run Nemotron's own repair attempt failed the checks and a labelled fixture repair was promoted). A live meter shows tokens, calls and estimated dollars.
Measured: one full session (teach, Konva, Fabric, tool change, repair, stress test) is about 5 model calls, 36k tokens and **$0.085** (89 s). Safety: model mode is **off unless `DEMO_MODEL_ENABLED=1`**, a global dollar cap refuses new sessions
(never silently downgrades), each session is capped at 120k tokens and 24 calls, and each visitor gets 3 live sessions per hour. When the budget is used up the page offers the recorded run, clearly labelled as a recording.

**One-click story.** In *Try it live*, "Watch the story" teaches a badge, reuses the rule on Konva and Fabric, applies the silent tool change, repairs, and stress-tests it in about 20 seconds with the free reference learner; every caption is built from what the server returned. "Watch it with recorded Nemotron" does the same with the replay below (no model call, and no repair, because the recorded procedure survived the tool change).

**Nemotron replay (free, always available when the tape is installed).** `docs/replay/nemotron_tape.json` holds the raw output of one real Nemotron session (recorded 2026-10-12: 3 calls, 32k tokens, about $0.09).
Choosing "Nemotron replay" runs the same teaching loop with that recorded output, against the live engine and verifier, with the model off and no cost. It is labelled REPLAY everywhere. It answers only requests identical to the recorded
ones, so it covers the default badge position (anything else is refused, never improvised; a different teaching answer still matches when it leads to a byte-identical model prompt, and the recorded procedure is then checked live against the rule you taught). It does not show a model repair: in the recorded run the model's procedure survived the silent tool change.

| Tab | What it is | Source of what you see |
|---|---|---|
| **Try it live** (`/#live`) | Teach the badge rule yourself, reuse it on Konva or Fabric, silently change the tool, reproduce the mismatch, repair, then download the result | Real engines and the independent verifier, run on your clicks. Reference mode: non-model learner and scripted native procedures, **no language model**. Nemotron mode: live and metered (see above). Every response labels which produced what. |
| **Real SVG** (`/#svg`, experimental) | Apply the rule you taught to a real SVG: pick one of three owner-authored documents (or check your own), choose card/badge pairs, apply, and get the exact patch, before/after previews, and a browser measurement of every badge | Original bytes edited surgically through a typed, whitelisted patch; rendered world geometry measured in Chromium; **no model** |
| **Learn / Reuse / Transfer / Challenge** | A recorded, annotated walkthrough of the same story | Recorded from a real offline run; labelled RECORDED |
| **Compare** (`/#compare`) | Stored live-model pilot results against baselines | Rows from real Nemotron runs, development split, with their limits stated first |

**Break it:** *Try to break it* runs 40 generated inputs (domain boundaries first, then seeded random sizes and positions) on the real engine, judges each with the
independent verifier, and reports exactly how many passed and the first failures with their numbers. It is bounded sampling, and says so.

**Verify it yourself:** the evidence package is self-contained (rule, domain, hash-chained teaching ledger, native program, observed geometry). *Re-check this package
offline* (or `uv run python -m open_apprentice.cli replay-evidence evidence.json`) recomputes the ledger chain, the sealed concept hash, the program hash and
the rule's exact result with no engine and no model, and checks that the package's own pass/fail claim agrees. Edit one byte of the file and it fails.

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
- 1,500+ tests (1,561 in the unit, integration, contract and evaluation suites), including engine-backed end-to-end tests (`OA_ENGINE_TESTS=1`) and an import-boundary contract that keeps the evaluator out of agent code.

**Measured with a live NVIDIA model (development split, small samples):** the model alone committed to a wrong rule 15 of 34 times (44%); an extra "audit" round did not help; unioning the model's proposals with a
bounded symbolic search cut it to 1 of 20 (5%). A non-model search alone also solves these tasks, so that alone does not show the model adds value. On six rules *outside* the search's grammar it does: search alone got 0 of 12 right, the model alone 5 of 12 (with 2 confident-wrong commits), and the hybrid committed 5 rules, all correct. Tiny samples, development split.

**Earlier pilot, not flattering:** on development-split pilot runs (Nemotron-3-Ultra via Nebius, a handful of episodes), a
non-model reference solves every task, while every model-based method, including ours, often **commits output from a rule that fit the examples but
was not the intended one**. We report this in the Compare tab and `docs/status.md` instead of hiding it. These are pilot numbers, not the locked study, and
do not support any claim that our method beats the baselines.

**Not built yet:** a skill inspector, entering a corrected example after "Neither", model-written SVG patches, and the spec's matched baseline pilot on real assets. The SVG lane edits rectangles by translate-only world geometry; paths, rotation/scale and shared styles are out of scope and reported as such.

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
