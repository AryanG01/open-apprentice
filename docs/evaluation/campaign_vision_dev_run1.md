# Reading a banner image: development probe, run 1 (re-scored after the frame fix)

Model `nvidia/Nemotron-3.5-Super-VL` · 6 development banners rendered by the real engine · 11 calls · $0.040 (ledger). Development fixtures, not held out; one run, no retries.

**Decision: partial** (rule fixed beforehand: go = 5 of 6 banners with every layer found at box overlap ≥ 0.5 and median text-layer overlap ≥ 0.6; partial = roles named right on 5 of 6 and ≥ 70% of words exact).

- Every layer found on **0 of 6** banners; all six roles named once on 5.
- Median box overlap of the text layers: **0.464**; words read exactly: **0.75**.

| banner | roles named | all found | brand_mark IoU | product_image IoU | headline IoU | price IoU | cta IoU | legal IoU | words exact | origin |
|---|---|---|---|---|---|---|---|---|---|---|
| teach_before | yes | no | 0.372 | 0.534 | 0.22 | 0.573 | 0.882 | 0.119 | 4/4 | model |
| short_a | yes | no | 0.446 | 0.568 | 0.31 | 0.59 | 0.938 | 0.113 | 4/4 | model |
| short_b | yes | no | 0.453 | 0.533 | 0.297 | 0.593 | 0.882 | 0.148 | 4/4 | model |
| de_long_a | yes | no | 0.9 | 0.551 | 0.885 | 0.589 | 0.924 | 0.374 | 3/4 | model |
| de_long_b | no | no | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0/4 | manual |
| fr_long | yes | no | 0.915 | 0.536 | 0.711 | 0.554 | 0.758 | 0.345 | 3/4 | model |
