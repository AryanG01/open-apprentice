# Campaign role mapping: does Nemotron help? (pre-registered 2026-10-23)

Written and committed **before** the test banners exist and before any run. The set, arms, metrics and bars below do not
change after the first run; anything added later is labelled post hoc.

## Question

The development measurement (`campaign_nemotron.md`) tied: Nemotron 6/6, heuristic 6/6, on six plain banners. Does
Nemotron improve role mapping on harder untagged banners, and does the shipped checker-plus-fallback add anything over
the raw model?

## The set

24 untagged 16:9 banners in `benchmarks/final/campaign_roles/` (git-ignored). Each SHA-256 is committed in
`campaign_roles_manifest.json` before the first run. A fresh Claude agent writes them from this protocol and the
scene format. It does not see the role prompts, the heuristic, the checker, or any model output, and it does not run
the system. Same model family as the builder: "held out" means not seen during building, not independent human data.

Eight categories, 3 banners each:

| category | what makes it hard |
|---|---|
| plain | control: the 7 roles and nothing else |
| big_decor_image | a decorative image (lifestyle photo, texture) larger than the product image |
| big_logo | the brand mark is the larger image, the product a small cut-out |
| text_distractors | extra text layers (badge, subheadline, tagline) whose font sizes fall between or above the role texts |
| price_emphasis | the price's font is larger than the headline's (sale banner) |
| extra_group | a second shape+text group (badge, sticker) besides the CTA |
| twin_prices | two price-like texts (old struck price and current price); gold price is the current one |
| absent_role | one required role is missing (no legal line, or no price); the right answer is to not give a confident full mapping |

Gold: the role tags in each file (decorative layers carry none). Absent-role files are marked `"expect": "abstain"`.

## Arms

- **A, heuristic:** `heuristic_roles` as shipped.
- **B, Nemotron raw:** the shipped prompt (`prompts/campaign_roles.md`), the same opaque-id layer list, its answer
  taken as given (unparseable = no answer).
- **C, shipped hybrid:** `propose_roles` as shipped: B's answer if the checker accepts it, otherwise the heuristic.
  The owner-confirmation step needs a person and is not measured. C reuses B's call (one call per banner).
- **D, Nemotron strong prompt:** a prompt written before the set exists (`prompts/campaign_roles_strong.md`) that warns
  of decorative layers and lets the model abstain; same input, no checker.

Model `nvidia/nemotron-3-super-120b-a12b` on Nebius Token Factory, the production settings (reasoning effort low).
One call per banner per model arm, no retries, no selection among runs.

## Metrics (per arm, denominators shown, per-banner table published)

- **Exact:** for the 21 map cases, the mapping equals the gold; for the 3 abstain cases, the arm gives no complete
  7-role mapping.
- **Macro-F1** over the 7 roles on the 21 map cases (a layer given a role it does not have counts against both).
- **False confident:** a complete 7-role mapping that is wrong (the owner would be shown a wrong answer as a proposal).
- **Corrections:** layers the owner would have to change to reach the gold (map cases), a proxy for effort; time to an
  accepted mapping needs people and is not measured.
- **Calls, tokens, latency, cost** from the run's ledger.

## Bars (decided now)

1. "Nemotron improves role mapping" is claimed only if **C exact ≥ A exact + 3** and **C false-confident ≤ A's**.
2. "The checker adds safety" is claimed only if **C false-confident < B false-confident**.
3. "A better prompt beats the shipped one" is claimed only if **D exact ≥ C exact + 3**.

Otherwise the result is reported as no measured gain, whichever direction the numbers lean. The product is not changed
between writing the set and the run.

## Budget

48 calls (B and D). Run cap $0.40 through `SpendGuard`; the Nebius balance stays above the $10 reserve.
