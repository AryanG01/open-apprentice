# Campaign lane: what Nemotron adds

2026-10-22 · model `nvidia/nemotron-3-super-120b-a12b` (live, Nebius Token Factory) · 89746 tokens · $0.255 spent (ledger). Development fixtures, not held out.

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

Nemotron's wording used on **0 of 3**; otherwise the template.

| banner | used | text shown | rejected because |
|---|---|---|---|
| de_long_a | template | The headline needs 317 px but its frame holds 160 px. Shrinking the product image fits; Splitting across two cards fits. | does not say plainly that shrinking fits; does not say plainly that spliting fits |
| de_long_b | template | The headline needs 317 px but its frame holds 160 px; the legal line needs 218 px but its frame holds 160 px. Shrinking the product image does not fit; Splitting across two cards fits. | suggests shrinking works, but it does not fit; does not say plainly that spliting fits |
| fr_long | template | The headline needs 238 px but its frame holds 160 px. Shrinking the product image fits; Splitting across two cards fits. | does not say plainly that shrinking fits; does not say plainly that spliting fits |

## Native procedures (accepted only if the verifier passes a seen banner and two new ones)

| engine | accepted | attempts | cases passed per attempt |
|---|---|---|---|
| konva | Nemotron | 1 | 3 of 3 |
| fabric | Nemotron | 2 | 0 of 0, 3 of 3 |

## Reading (hand-written, 2026-10-22)

This is run 4, the first under the setup fixed after the final review: the role prompt shows opaque layer ids and no
asset names, the procedure examples are disjoint from the acceptance banners (`short_b`, `de_long_a` are unseen), empty
programs are refused, and the explanation check requires every outcome stated with the right polarity.

- **Roles: 6 of 6, with opaque ids.** Nemotron labels every layer correctly without id hints. The heuristic also gets
  6 of 6 on these simple banners, so no gain over it is shown.
- **Explanations: 0 of 3 accepted** under the stricter check; the template was shown each time. The rejected wording was
  not recorded in this run (recording was added afterwards), so whether the check is now too strict or the wording was
  wrong cannot be told from this table. In runs 2 and 3 under the looser check, 3/3 and 2/3 were accepted.
- **Procedures: accepted on Konva at attempt 1 and on Fabric at attempt 2**, each passing the seen banner and the two
  unseen ones. The saved programs (`campaign_nemotron_programs.json`) are again one loop per input list in the
  prompt's order: contract-following, not procedure design.
- **Cost: $0.255 (ledger) for 14 calls, far above the ~$0.03 estimate.** Two procedure calls (Fabric's first attempt
  and its retry) hit the completion limit after ~35k tokens of reasoning each and cost $0.22 between them for nothing
  usable. `max_tokens` does not bound Nemotron-3-Super's reasoning here, so a single procedure request can cost about
  $0.25. All four runs today: $0.358 (ledger).

Earlier runs (prompts before the review fixes; not comparable): run 1 lost its table to a CLI bug ($0.031); run 2
($0.040) explanations 3/3, procedures accepted at attempt 1 on both engines (programs not saved); run 3 ($0.032)
explanations 2/3, procedures accepted at attempt 1, Konva program identical to the reference.
