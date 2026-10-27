# Fresh synthetic four-banner evaluation: results of the first attempt (27 Oct 2026)

Fresh **synthetic convenience set** (AI-generated fictional banners, built with knowledge of the product's scope): not a sealed
benchmark, not real-world or user evidence, four rows, no population claim. Protocol frozen before any model call:
`../../fresh_synthetic_protocol.md`. Stage A committed before annotations were read. Operator in Stage B is a **script** applying a
fixed correction rule, so **active human time is not measured**; the manual comparator was **not run**. Visual judgement is the
assistant's (the author of the product): a bias, the exports are saved for the owner to look at.

Model calls and cost (assumed list price; the Nebius dashboard is authoritative): reading `Nemotron-3.5-Super-VL` 4 calls,
$0.0125 in total; question wording `nemotron-3-super-120b-a12b` 3 calls, about $0.0022 in total (banner_03, banner_04, and the
banner_02 second pass). One vision read per image, no second paid read (Stage B replays the logged Stage A reply; the replay
equalled Stage A's editor state on all four).

| | banner_01 lamp | banner_02 bottle | banner_03 speaker (long copy) | banner_04 forest |
|---|---|---|---|---|
| Preflight (app's flat-border detector, before inference) | flat: within contract | flat: within contract | flat: within contract | not flat: outside contract |
| Raw extraction: roles / text exact | 6/6 / 4/4 | 6/6 / 4/4 | 6/6 / 4/4 | 6/6 / 4/4 |
| Raw boxes on target (measured/eye, see scoring) | 6/6 | 5/6 (bottle clipped, 79% covered) | 2/6 (product 61%, price, button, small print on the headline's last lines) | 5/6 (headline covers one of two lines) |
| What the editor did | snapped; no blocker | **snapping grew the headline box up into the logo: editor blocked** ("Logo box overlaps the headline text") | snapped | boxes not snapped (non-flat note) |
| Corrections applied by the script | 0 | 1 box (headline restored to the model's raw box) | 4 boxes (headline, price, button, small print) | 1 box (headline) |
| Question asked | no | yes, after the correction: neither layout fits | yes: headline needs 396 px, frame holds 160; shrink and split both fit | yes: neither layout fits |
| Operator answer (fixed policy) | n/a | neither | split | neither |
| Outcome | story card built | **no story card**: product below the minimum width in both layouts | story card built (two cards), headline kept in full | **no story card**: product below the minimum width in both layouts |
| Mechanical checks | 15/15 | n/a | 15/15 | n/a |
| Exact content preserved in the output | yes | n/a | yes (all 101 headline characters) | n/a |
| Visual review (internal) | **fails**: a stray fragment of the wordmark ("_UMIQ") sits above the lamp: the product rectangle reaches into the logo | n/a | **fails**: the speaker is cut off and a fragment of the wordmark sits on its top edge (product box not corrected); card 2 is sparse | n/a |
| Elapsed (Stage B, scripted, replayed read) | 5 s (live read in Stage A: 12.4 s) | 9 s (+ 120 s wait on the blocked first pass) | 6 s (live read 11.3 s) | 6 s (live read 6.4 s) |

## What this says (and does not)
- **Reading:** on four new images the model named every part and read every word exactly (24/24 roles, 16/16 text), including a
  101-character headline and a photographic background. That part held up.
- **Boxes:** 18/24 on target. They fail when the headline wraps onto many lines (banner_03) and the app's own snapping can make
  things worse (banner_02: it grew the headline into the logo).
- **The checker is green on bad pictures.** Both cards that were built passed 15/15 and are visibly flawed. The checks are
  structural by design (copy, link, logo presence, proportions, safe areas, minimum sizes, overlaps of *placed* layers); they do
  not look inside the cropped pictures. The editor's gate caught text inside a crop but not another picture's fragment.
- **Two of three "intended supported" banners produced no story card**, one because the model's box plus the app's snap blocked it,
  and then, like banner_04, because a tall narrow product (a bottle) cannot reach the minimum product width on a 9:16 card. The
  app said so and built nothing: a documented limit, not a silent bad output, but it means the supported envelope is narrower
  than "flat background". "Intended supported" was never certification.
- **Unsupported image (banner_04):** the app detected a non-flat background only as "boxes are not snapped"; it did **not**
  refuse. It was stopped incidentally by the product-width limit, not by recognising a photograph. Its preview showed a flat olive
  rebuild with no warning. Not a faithful result and not claimed as one.
- **Question behaviour:** banner_03's long headline produced a real overflow question with both outcomes rendered; the operator
  policy chose split. Nothing was shortened.
- **Preference reuse:** not demonstrated on these four (one banner asked once; the others did not trigger comparable branches).
  The reuse sequence is proven separately on purpose-built fixtures (`tests/e2e/adapt_preferences.test.mjs`).

## Product changes made AFTER the first attempt (development, not untouched evaluation)
These were made because of what the four rows showed; none of the four has been re-run, and any rerun would be a **development rerun**.
1. The editor now also blocks a product box that overlaps the logo box ("its crop would contain part of the logo"): would have
   stopped banner_01's stray fragment (and so banner_01 would now need a rectangle that avoids the logo, which for this lamp
   means cutting into its shade: honest outcome, a limit).
2. When the background is not a flat colour, the rebuilt preview caption says it is a simplified version, not a faithful one.
3. The limits panel, README and submission now name: no overlapping logo/product rectangles; tall narrow products fail; the checks do
   not look inside the pictures; boxes are often loose or misplaced when a headline wraps.
Left unchanged on purpose: the split card's sparse second card (changing the built-in split layout would re-baseline the frozen
authored gold and the sealed 22/22), the snapping behaviour that grew banner_02's headline, and the box model itself.

## Files
`stage_a/` raw responses, app-resized PNGs, editor states, overlays, screenshots; `calls_stage_a.jsonl` raw replies and usage;
`stage_b/` first Stage B pass (exports, question and result screenshots, per-case JSON); `stage_b_pass2/` banner_02 after the
headline box correction; `product_box_measurement.json`; `stage_a_scoring.md`.
