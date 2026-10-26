# Reading real hand-drawn sketches: pre-registered protocol

Written 26 Oct 2026, before any real sketch has been read by the model. Companion to `campaign_sketch_protocol.md`, which covers
synthetic wireframes (result so far: partial, `campaign_sketch_dev_run1.md`).

## Question
Does Nemotron-3.5-Super-VL read a rough, real, hand-drawn banner sketch into the right parts, in the right places?

## Input
The owner's hand-drawn sketches (target 4 to 5; any pen, paper or tablet, photographed or screenshotted; some labelled, some not).
Nothing is selected after seeing results: every sketch the owner sends is run once, in the order received.

## Procedure
1. **Before the model runs**, the sketch's drawn parts are written down from the image alone: which of logo, product picture,
   headline, price, button, small print the drawing contains, and roughly where. This list is committed with the images.
2. Each image is letterboxed to 1280 x 720 as the app does, sent once to the production endpoint with the production prompt
   (`prompts/campaign_sketch.md`), no retries.
3. An overlay of the returned boxes on the sketch is produced by `scripts/sketch_probe_real.mjs` and judged by eye by the person
   running the probe (the assistant), who records, per returned box, **on target** (the box mostly covers the drawn part,
   at least about 70 percent by eye) or **off target**.

## Metrics, per sketch and pooled
- **Role recall:** drawn parts that the model returned with the right role, over drawn parts.
- **Role precision:** returned parts that match a drawn part, over returned parts (an invented part counts against it).
- **Box on target:** returned boxes judged on target, over returned boxes that match a drawn part.

## Decision rule (fixed now)
- **Go:** pooled role recall at least 0.9 and pooled box-on-target at least 0.7.
- **Partial:** pooled role recall at least 0.8, whatever the boxes.
- **No-go:** anything else.

## Caveats stated in advance
The judge of "on target" is the assistant that built the product, by eye: a bias the owner can check from the saved overlays.
A handful of sketches is a sanity check, not a measurement of a population. The owner's drawing style is one style. Words
the model reads from handwriting are not scored; the app uses words from the page or typed by the user.

## Cost
Under $0.05 at the production vision price (about $0.005 per sketch). Spend is within the owner's $5 development cap.

## Reporting
All sketches, overlays, per-box judgements and the decision are published in `campaign_sketch_real_run1.md`, including any that
fail. If the result is partial or no-go, the in-app limits panel and the README keep saying so.
