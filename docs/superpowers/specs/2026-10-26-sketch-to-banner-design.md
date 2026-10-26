# Sketch to banner: one pipeline, two doors, one extra source of truth

Status: approved by the owner on 26 Oct 2026 ("go for full build"). Deadline: 30 Oct 10:00 PDT (31 Oct 01:00 SGT).

## Intent

"Adapt a banner" proves a banner is adapted correctly. The owner wants the same tool to also *start* a banner: from a rough
sketch plus the product's own web page. The rule that keeps this on-story: **nothing is generated that cannot be checked.**
Layout intent comes from the sketch, facts come from the page, wording is drafted by Nemotron from those facts only, and every
claim that reaches the banner is grounded in the page text by a deterministic check. The result flows through the existing
pipeline (rebuild as editable layers, adapt to a story card, ask on overflow, independent verifier), plus one new advisory:
does the banner's price match the page?

Non-goals: generating pictures (Token Factory offers no image model; the owner supplies logo and product pictures), a drawing
tool inside the app, anything that makes a claim the page does not make, 3D in the main flow.

## Who does what (shown in the app)

| Job | Who |
|---|---|
| Read the sketch into layers | Nemotron-3.5-Super-VL |
| Fetch the product page | Tavily Extract |
| Lift grounded facts from the page, draft headline options | Nemotron-3-Super |
| Ground every fact and claim in the page text, check glyphs, lengths, numbers | deterministic checks |
| Confirm parts, copy, pictures, colours | the owner |
| Rebuild, adapt, verify; compare price with the page | pipeline, independent verifier, page check |

## Journey

1. Landing offers two doors under the same headline: **Bring a banner** (exists) and **Start from a sketch** (new).
2. Sketch door, step 1: upload a photo or screenshot of a rough wireframe (the browser letterboxes it onto 1280 x 720 white),
   optionally paste a product page address, or press "Use the sample sketch" / "Use the sample page".
3. Step 2 (workbench): the sketch with Nemotron's boxes on the left; on the right, in order: **Copy from your page**
   (facts, each with its source quote; three headline options as radios; price, button, small print prefilled and editable),
   **Your pictures** (one upload slot per picture box; the box refits to the picture's proportions), **Colours** (six
   background presets, one custom), then the part list exactly as in the banner door.
4. "Build my banner" rebuilds the banner as layers (existing confirm path), then the existing story-card flow runs.
5. Result shows the existing 14 checks plus a **Page check** row: price on the banner vs prices on the page (match, mismatch,
   unknown). It is an advisory, never a block.
6. The banner door gets the same optional "Check against your page" field.

## API contract

All under `/api/campaign/workspaces/{wid}`; rate limited like the rest; model and vision use is metered by the workspace ledger.

`POST /sketches` body `{image}` (data URL, PNG or JPEG, exactly 1280 x 720, at most 2 MB). Response is the existing upload
response (`upload_id, origin, language, layers[], problems[], note, model`) so `AdaptUpload` is reused. Stored in
`ws.uploads[uid] = {"image", "kind": "sketch"}`. Confirm is the existing `POST /uploads/{uid}/confirm`; provenance source is
`upload` (verifier: `gold_applies=False`). Vision requests per address per hour: shared with uploads.

`POST /pages` body `{url}`. Response:

```json
{ "page_id": "ab12cd34ef56", "url": "https://...", "title": "Halden H7", "chars": 4210, "origin": "tavily",
  "language": "en",
  "facts": {
    "product_name": {"text": "Halden H7 Headphones", "quote": "..."} ,
    "prices": [{"text": "$159", "amount": "159.00", "currency": "USD", "quote": "Now $159"}],
    "features": [{"text": "40 hour battery", "quote": "..."}],
    "legal": [{"text": "Offer ends 31 Oct 2026", "quote": "..."}] },
  "copy": { "origin": "model", "options": [{"id": "c1", "headline": "Hear only what matters."}],
            "price": "$159", "cta": "Shop now", "legal": "Offer ends 31 Oct 2026", "problems": [] },
  "problems": [], "note": "" }
```

`origin` is `tavily` or `mock`. `copy.origin` is `model` or `template`. Errors are plain sentences: 422 bad address,
429 quota (6 pages per hour per address, 3 pages per workspace), 502 "the page could not be read" (the response says why
when Tavily says why). A page that reads but has no price returns 200 with `facts.prices: []` and a problem sentence.

`POST /page-check` body `{banner_id, page_id}`. Deterministic, no model. Response:

