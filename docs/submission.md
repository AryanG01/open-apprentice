# Devpost submission: Open Apprentice

Paste-ready text for the fields on https://nebiusglobalaihackathon.devpost.com (rules checked 2026-10-20). Every number below
comes from a file in this repository. The file is named next to the claim so it can be checked before submitting.

- **Track:** Best Apps and Agents
- **Demo:** https://open-apprentice-md76de375q-uc.a.run.app
- **Code:** https://github.com/AryanG01/open-apprentice (public, MIT)
- **Video:** <YouTube link, public, 2:55>

---

## Tagline (one line)

Show an AI how you want your diagrams laid out, once. It asks when it isn't sure, then fixes every diagram you have,
and proves each edit.

## Inspiration

Every team has the same diagrams: architecture maps, process flows, org charts, floor plans. Every team has the same
mess too, with notes drifting around their boxes as people edit. Style rules are easy to show and hard to write down. AI
tools that "just fix it" guess, and a guess applied to a hundred files is a hundred chances to be quietly wrong. We wanted
an apprentice instead of an autopilot. It learns from one example, asks the one question your example leaves open, and
never changes a file it can't prove it changed correctly.

## What it does

1. **Bring your diagrams.** Import real `.drawio` files, or try a sample or the 100-diagram library. The real draw.io
   engine draws each one and measures every box. The apprentice matches each note to its box and you check its guess.
2. **Show it once.** Drag the notes on one diagram to where they belong. Every move is redrawn by the engine.
3. **Watch it think.** NVIDIA Nemotron, called live through Nebius Token Factory, writes small candidate programs that
   could explain your example. Each one is replayed against what you did, and the ones that don't fit are dropped. If
   several still fit, the apprentice does not guess. It searches for a test diagram where those programs disagree, renders
   each outcome, and asks you one question with a picture of each answer. A side panel shows all of this as it happens:
   how many programs were proposed, how many still fit, the test diagram it drew, and which program stands behind each
   option.
4. **Preview, then commit.** The rule is previewed on diagrams you never touched. A diagram where it would break the
   layout is shown as blocked and cannot be approved. Then it is stored as a versioned skill.
5. **Reuse everywhere.** Apply the skill to the whole library in one click, then to a 217-object company platform map.
   Each edit is a byte-exact patch of just the note positions. Before anything is published, the file is re-parsed,
   re-rendered and measured. Three separate checks must pass: the measured positions match the rule, nothing else in
   the file changed, and nothing leaves the page or overlaps. Each result gets its own receipt and a before/after slider,
   and can be downloaded as `.drawio` or SVG.
6. **Correct it.** Nudge a result you dislike. The apprentice asks whether you meant to change the skill, keep a one-off
   override, or undo a mistake, and the skill gets a new version.

It works on any draw.io diagram where text notes annotate shapes: flowcharts, architecture maps, org charts, roadmaps,
network maps and floor plans. It only moves notes; it does not restyle. An earlier prototype, also in the app, applies the
same show, ask and check loop to UI components across two graphics engines (Konva and Fabric).

**A second, newer lane: banner to story card (Campaign tab, development fixtures).** You teach one compound layout
change: a layered 16:9 promo banner (logo, product image, headline, price, button, legal line) becomes a 1080x1920
story card, with every layer moved, resized and restyled. The rule is learned by search from that one example and reused
on other banners by each layer's role, not its coordinates. One example fits two rules for the product photo: it always
fills the same frame, or it scales by the factor the example used. The two agree on the teaching banner, so the
apprentice builds a test banner where they disagree (the same banner with a smaller photo). It renders and verifies both
outcomes and asks you once, before any run. A "show the work" table then lists the learned rule role by role. When a long headline, such as German copy, does not fit,
the apprentice stops and shows two fully rendered outcomes (shrink the product image, or split across two cards). It
saves your answer per language as a versioned preference that you can roll back. The same rule runs in real Konva and
real Fabric, and every result passes an independent verifier before it is shown: 16 of 16 rows pass on both engines.
Nemotron-3-Super has two checked jobs here:
- **Roles:** it proposes layer roles for banners that arrive untagged, and you confirm them. On 6 plain banners it and
  a simple rule of thumb both scored 6 of 6. On 24 harder held-out banners (decoy layers, sale prices, twin prices),
  pre-registered and written by a separate AI agent, the shipped Nemotron proposal was exactly right on 14 against the
  rule of thumb's 6. That run also showed our own checker rejecting correct sale-banner answers. We fixed the checker
  and ran again on a new set of 24: 17 against 7. Images are not part of the model's input, so image roles stay
  guesses, and you confirm every mapping.
- **Wording:** it phrases the overflow question. Its wording is used only if every number in it matches the measured
  facts. Re-measured with every wording recorded: 6 of 6 were factually right. Our check refused one of them because
  Nemotron typed a curly apostrophe ("doesn’t"), which the check misread. We fixed the check. If a wording is refused,
  the built-in wording is shown and the page says so.

