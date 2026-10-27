# Expected content and evaluation brief — not extraction input

Keep this file, expected_content.json and generation prompts outside the Nemotron extraction request. The operator has access to these answers; that is a limitation of this developer-operated evaluation. Save uncorrected model output before using these notes to score or correct it.

## Common target

Turn each supported banner into a readable 1080×1920 story card, or the app's existing explicit two-card alternative when appropriate. Preserve the product identity/picture, fictional wordmark, exact approved wording, currency and amount, CTA and demo disclaimer. Do not invent product capabilities, destinations, prices or offers. Preserve approved copy once across the output contract; brand/background repetition is permitted only where the existing split contract explicitly allows it. No destination URL is supplied.

Readability, visual balance and source fidelity are assessed separately from mechanical checks. The source images are flattened PNGs, not editable source projects. No target coordinates or expected template outputs are supplied, so matching a hand-authored golden composition is not the task.

Text scoring: retain raw strings; normalize Unicode NFC and collapse whitespace introduced by line wrapping for a separate normalized-exact comparison. Preserve case, punctuation, words, decimal values and currency; do not silently lowercase or discard punctuation. Score the wordmark as image/brand preservation where the product treats it as a crop, not as an extra editable headline. All copy below was visually checked in the final generated images.

## banner_01.png — lamp

- Wordmark: `LUMIQ`
- Headline: `Light for your quiet hours.`
- Price: `SGD 89`
- CTA: `SHOP THE LAMP`
- Fine print: `Demo offer. Lamp only.`
- Product: one teal adjustable desk lamp; no model number or other product text.
- Composition: product left, text right, ivory background.
- Intended support: ordinary supported input, pending contract-based preflight.
- Success: all content survives; lamp silhouette and aspect ratio remain intact; the result is readable. Shadows/crop background may expose a reconstruction limitation; record it.

## banner_02.png — bottle

- Wordmark: `ROVENA`
- Headline: `A better bottle for busy days.`
- Price: `SGD 39`
- CTA: `SHOP THE BOTTLE`
- Fine print: `Demo offer. Bottle only.`
- Product: one orange insulated bottle with closed lid, without product lettering.
- Composition: text left, product right, pale sage background.
- Intended support: ordinary supported input, pending contract-based preflight.
- Success: correct role assignment despite reversed arrangement; full bottle preserved without distortion. This is a fresh input, but preference reuse is only demonstrated if its actual conditions make the saved preference applicable.

## banner_03.png — long-copy speaker

- Wordmark: `TUNORA`
- Headline: `Make room for your favourite music, from the first morning coffee to the last quiet moment of the day.`
- Price: `SGD 129`
- CTA: `SHOP THE SPEAKER`
- Fine print: `Demo offer. Speaker only.`
- Product: one navy portable speaker with woven front and a carry loop, no product lettering.
- Composition: product left, long text right, pale blue background.
- Intended support: long-copy case inside the stated text-length envelope, pending preflight.
- Success: every word survives in readable output; if the app cannot satisfy its constraints, it asks or explains the limitation. A particular overflow branch is not guaranteed. Never shorten the headline, shrink below the declared minimum or drop fine print to manufacture success.

## banner_04.png — unsupported photographic background

- Wordmark: `ROVENA`
- Headline: `Take the long way home.`
- Price: `SGD 39`
- CTA: `SHOP THE BOTTLE`
- Fine print: `Demo offer. Bottle only.`
- Product: one orange bottle with a metal/loop cap; different depicted bottle from banner_02.
- Composition: detailed full-bleed forest, stream, rocks and moss; product integrated into the scene.
- Intended support: unsupported for faithful reconstruction by the current simple-background approach.
- Desired handling: explain the limitation/refuse faithful reconstruction, or explicitly obtain approval for a lossy simplified alternative. A green geometry/content check alone must not claim the photographic background was preserved. Record whether detection was automatic, manual or only disclosed in a general limits panel. Do not treat a simplified export as faithful success.

## Cost, time and provenance fields

All source pages and destination links are absent. Do not invent URLs or run a page-fact comparison against a fabricated website. Product prices are fictional scoring strings, not market data. Capture actual usage/cost and timings; the supplied templates contain no measurements. Unsupported handling is a separate outcome, not a successful supported adaptation.
