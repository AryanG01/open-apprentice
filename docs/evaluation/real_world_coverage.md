# Real-world coverage: how many real 16:9 designs have all six parts?

Our own measurement, not user research. Written 25 Oct 2026, before deciding whether parts may be optional.

**Data:** Crello (`cyberagent/crello`, validation split, 1,852 designs) read through the Hugging Face dataset-server API. Licence (CDLA-Permissive-2.0 per the dataset card) is **not yet verified against the LICENSE file**; only metadata (element types and text) was read, no images are copied into the repo.

**Method:** keep designs whose canvas ratio is 1.6 to 1.95 (274 designs). Count by element type and text with simple patterns (a currency sign with a digit = price; terms/valid/apply/copyright/asterisk = small print; a short imperative phrase of 4 words or fewer = button). The patterns are crude, so treat the counts as rough.

| Part present | Designs (of 274) |
|---|---|
| two or more picture elements | 252 |
| two or more text elements | 244 |
| a button-like phrase | 26 (9.5%) |
| a price | 5 (1.8%) |
| small print | 0 |
| **all six parts** | **0** |
| a picture, two texts and a button | 26 |
| a picture and two texts only | 242 |

**Reading:** Crello is general design templates (posters, social posts), not retail ads, so the price and small-print counts understate retail banners. Even so, requiring all six parts would reject nearly every real design we can find online. Our current flow is honest about this in its limits panel, but it is a real completeness ceiling.

**Decision (25 Oct 2026):** price, small print and button are now optional; logo, product image and headline stay required. Every part that is present is checked exactly as before (price needs a number and a currency, small print must be the smallest text, the button is a plate plus words, contrast, glyphs, overlap). Absent parts are handled by:
- the role gate and the editor checks (only the three required parts can be "missing");
- the stacking order, which is re-ranked when a part is absent so the engine never gets an index past the last layer;
- the split option (a second card), which is offered only when there is a price, button or small print to put on it;
- the verifier, where a banner without a button must not gain one.

Tests: `tests/unit/campaign/test_optional_roles.py` (role gates), `tests/integration/test_campaign_api.py` (a banner without each part, and without all three, is adapted and passes every independent check; the split is offered only when card 2 has content) and `tests/e2e/adapt.test.mjs` (remove the parts in the editor and still get a verified card).

## Under the current rule (re-measured 25 Oct 2026, same 274 designs)

The current rule needs a headline (some text) and two pictures (logo and product); price, button and small print are optional.

| By element count in Crello's metadata | Designs (of 274) |
|---|---|
| two or more pictures (photos or vector illustrations) and some text | **252 (92%)** |
| two or more photos (not counting vector illustrations) and some text | 23 (8%) |

**How to read it.** The 92% is an **upper bound**: Crello's vector elements are often decorative art, not a logo or a product. The 8% is a lower bound. The truth is between them, and element counts cannot tell where. We have **not** run the flow on these designs: that would need their preview images, a verified dataset licence and vision calls. Do not read 92% as "the app works on 92% of designs"; read it as "the old six-part rule excluded all of them, and the current rule no longer does for most".