Nemotron-written native procedures passed the verifier on both engines, but they closely follow the prompt's template.
Each request can cost about $0.25, so they are switched off in the public demo. Those were public development
fixtures. On a sealed set of 8 new banners in 4 new languages, written by a fresh agent from the written rules only
(not by us), 22 of 22 results pass on both engines, and it asks exactly when it should
(`docs/evaluation/campaign_sealed.md`).

## How we built it

- **NVIDIA Nemotron on Nebius Token Factory:** the reasoning core.
  - **Nemotron-3-Super** (`nvidia/nemotron-3-super-120b-a12b`) runs the live site. A pre-registered check on the demo flow
    adopted it: median sessions took about 22 s, against about 58 s for Ultra, at roughly a tenth of the cost
    (`docs/evaluation/product_model_check.md`).
  - **Nemotron-3-Ultra** (`nvidia/Nemotron-3-Ultra-550b-a55b`) is the model in our frozen evaluation, where serious
    reasoning matters more than speed.
  - Both are called through Token Factory's OpenAI-compatible API, with `reasoning_effort: low` and JSON-mode (`json_object`)
    responses.
- **Safety by construction.**
  - Model output is a program in a tiny exact-arithmetic rule language, run by a sandboxed interpreter. There is no
    `eval` and nothing the model writes is executed as code.
  - An event-sourced teaching log makes every session replayable.
  - The learner is "text-blind": it never sees note text, so it cannot cheat with special cases.
- **Real engines.** A Node and Playwright service drives the real draw.io viewer in a locked, offline headless Chromium.
  Every check measures what was actually rendered, not what we expected.
- **Product.** FastAPI and React on Google Cloud Run, with state in Cloud Storage, long steps through Cloud Tasks
  (OIDC-authenticated), and a durable spending cap shared by every instance.
- **Evaluation.** A frozen battery of 36 held-out episodes × 3 repeats, run live on Ultra. The learner runs in an isolated
  process that cannot read the answers, and an independent scorer grades the results (`docs/evaluation/final_results.md`).

## The hard problems, and what we used to solve them

Each row below runs in the live demo. The papers are the published idea we build on. We name them so you can see where
the design comes from, not to claim we reproduced their results.

