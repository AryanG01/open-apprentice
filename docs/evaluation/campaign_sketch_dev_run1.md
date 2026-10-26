# Reading a rough sketch: development probe

Model `nvidia/Nemotron-3.5-Super-VL` · 6 synthetic wireframes (seeded wobbly lines drawn from the development fixtures, NOT hand drawn) · 6 calls · $0.027 (ledger). Development fixtures, not held out; one run, no retries. The owner's real sketches are a separate set and are the honest test.

**Decision: partial** (rule fixed beforehand: go = every layer found at box overlap ≥ 0.3 on 5 of 6 sketches and median overlap of all layers ≥ 0.5; partial = all six roles named once on 5 of 6 and median overlap ≥ 0.3).

- Every layer found on **2 of 6** sketches; all six roles named once on 6.
- Median box overlap of all layers: **0.611**.
- Post hoc: words the model wrote although the sketches carry none: 1.

| sketch | roles named | all found | brand_mark IoU | product_image IoU | headline IoU | price IoU | cta IoU | legal IoU | origin |
|---|---|---|---|---|---|---|---|---|---|
| teach_before | yes | no | 0.714 | 0.942 | 0.24 | 0.614 | 0.781 | 0.184 | model |
| short_a | yes | no | 0.781 | 0.953 | 0.573 | 0.636 | 0.806 | 0.2 | model |
| short_b | yes | no | 0.576 | 0.913 | 0.181 | 0.0 | 0.0 | 0.199 | model |
| de_long_a | yes | yes | 0.651 | 0.96 | 0.513 | 0.821 | 0.756 | 0.447 | model |
| de_long_b | yes | no | 0.69 | 0.583 | 0.19 | 0.0 | 0.0 | 0.0 | model |
| fr_long | yes | yes | 0.576 | 0.913 | 0.854 | 0.609 | 0.889 | 0.643 | model |
