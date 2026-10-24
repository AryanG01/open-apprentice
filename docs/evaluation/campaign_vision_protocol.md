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
