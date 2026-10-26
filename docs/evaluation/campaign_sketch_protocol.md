# Reading a rough sketch with Nemotron VL: protocol (pre-registered 2026-10-26)

Written before any live call. **No live run of the sketch reader has happened as of this commit**; the only runs so far use
`MockProvider` (plumbing tests, no claim about Nemotron). The decision rule below is fixed now and is not changed by results.

## Question
Can `nvidia/Nemotron-3.5-Super-VL` (text + image in, text out, Nebius Token Factory) read a rough hand-drawn wireframe of a
16:9 banner (`prompts/campaign_sketch.md`, frozen before the run) into its six layers (`brand_mark`, `product_image`,
`headline`, `price`, `cta`, `legal`) with boxes the owner only needs to nudge? Words are not expected: a sketch carries
scribbles, so the model should return empty text and invent none.

## Part A: development probe (synthetic sketches)
- **Input:** six synthetic wireframes drawn by `evaluation/campaign_sketch_eval.py` from the authored layers of the six
  development fixtures (`teach_before`, `short_a`, `short_b`, `de_long_a`, `de_long_b`, `fr_long`): wobbly seeded-jitter
  boxes, a crossed box for the product, a rounded box with a scribble for the button, zig-zag scribble rows for text
  (rows from text length and font size), a drawn `$` on the price line, dark grey on white, 1280x720. Seed `20261026 + index`.
  Development fixtures, not held out.
- **Run:** once, production settings, one call per sketch (plus the one automatic retry if a reply is cut off), run cap
  **$0.15**, command `oa eval campaign-sketch --live --cap-usd 0.15`. The model never sees the fixture, only the picture.
- **Truth:** the fixture's authored boxes (button: its plate), scaled to 1280x720. The drawn extent differs from these boxes
  (text frames are generous; the pencil rows fill part of them), hence the generous threshold.
- **A layer is "found"** when the model's box and the true box overlap at IoU >= **0.3**. **Roles named** = exactly the six
  roles, each once.
- **Decision (fixed now):**
  - **go:** every layer found on at least **5 of 6** sketches and the median IoU of all layers over all sketches is at
    least **0.5**: the sketch door ships with Nemotron's boxes as the starting point;
  - **partial:** all six roles named once on at least **5 of 6** sketches and median IoU at least **0.3**, but go is not
    met: the door ships, labelled as "roles read, boxes need dragging";
  - **no-go:** otherwise: the door ships on the manual template and the model is not claimed to read sketches.
- **Reported even if it fails:** the per-sketch table with every IoU, the raw replies (JSON next to the table), the cost,
  and which roles failed. Anything decided after seeing results is labelled post hoc. Post hoc, but computed and shown
  anyway: words the model wrote although the sketches carry none (invented words).

## Part B: the owner's real sketches (added later, separate, labelled)
Photos or scans of the owner's own hand-drawn wireframes, added after Part A in a later commit that states the set size,
the same scoring and the same decision thresholds before that run. Reported as its own table; never merged into Part A.
This is the honest test of the feature.

## Limits stated in advance
- The synthetic sketches are **not hand drawn**: they are straight lines with seeded jitter, drawn from our own banner
  layouts, so they are far more regular than a person's pencil. A pass here says the plumbing and basic reading work; it says
  nothing about real handwriting, photographs of paper, other layouts or other designers.
- Six sketches from one layout family; no held-out set in Part A.
- Words are not scored (the sketches have none). Whether the model reads real handwriting is untested here.
- The wireframes contain no colour or font information, so none is scored.
- The verdict is a statement about this model, prompt and these inputs on the day of the run.

## Cost
Cap **$0.15** for Part A, checked by the spend guard before every call; six calls expected, each reading one 1280x720 image
(the banner reader's run 2 measured the same call shape). Nothing else is spent.
