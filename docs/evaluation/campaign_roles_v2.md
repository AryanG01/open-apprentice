# Campaign role mapping: result of the pre-registered comparison

Protocol: `campaign_roles_protocol.md` · set: 24 banners (21 map, 3 abstain), manifest `1ebb7e8940d269d7…` · model `nvidia/nemotron-3-super-120b-a12b` · 48 calls · $0.072 (ledger)

| arm | exact (of 24) | false confident | corrections (21 map cases) | macro-F1 |
|---|---|---|---|---|
| A: heuristic | 7 | 17 | 39 | 0.810 |
| B: Nemotron, shipped prompt, raw | 18 | 6 | 12 | 0.939 |
| C: shipped hybrid (Nemotron, checker, heuristic fallback) | 17 | 7 | 14 | 0.925 |
| D: Nemotron, strong prompt, may abstain | 18 | 2 | 32 | 0.872 |

- Bar 1 (Nemotron improves role mapping): MET
- Bar 2 (the checker adds safety): NOT MET
- Bar 3 (a better prompt beats the shipped one): NOT MET
- Bar 4, run 2 addendum (the fixed checker no longer costs accuracy): NOT MET

## Per banner (✓ exact, ✗ wrong, ! false confident)

| banner | category | A | B | C | D | C used | why C fell back / D abstained |
|---|---|---|---|---|---|---|---|
| absent_role_1 | absent_role | ✓ | ✓ | ✓ | ✓ | heuristic | role legal is missing / D: legal |
| absent_role_2 | absent_role | ✓ | ✓ | ✓ | ✓ | heuristic | role price is missing / D: price |
| absent_role_3 | absent_role | ✓ | ✓ | ✓ | ✓ | heuristic | role legal is missing / D: Missing brand_mark and cta roles |
| big_decor_image_1 | big_decor_image | ! | ✓ | ✓ | ✓ | model | - |
| big_decor_image_2 | big_decor_image | ! | ✓ | ✓ | ✗ | model | - / D: Cannot confidently identify which image layer is the brand_mark and which is the |
| big_decor_image_3 | big_decor_image | ! | ! | ! | ✓ | model | - |
| big_logo_1 | big_logo | ! | ! | ! | ! | model | - |
| big_logo_2 | big_logo | ! | ! | ! | ✗ | model | - / D: brand_mark |
| big_logo_3 | big_logo | ! | ! | ! | ✗ | model | - / D: Cannot determine which image layer is brand_mark and which is product_image |
| extra_group_1 | extra_group | ! | ✓ | ✓ | ✓ | model | - |
| extra_group_2 | extra_group | ✓ | ! | ! | ! | model | - |
| extra_group_3 | extra_group | ! | ✓ | ✓ | ✓ | model | - |
| plain_1 | plain | ✓ | ✓ | ✓ | ✓ | model | - |
| plain_2 | plain | ✓ | ✓ | ✓ | ✓ | model | - |
| plain_3 | plain | ✓ | ✓ | ✓ | ✓ | model | - |
| price_emphasis_1 | price_emphasis | ! | ✓ | ✓ | ✗ | model | - / D: brand_mark |
| price_emphasis_2 | price_emphasis | ! | ✓ | ! | ✓ | heuristic | price must contain a number and a currency |
| price_emphasis_3 | price_emphasis | ! | ✓ | ✓ | ✓ | model | - |
| text_distractors_1 | text_distractors | ! | ✓ | ✓ | ✓ | model | - |
| text_distractors_2 | text_distractors | ! | ! | ! | ✓ | model | - |
| text_distractors_3 | text_distractors | ! | ✓ | ✓ | ✓ | model | - |
| twin_prices_1 | twin_prices | ! | ✓ | ✓ | ✓ | model | - |
| twin_prices_2 | twin_prices | ! | ✓ | ✓ | ✓ | model | - |
| twin_prices_3 | twin_prices | ! | ✓ | ✓ | ✓ | model | - |

## Reading (hand-written after the run, 2026-10-23; post hoc)

Run 2 of the pre-registered comparison (protocol addendum): the checker fixed in `08becc8`, a new set from a fresh agent,
and nothing else changed. Run once.

- **Bar 1 met again: what ships gets 17 of 24 against the heuristic's 7**, with 7 false-confident proposals against
  17. Across both runs, the shipped hybrid has 31 of 48 against the heuristic's 13. That is 14 and 6 for run 1, which
  used the old checker, and 17 and 7 for run 2.
- **The checker fix recovered most of the loss.** In run 1 the hybrid trailed raw Nemotron by 3. In run 2 it trails by
  1, and **bar 4 is not met because of that one case**: price_emphasis_2's price is "4.299 TL". The checker's currency
  words did not include TL. This was noticed from the set author's summary **before the run** and left unfixed, as the
  protocol requires. It is fixed after this run (TL and other ISO codes added) and that fix is not scored here.
- **The checker still adds no measured safety (bar 2 not met):** hybrid 7 false-confident, raw 6. On the cases where a
  wrong answer passed the checker, it was a plausible one (an image swap, a sticker taken as the CTA, a distractor text),
  which no type or size rule can catch.
- **The strong prompt ties raw Nemotron on exact answers (18 each), so bar 3 is not met this time.** It has the fewest
  false-confident answers (2), because it refuses instead of guessing, at the cost of more owner corrections (32).
- **Images are still guesses.** The input carries no image content. The big_logo answers are rejected by the checker's
  "product larger than logo" rule even when right, and here none were right.
- **Same limits as run 1:** the set was written by an AI agent of the builder's model family, no people were involved,
  and images are out of scope.

**What a reader can take from runs 1 and 2:** on untagged banners with distractors, sale prices or twin prices,
Nemotron's role proposals are right far more often than a size rule (31/48 vs 13/48 as shipped). The deterministic
checker keeps impossible answers out but does not catch plausible wrong ones, so the owner's confirmation step is still
needed.
