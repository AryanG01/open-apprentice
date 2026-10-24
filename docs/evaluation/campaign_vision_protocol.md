# Reading a banner image with Nemotron VL: protocol (pre-registered 2026-10-24)

Written and committed before any live vision call. Part A is the development probe; Part B (the held-out comparison) is
added in a later commit before its run.

## Question
Can `nvidia/Nemotron-3.5-Super-VL` (text + image in, text out, Nebius Token Factory) read a flat banner image and return its
layers (role, box, words, size, colour) well enough that the owner only needs to correct a few boxes?

## Part A: development probe
- **Input:** the six development banners that carry all six layers (`teach_before`, `short_a`, `short_b`, `de_long_a`,
  `de_long_b`, `fr_long`), rendered to 1280x720 PNG by the real engine. Their authored nodes are the truth. Development
  fixtures, not held out; the prompt (`prompts/campaign_vision.md`) was written before this run and is not changed by it.
- **Run:** once, production settings, one call per banner (plus the one automatic retry if a reply is cut off), run cap $0.15.
- **A layer is "found"** when its box overlaps the true box at IoU ≥ 0.5. **Words exact** = text equal after whitespace
  normalisation.
- **Decision (fixed now):**
  - **go:** every layer found on at least 5 of 6 banners and the median IoU of the text layers is at least 0.6;
  - **partial:** all six roles named once on at least 5 of 6 banners and at least 70% of the words exact, but the boxes fail
    the bar: the product shows the model's roles and words and the owner drags the boxes;
  - **no-go:** otherwise: the editor ships on its manual template and the model is not claimed to read banners.
- **Report:** per-banner table with every IoU, the raw replies kept in the JSON next to the table. Anything decided after
  seeing the results is labelled post hoc.

## Limits stated in advance
Six banners from one author and one brand style, rendered by our own engine in Liberation Sans on flat colours: this tests
the plumbing and the model's basic reading, not real-world banners. It says nothing about photographic backgrounds, other
fonts, or other designers' layouts.

## Addendum, written after run 1 and before run 2 (2026-10-24)
Run 1 (`campaign_vision_dev_run1.md`): decision **partial** as first scored. Two things were found afterwards:
1. **A scoring bug:** the fixtures are not all 1280x720 (three are 1600x900, one 1920x1080) and run 1 compared the model's
   boxes with the authored boxes as if they were. Fixed (boxes are compared in the banner's own frame); the stored replies
   were re-scored with no new call. The registered rule is unchanged and still gives **partial** (median text-layer IoU 0.46).
2. **One banner's reply was cut off twice** at the 4,000-token cap and fell back to the manual template.

Run 2 changes only the vision token cap (4,000 to 8,000). Same model, prompt, banners, rule and cap. Both runs are
reported. A **post hoc** column (share of a text box lying inside its authored frame) is added because the model draws boxes
tight around the visible words while the authored frames are generous; it is not part of the registered decision.

## Addendum 2, written before probe run 3 (2026-10-25)
Live use of the built app showed one failure the probe could not: a product-image box that reached into the headline, so the
picture crop held the first words. Changes made because of it (all outside the probe's scoring):
- the server's overlap rule now also fires when more than 20% of a *text* box lies inside an image box;
- the browser snaps boxes to the content on flat backgrounds (images may grow at most 14 px) and shows the two crops;
- `prompts/campaign_vision.md` gains two sentences: a picture box must not contain words, and boxes must not overlap
  (except the button's words inside the button).

Run 3 re-runs the six development banners with that prompt (same model, rule and cap). If it is not worse than run 2 on the
registered rule, the prompt is **frozen** for the held-out evaluation (Part B); if it is worse, the run 2 prompt is restored
and frozen instead. Whatever happens, all three runs are reported.
