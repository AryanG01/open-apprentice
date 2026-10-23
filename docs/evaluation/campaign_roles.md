# Campaign role mapping: result of the pre-registered comparison

Protocol: `campaign_roles_protocol.md` · set: 24 banners (21 map, 3 abstain), manifest `2555549d0f5b546f…` · model `nvidia/nemotron-3-super-120b-a12b` · 48 calls · $0.075 (ledger)

| arm | exact (of 24) | false confident | corrections (21 map cases) | macro-F1 |
|---|---|---|---|---|
| A: heuristic | 6 | 18 | 41 | 0.803 |
| B: Nemotron, shipped prompt, raw | 17 | 5 | 14 | 0.946 |
| C: shipped hybrid (Nemotron, checker, heuristic fallback) | 14 | 10 | 20 | 0.891 |
| D: Nemotron, strong prompt, may abstain | 18 | 2 | 32 | 0.880 |

- Bar 1 (Nemotron improves role mapping): MET
- Bar 2 (the checker adds safety): NOT MET
- Bar 3 (a better prompt beats the shipped one): MET

## Per banner (✓ exact, ✗ wrong, ! false confident)

| banner | category | A | B | C | D | C used | why C fell back / D abstained |
|---|---|---|---|---|---|---|---|
| absent_role_1 | absent_role | ✓ | ✓ | ✓ | ✓ | heuristic |  is not a layer it was shown; role legal is missing |
| absent_role_2 | absent_role | ✓ | ✓ | ✓ | ✓ | heuristic | role price is missing / D: price |
| absent_role_3 | absent_role | ✓ | ✓ | ✓ | ✓ | heuristic | role cta is missing |
| big_decor_image_1 | big_decor_image | ! | ! | ! | ! | model | - |
| big_decor_image_2 | big_decor_image | ! | ✓ | ✓ | ✗ | model | - / D: brand_mark role not identifiable |
| big_decor_image_3 | big_decor_image | ! | ! | ! | ✓ | model | - |
| big_logo_1 | big_logo | ! | ! | ! | ✓ | model | - |
| big_logo_2 | big_logo | ! | ! | ! | ✗ | model | - / D: brand_mark |
| big_logo_3 | big_logo | ! | ! | ! | ✗ | model | - / D: brand_mark |
| extra_group_1 | extra_group | ! | ✓ | ✓ | ! | model | - |
| extra_group_2 | extra_group | ! | ✓ | ✓ | ✗ | model | - / D: Missing brand_mark layer and unable to distinguish which group is the cta versus |
| extra_group_3 | extra_group | ! | ✓ | ✓ | ✓ | model | - |
| plain_1 | plain | ✓ | ✓ | ✓ | ✓ | model | - |
| plain_2 | plain | ✓ | ✓ | ✓ | ✓ | model | - |
| plain_3 | plain | ✓ | ✓ | ✓ | ✓ | model | - |
| price_emphasis_1 | price_emphasis | ! | ✓ | ! | ✓ | heuristic | text sizes must run headline > price > legal |
| price_emphasis_2 | price_emphasis | ! | ✓ | ! | ✓ | heuristic | text sizes must run headline > price > legal |
| price_emphasis_3 | price_emphasis | ! | ✓ | ! | ✓ | heuristic | price must contain a number and a currency sign; text sizes must run headline > price > legal |
| text_distractors_1 | text_distractors | ! | ✓ | ✓ | ✓ | model | - |
| text_distractors_2 | text_distractors | ! | ✗ | ! | ✓ | heuristic | unknown role ; role  is given to more than one layer |
| text_distractors_3 | text_distractors | ! | ✗ | ! | ✓ | heuristic | unknown role ; role  is given to more than one layer |
| twin_prices_1 | twin_prices | ! | ✓ | ✓ | ✓ | model | - |
| twin_prices_2 | twin_prices | ! | ✓ | ✓ | ✓ | model | - |
| twin_prices_3 | twin_prices | ! | ✓ | ✓ | ✓ | model | - |

## Reading (hand-written after the run, 2026-10-23; everything below is post hoc)

Run once with the production settings (Nemotron-3-Super, reasoning effort low). No re-runs and no changes to the product,
prompts or set after sealing.

- **Bar 1 met: Nemotron beats the heuristic on these harder banners.** The shipped hybrid gets 14 of 24 exactly right
  against the heuristic's 6, with 10 false-confident proposals against 18. On the 3 plain banners every arm is right,
  as in the development tie. The heuristic fails every banner that has an extra layer or breaks its size ordering.
- **Bar 2 not met: the shipped checker makes the hybrid worse than the raw model.** Raw Nemotron gets 17 right with 5
  false-confident; the hybrid gets 14 with 10. The checker rejected 5 answers and fell back to the heuristic, which was
  then wrong on all 5:
  - 3 correct sale-banner answers, because the rule "headline font > price font > legal font" is false for sale
    banners. One of them also used "zł", which the checker's currency list ($ € £ ¥) does not include.
  - 2 text_distractors answers where the model gave the decorative layers the empty role `""`. The other layers were
    right. A checker that ignored empty labels would have accepted both.
- **Bar 3 met: the strong prompt (D) gets 18 right with 2 false-confident.** Its gain is mostly abstaining where the
  input cannot decide the answer (below). Its correction count is the highest (32) because an abstention leaves all
  7 layers for the owner to label.
- **A flaw in the set:** the model sees images only as id, type and box, with no pixels and no asset names. So
  big_decor_image and big_logo (6 banners) ask which of two images is the product with nothing but size and shape to
  go on. Every answer there is a guess. D abstained on 4 of the 6, which is the right behaviour. The set's author
  validated "a careful human reading the layer list could get it right" for text, not for images.
- **Absent roles:** all arms "pass" the 3 abstain banners, but for different reasons. The heuristic and the hybrid
  return an incomplete mapping, and raw B too, because a 7-role mapping is impossible with 6 layers. Only D says why.
  So this category does not tell the arms apart.

**What this supports:** with the same opaque-id input, Nemotron maps roles better than the size heuristic on banners
with distractors, sale prices or twin prices. The shipped deterministic check, as written, throws away some of that
gain. **What it does not support:** anything about images; any claim from people (the set was written by an AI agent of
the same family as the builder, not by the owner or a designer); a product change scored on this same set (a fixed
checker needs a new sealed set).

**Product changes this suggests** (not made; each needs a new set to measure):
- drop the font-size ordering rule;
- widen the currency check;
- treat `""` as unlabeled;
- when the checker rejects the model's answer, show "no confident proposal" instead of quietly falling back to the
  heuristic;
- give the model the image content, or let the owner confirm only the image roles.
