# Stage A scoring: raw extraction of the four originals (first attempt, 27 Oct 2026)

Scored **after** `stage_a/` and `calls_stage_a.jsonl` were committed (commit "eval(fresh): stage A ..."). Model:
`nvidia/Nemotron-3.5-Super-VL`, 4 calls, 1,515 prompt tokens each, about $0.0125 in total at the assumed list price. Overlays of
the raw returned boxes on the app's resized image: `stage_a/*.raw_overlay.png`. Box judgement is by eye (a returned box
"on target" if it covers at least about 70% of its element and little else); there are no annotated boxes. The judge is the assistant that built the product.

| Image | Role set | Text exact (NFC, whitespace collapsed) | Boxes on target | Misplaced |
|---|---|---|---|---|
| banner_01 | 6/6 | 4/4 (headline, price, button, small print) | 6/6 | none |
| banner_02 | 6/6 | 4/4 | 6/6 | none |
| banner_03 (long copy) | 6/6 | 4/4 (all 101 headline characters) | 3/6 | price, button and small print boxes sit on the headline's last lines; the headline box ends a line short |
| banner_04 (forest) | 6/6 | 4/4 | 5/6 | headline box covers about the first line of two |
| **All** | **24/24** | **16/16** | **20/24 (0.83)** | 4 boxes |

Reading: the words and roles were read correctly on all four images, including the long headline and the photographic
background. The model's weakness is box placement when the headline wraps onto many lines: three of the six banner_03 boxes
were moved off their elements. This is the same failure the earlier probes reported (roles right, boxes loose), now seen on
a case the product was not tuned on. **No annotated expected text reached the model.**
