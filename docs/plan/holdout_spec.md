# Held-out set: 8 new banners (generate once, do not retry, do not show them to the assistant)

Why: the first four banners are now spent (code was changed because of them). These eight decide whether the improvements work on
inputs nobody tuned on. They are run **once**; anything fixed afterwards is a development change and the set is then spent.

## How to generate
Use ChatGPT image generation (or any generator you can legally use), **one call per banner, keep the first output, no retries, no edits.**
Landscape 16:9 (about 1672 x 941), flat PNG, fictional brands, no real logos, no URLs. Save the exact prompt you used next to each image.
Prompt skeleton (change the bracketed parts): *"A flat promotional web banner, 16:9, [BACKGROUND], fictional brand wordmark '[BRAND]' small at [WHERE], one product: [PRODUCT, one object, no text on it], headline '[HEADLINE]', price '[PRICE]', a rounded button '[CTA]', tiny fine print '[LEGAL]'. No other text. Clean modern advertising style."*

| # | Case | Background | Product | Layout |
|---|---|---|---|---|
| H1 | tall narrow product | flat light colour | tall slim bottle or tube | product right, text left |
| H2 | tall narrow product | flat mid colour | tall spray can or tower speaker | product left, text right |
| H3 | soft gradient (out of the flat envelope) | smooth two-colour diagonal gradient | any single product | any |
| H4 | photograph (out of the envelope) | detailed photo scene | any single product | any |
| H5 | long headline (about 90 characters, English) | flat | wide product (sneaker, camera) | text left |
| H6 | long headline in German (about 70 characters) | flat | any | product left |
| H7 | reversed or unusual layout | flat | square product | logo top right, text bottom, product top |
| H8 | stacked centred layout | flat | any | logo top centre, product centred, text and button beneath |

Each banner needs: brand wordmark, headline, price with currency, button text, a fine-print line (all fictional), written down
exactly as they should read (`expected.json`: file, brand, headline, price, cta, legal, case id). Keep `expected.json` and the prompts
outside anything the app sees.

## What I will do with them
Run the frozen app once on each, through the normal upload and editor, with a fixed scripted operator rule written before the run.
Report two numbers: **in-envelope** inputs (H1, H2, H5, H6, H7, H8) that give a clean card by the written checklist, and
**out-of-envelope** inputs (H3, H4) that are refused or labelled correctly before a bad output. Every failure is published.
The checklist (judged at phone size by someone who did not write the change): every approved word present and legible; product whole
and undistorted; no fragment of another element; logo intact; nothing outside the safe area; no accidental overlap; spacing balanced.
