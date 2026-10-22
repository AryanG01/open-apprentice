# Campaign lane: what Nemotron adds

2026-10-22 · model `nvidia/nemotron-3-super-120b-a12b` (live, Nebius Token Factory) · 19727 tokens · $0.032 spent (ledger). Development fixtures, not held out.

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

Nemotron's wording used on **2 of 3**; otherwise the template.

| banner | used | text shown | rejected because |
|---|---|---|---|
| de_long_a | model | The headline needs 317 px but its frame provides only 160 px, causing overflow. The built‑in shrink_hero option reduces the hero size to fit, and split_two_cards moves excess content to a second card, both of which accommodate the overflow. | - |
| de_long_b | template | The headline needs 317 px but its frame holds 160 px; the legal line needs 218 px but its frame holds 160 px. Shrinking the product image does not fit; Splitting across two cards fits. | the number 1080 is not in the measured facts; the number 1920 is not in the measured facts |
| fr_long | model | The headline needs 238 px but its frame provides only 160 px, causing vertical overflow. The built‑in ‘shrink_hero’ scales the banner down to fit, while ‘split_two_cards’ divides the content across two story cards so each fits. | - |

## Native procedures (accepted only if the verifier passes a seen banner and two new ones)

| engine | accepted | attempts | cases passed per attempt |
|---|---|---|---|
| konva | Nemotron | 1 | 3 of 3 |
| fabric | Nemotron | 1 | 3 of 3 |

## Reading (hand-written, 2026-10-22)

- This is the third live run on Nemotron-3-Super (run 1, $0.031, lost its table to a CLI bug; run 2, $0.040, explanations
  3/3; this run, $0.032, explanations 2/3: one rejected for stating a number not in the facts). Wording quality varies
  run to run; the fact check is what keeps a wrong explanation off the screen.
- Roles: 6 of 6 for Nemotron and for the heuristic. These development banners are easy; no gain is shown.
- Procedures: the programs Nemotron wrote are saved in `campaign_nemotron_programs.json`. Both are one loop per input
  list in the order the prompt lists them, with arguments named after the input fields. The Konva program is
  byte-identical to the reference procedure (which the prompt does not contain); the Fabric one differs only in
  variable names and a redundant guard. The prompt's input contract all but dictates the program, so this shows that
  Nemotron reliably follows a precise tool contract on both engines, not that it designs procedures. A harder test
  would give it unordered or higher-level inputs.