| Problem | What we did | Built on | Measured |
|---|---|---|---|
| One example fits many rules. Which one did the user mean? | Keep every candidate rule that reproduces all teaching so far (a sampled version space). Ask the question the candidates disagree on most, scored by the entropy of how they split. A "show the work" panel under each question gives the candidate count, every Z3 pair search and the split sizes (never which rule backs which option, so it cannot steer the answer). | Version spaces (Mitchell, *Generalization as Search*, 1982). Query by committee (Seung, Opper & Sompolinsky, COLT 1992). | Asks on ambiguous examples where the free model asks on none (2/12 vs 0/12, frozen set) |
| One example, two readings (Campaign) | Both readings of the product photo ("same frame" or "scale like the example") are built and checked to reproduce the example exactly. A test banner where they disagree is constructed and both outcomes are rendered and verified; the owner picks once. The gold is written for one reading, so under the other the gold comparison is left out, never counted as passed | Same disagreement-driven questioning, on a constructed input | `campaign/learn.py` `interpretations`, `probe_banner`; API and browser tests |
| Finding the example that tells two rules apart | z3 searches for a concrete input where two surviving rules disagree, under a time and memory budget in a separate, killable process. The witness is re-run concretely before it is shown. "Unknown" is never treated as a pass. | Distinguishing inputs in oracle-guided synthesis (Jha, Gulwani, Seshia & Tiwari, ICSE 2010). The Z3 SMT solver (de Moura & Bjørner, TACAS 2008). | `concepts/witness.py`; five distinct result statuses, all tested |
| Model output must never run as code | Nemotron writes programs in a small JSON rule language. A restricted interpreter with exact fractions runs them. There is no `eval`, and an import-linter contract keeps the evaluator out of agent code. | Programming by example with a domain-specific language (Gulwani, FlashFill, POPL 2011). | 2 import contracts kept; 1,561 tests |
| A model should not grade its own work | An independent verifier re-measures every result: text height from the font file with fontTools, plus copy, image proportions and safe areas. It shares no geometry code with the engine. | Separating generation from verification | Campaign sealed set 22/22 on Konva and Fabric |
| Layer names give the answer away | Nemotron sees layers under hashed opaque ids (L1…Ln), no asset names. A deterministic checker rejects impossible mappings, and the owner confirms. | Pre-registered held-out evaluation | Pre-registered, two runs on new banners written by a separate AI agent: 14/24 then 17/24 for the shipped hybrid against 6/24 and 7/24 for a size heuristic. Run 1 exposed checker bugs; we fixed them and re-ran on a new set |
| Generated wording can invent numbers | Nemotron only words facts the engine measured. A checker refuses any number, element or claim of fit that is not in those facts, and a template is the fallback. | Constrained, fact-checked generation | 6/6 factually right in the re-measurement |
| A public demo spending real money | One durable ledger in Cloud Storage, written with object-generation preconditions so concurrent instances cannot overwrite each other. The diagram lane reserves each call's worst case there before calling. The other lanes check the ledger before each call and record what they spent after it. So every Cloud Run instance shares one cap that survives restarts. Rate limits key on the address Cloud Run appends, so a forged header cannot reset them. | Optimistic concurrency control | Shared $3 cap verified on production |
| Choosing the live model | Same flow on Nemotron-3-Super (120B total, 12B active; hybrid Mamba-2 and attention with LatentMoE, per NVIDIA's technical report) and Nemotron-3-Ultra, compared with a rule set before the run | Pre-registered model choice | Super: about 22 s per session against about 58 s, at roughly a tenth of the cost |

## Challenges we ran into

- **Hidden reasoning tokens count against the completion cap.** Early on, cut-off replies looked like model failures. We
  now record a cut-off reply as an empty round instead of a crash. This is a disclosed product policy
  (`docs/evaluation/product_policy.md`).
- **Being honest about results.**
  - On plain learning, the same model acting freely beats our asking policy: 28/48 against 22/48.
  - Ours is better at refusing conflicting examples (12/12 against 6/12), asks when examples are ambiguous (2/12 against
    0/12), and is cheaper ($0.17 against $0.26 per run).
  - We publish all of it, including a second policy we tried and rejected.
- **The checks earned their keep.** In one recording, our own scripted "user" answered a question wrongly. The skill would
  have put notes inside taller boxes, and the layout check blocked those files instead of publishing them broken.

## Accomplishments we're proud of

- A model that asks the one question that matters, with pictures, instead of guessing.
- 100 out of 100 library diagrams, and a 217-object platform map, fixed by a skill learned from one example. Every edit is
  checked against what the real engine rendered.
- A reproducible, isolated evaluation with its failures published.

## What we learned

Asking is cheap and guessing is expensive. One well-chosen question, backed by a rendered picture, settles what pages of
prompt engineering cannot. Speed matters as much as intelligence in a live product, which is why Super runs the live site
and Ultra does the heavy evaluation.

## What's next

- Restyling as well as moving: colours, fonts, alignment of whole groups.
- More formats (Figma, slides, SVG libraries).
- Teaching on larger documents, and team-wide skill libraries with review and rollback.

## Built with

nvidia-nemotron, nebius-token-factory, python, fastapi, react, typescript, playwright, draw.io, konva, fabric.js, google-cloud-run,
cloud-tasks, cloud-storage, z3, remotion

## Feedback on Nebius Token Factory and NVIDIA models (required field)

What worked well:
- The OpenAI-compatible endpoint worked with an unmodified client. `GET /models` lists the exact model ids, and every
  response echoes the id.
- `response_format` with `json_schema` (`strict: true`) returned valid JSON once the token budget was large enough.
- `usage` includes `reasoning_tokens` and prompt-cache hit/miss counts, which made precise cost accounting possible.
- `reasoning_effort` (`none`/`low`) clearly changes hidden reasoning spend, from 23 to 7 to 0 tokens on a small task.
- Nemotron-3-Super is fast enough for an interactive product. It reached the first question in about 20 s and finished a
  full live teaching session in about 25 s.

What would help:
1. **Truncation from hidden reasoning is the biggest pitfall.** Reasoning tokens count against `max_tokens`. With a small
   cap a request returns zero visible text and `finish_reason: "length"`. Some Ultra replies to our rule-writing prompts
   hit our 32k completion cap inside hidden reasoning, ending 10 of our evaluation runs. Ideas:
   - a separate budget for reasoning versus visible output;
   - a distinct finish reason when the cap is hit inside reasoning;
   - a warning in the docs.
2. **Docs:**
   - The chat-completion reference lists `json_schema` in the enum but says in prose that only `json_object` and `text`
     are supported. In practice `json_schema` works.
   - `seed` is accepted but undocumented.
   - Prices and numeric rate limits are not on the reference page.
3. **Latency:** a long Ultra reasoning reply can take minutes. Streaming the reasoning progress, or an estimated time
   budget per request, would let apps show meaningful progress.
4. **Billing visibility:** an API view of spend per key or per day would let apps enforce caps against the real balance.
   We keep our own durable ledger, and it ran about 11% below the real spend on the dashboard because of our rate assumptions.

## Testing instructions (for judges)

Open the demo URL; no login is needed.
1. Press **Try a sample: Online order journey** and **Hiring process**, then **Confirm mapping** on each.
2. Under *Show it once*, drag each note under its box, lined up with its left edge.
3. Tick **Use the live model** and press **This whole document is right**.
4. Answer the question, approve the preview, then apply the skill to the other documents. Optionally press **Load the
   100-diagram library**, then **Confirm all**, **Select all** and **Apply**.
5. Optional, the newer lane: open the **Campaign** tab, press **Learn this layout**, then pick a banner. `de_long_a`
   asks the overflow question; choose an outcome or **Neither**. `untagged_short_b` shows Nemotron's role proposal; press
   **Confirm roles and run**.

Live sessions use Nemotron-3-Super under a durable spending cap. If the cap is reached, the page says so and offers the
offline learner. A live run can also stop and say why, for example when your example is ambiguous in a way it cannot
resolve.