```json
{ "status": "match", "rows": [{"field": "price", "banner": ["$159"], "page": ["$159", "$229"], "ok": true,
                              "detail": "The banner price $159 is on the page."}],
  "notes": [] }
```

`status` is `match` (every banner price amount is on the page, same currency when both state one), `mismatch` (at least one
banner amount is not on the page while the page lists prices), or `unknown` (no price on the banner or none on the page).

## Rules that keep it honest (all deterministic, all tested)

Grounding. A fact is kept only when its `quote` appears in the page text after normalisation (NFKC, casefold, collapse
whitespace, strip markdown punctuation `*_[]()#>`) and its `text` appears inside the quote. Dropped facts are listed in
`problems`. Prices are parsed with `parse_price(text) -> (Decimal, currency) | None` handling `$1,299.00` and `1.299,00 €`.

Copy. Headline options come from Nemotron-3-Super. An option is kept only if: 1 to 90 characters; every digit run appears in
the page text; any currency symbol or code appears in the page text; none of these claim words unless the page has them:
best, number one, #1, guaranteed, free, cheapest, lowest price, proven, miracle, 100%, award-winning, official (and the
German, French, Spanish equivalents: beste, garantiert, gratis, kostenlos, meilleur, garanti, gratuit, mejor, garantizado,
gratis); no URL or e-mail; every character drawable by Liberation Sans. If no option survives, the template option is the
product name itself. The price line is the page's own price text, never generated. The button label comes from a fixed table
per language (en Shop now, de Jetzt kaufen, fr Acheter, es Comprar ahora, it Acquista ora, nl Koop nu, pt Comprar agora; any
other language: Learn more). Small print is the first grounded legal fact (at most 600 characters) or empty (the part is
optional).

Page address. https only, a host with a dot, no userinfo, no IP literal, not localhost or an internal suffix (.local,
.internal, .lan), at most 300 characters, no spaces. Tavily fetches the page; this server never does. The privacy line says
the address is sent to Tavily. Page text is held in memory with the workspace (30 minutes), truncated to 60,000 characters.

Sketch reading. Nemotron-3.5-Super-VL returns role, box (0 to 1000 grid), any legible words, a font-size estimate. Empty words
are expected, so proposal problems ignore empty text; confirm still requires words (typed or from the page copy). The reading
is evaluated with a pre-registered probe on synthetic sketches before any claim (docs/evaluation/campaign_sketch_protocol.md).

## Modules (each workstream owns its files; nobody else edits them)

Pages workstream: `src/open_apprentice/campaign/pages.py` (URL validation, `PageFetcher` protocol, `TavilyFetcher`,
`MockPageFetcher`), `campaign/facts.py`, `campaign/copy.py`, `evaluation/page_check.py` (independent of agent code),
`api/pages.py`, `prompts/campaign_facts.md`, `prompts/campaign_copy.md`, `apps/web/public/samples/halden-h7.html` (the sample
product page, owner-authored, real price and legal line), tests under `tests/unit/campaign/`, `tests/unit/evaluation/`,
`tests/integration/test_campaign_pages.py`. `app.state.page_fetcher` is set in `api/app.py` lifespan from `settings.page_mode`.

Sketch workstream: `campaign/sketch.py`, `prompts/campaign_sketch.md`, `api/sketches.py`, `evaluation/campaign_sketch_eval.py`
(synthetic wobbly wireframe renderer through the real engine's Chromium, scoring, CLI `oa eval campaign-sketch`),
`docs/evaluation/campaign_sketch_protocol.md`, `apps/web/public/samples/sketches/*.png`, the `allow_empty_text` parameter of
`campaign/vision.py:check_layers`, tests.

Web (owner of the conversation): `apps/web/src/*` (Sketch flow in `Adapt.tsx`, `ReadingLoader.tsx` using
`headphones3d.ts`, types), e2e, video, docs, deploy.

## Budget and safety

Paid calls are capped by the owner. Workstreams never call Nemotron live; they use `MockProvider`. One or two Tavily Extract
calls on the sample page are allowed for verifying the real response shape (about 0.2 credit each). Import-linter contracts
must stay green (campaign must not import evaluation; evaluation modules must not import agent code). Python 3.12, black,
type hints, ruff clean, conventional commits are the owner's to make: workstreams do not commit.

## What this is not claiming

No quality claim for sketch reading until the probe has run. No claim that copy is "good", only that every number and brand
term in it is on the page. The page check proves the banner agrees with the page the owner pointed to, not that the page is
right.
