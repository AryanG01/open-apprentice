# Reading a banner image: development probe

Model `nvidia/Nemotron-3.5-Super-VL` · 6 development banners rendered by the real engine · 6 calls · $0.030 (ledger). Development fixtures, not held out; one run, no retries.

**Decision: partial** (rule fixed beforehand: go = 5 of 6 banners with every layer found at box overlap ≥ 0.5 and median text-layer overlap ≥ 0.6; partial = roles named right on 5 of 6 and ≥ 70% of words exact).

- Every layer found on **0 of 6** banners; all six roles named once on 6.
- Median box overlap of the text layers: **0.551**; words read exactly: **0.833**.

| banner | roles named | all found | brand_mark IoU | product_image IoU | headline IoU | price IoU | cta IoU | legal IoU | words exact | origin |
|---|---|---|---|---|---|---|---|---|---|---|
| teach_before | yes | no | 0.472 | 0.526 | 0.202 | 0.569 | 0.938 | 0.114 | 4/4 | model |
| short_a | yes | no | 0.755 | 0.393 | 0.045 | 0.0 | 0.0 | 0.0 | 4/4 | model |
| short_b | yes | no | 0.558 | 0.541 | 0.246 | 0.515 | 0.947 | 0.216 | 4/4 | model |
| de_long_a | yes | no | 0.727 | 0.387 | 0.714 | 0.657 | 0.896 | 0.382 | 3/4 | model |
| de_long_b | yes | no | 0.864 | 0.413 | 0.714 | 0.55 | 0.896 | 0.854 | 2/4 | model |
| fr_long | yes | no | 0.864 | 0.554 | 0.885 | 0.552 | 0.924 | 0.297 | 3/4 | model |
