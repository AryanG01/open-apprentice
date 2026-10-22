# Campaign lane: authoring and sealing the private held-out set

The public development fixtures (`src/open_apprentice/campaign/fixture_data/`) were used while building the lane, so they
cannot support a generalization claim. This set can, if it is authored by the owner without looking at what the system
does, sealed before it is run, and never changed afterwards.

## Where it lives

`benchmarks/final/campaign/` (git-ignored; never commit it):

- `banners/<id>.json`: one 16:9 banner each, in the development fixture format: `{id, locale, provenance, artboard,
  expected_outcomes, scene}`. `expected_outcomes` lists the outcomes the owner considers correct for that banner:
  `["layout"]` when it should fit the story card, or one or both of `"shrink"`, `"split"` when it should overflow.
- `gold/<id>.<outcome>.json`: the owner's expected story card(s) for each listed outcome, in the gold format
  (`{fixture, outcome, applicable, scene}`), coordinates in each card's top-left frame.

## Rules for a banner to count as held out

- New ids (not `short_a`, `de_long_a`, …), new copy, new layouts of the source banner; at least one new locale.
- Only the vendored font (`Liberation Sans`, normal or bold) and the vendored assets (`h7-headphones`, `halden-wordmark`).
- Every role present exactly once: background, brand_mark, product_image, headline, price, cta, legal.
- The gold follows the taught story layout and the frozen limits (`campaign/limits.py`): safe insets 220/72/220/72,
  minimum sizes, built-in shrink/split geometry as documented in `campaign/builtins.py`. Author the gold from that written
  description, not from running the system.
- At least 6 banners: short ones that fit, long ones that need shrink, long ones where only split fits.

## Commands

```
oa eval campaign-seal            # validates, then writes docs/evaluation/campaign_sealed_manifest.json (hashes only)
git add docs/evaluation/campaign_sealed_manifest.json && git commit -m "chore: seal the campaign held-out set"
oa eval campaign-sealed-run      # refuses if any file changed; runs Konva and Fabric; report in results/campaign_sealed/<date>/
```

The run learns only from the public teaching pair. Questions are answered with the gold's outcome and recorded as such.
Report the table as it comes out, failures included. Once sealed, the set is frozen: a changed file means a new set and
a new seal, and the old results stay reported.
