# Reading a banner image: development probe

Model `nvidia/Nemotron-3.5-Super-VL` · 6 development banners rendered by the real engine · 7 calls · $0.041 (ledger). Development fixtures, not held out; one run, no retries.

**Decision: partial** (rule fixed beforehand: go = 5 of 6 banners with every layer found at box overlap ≥ 0.5 and median text-layer overlap ≥ 0.6; partial = roles named right on 5 of 6 and ≥ 70% of words exact).

- Every layer found on **0 of 6** banners; all six roles named once on 6.
- Median box overlap of the text layers: **0.567**; words read exactly: **0.833**.

| banner | roles named | all found | brand_mark IoU | product_image IoU | headline IoU | price IoU | cta IoU | legal IoU | words exact | origin |
|---|---|---|---|---|---|---|---|---|---|---|
| teach_before | yes | no | 0.301 | 0.569 | 0.161 | 0.168 | 0.145 | 0.068 | 4/4 | model |
| short_a | yes | no | 0.446 | 0.568 | 0.31 | 0.59 | 0.938 | 0.113 | 4/4 | model |
| short_b | yes | no | 0.347 | 0.426 | 0.325 | 0.581 | 0.902 | 0.119 | 4/4 | model |
| de_long_a | yes | no | 0.429 | 0.531 | 0.832 | 0.278 | 0.938 | 0.308 | 3/4 | model |
| de_long_b | yes | no | 0.431 | 0.539 | 0.875 | 0.646 | 0.866 | 0.953 | 2/4 | model |
| fr_long | yes | no | 0.864 | 0.611 | 0.714 | 0.552 | 0.809 | 0.348 | 3/4 | model |
