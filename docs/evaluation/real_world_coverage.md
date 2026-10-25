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

**Decision input:** make price, small print and button optional (headline, logo and picture stay required), if the learned layout, the checks and the verifier can skip an absent part without weakening any check.
