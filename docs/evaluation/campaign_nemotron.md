# Campaign lane: what Nemotron adds

2026-10-22 · model `nvidia/nemotron-3-super-120b-a12b` (live, Nebius Token Factory) · 25080 tokens · $0.040 spent (ledger). Development fixtures, not held out.

## Role proposals (banner shown with its roles removed; correct = exactly the authored roles)

Nemotron correct on **6 of 6**; heuristic correct on **6 of 6**.

| banner | Nemotron used | Nemotron correct | heuristic correct | Nemotron rejected because |
|---|---|---|---|---|
| teach_before | yes | yes | yes | - |
| short_a | yes | yes | yes | - |
| short_b | yes | yes | yes | - |
| de_long_a | yes | yes | yes | - |
| de_long_b | yes | yes | yes | - |
| fr_long | yes | yes | yes | - |

## Overflow explanations (used only if every stated number and element matches the measured facts)

Nemotron's wording used on **3 of 3**; otherwise the template.

| banner | used | text shown | rejected because |
|---|---|---|---|
| de_long_a | model | The headline needs 317 px but its frame provides only 160 px, causing overflow. Both built‑in options—shrinking the hero or splitting into two cards—fit within the limits. | - |
| de_long_b | model | The headline (317 px) and legal (218 px) texts exceed their frames’ 160 px height, so they overflow. The shrink‑hero option cannot fix this (false), while splitting into two cards resolves the overflow (true). | - |
| fr_long | model | The headline needs 238 px but its frame provides only 160 px, causing overflow. Both built‑in options—shrinking the hero image and splitting into two cards—fit the layout. | - |

## Native procedures (accepted only if the verifier passes a seen banner and two new ones)

| engine | accepted | attempts | cases passed per attempt |
|---|---|---|---|
| konva | Nemotron | 1 | 3 of 3 |
| fabric | Nemotron | 1 | 3 of 3 |
