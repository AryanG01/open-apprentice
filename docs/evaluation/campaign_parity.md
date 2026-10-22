# Campaign lane: Konva / Fabric parity

Generated 2026-10-22 at commit `ce33259` (Konva 9.3.22, Fabric 6.9.1) by `oa eval campaign-parity`. Public development fixtures, not held out.

One learned rule for both backends (origin `search`, sha256 `d1e124db9dd79ed3…`), the same reference procedure, built-in outcomes labelled as such. Each row is the independent verifier against the authored gold.

**16 of 16 rows pass.**

| fixture | outcome | backend | verifier | failed checks |
|---|---|---|---|---|
| teach_before | layout | konva | pass | - |
| short_a | layout | konva | pass | - |
| short_b | layout | konva | pass | - |
| de_long_a | shrink | konva | pass | - |
| de_long_a | split | konva | pass | - |
| de_long_b | split | konva | pass | - |
| fr_long | shrink | konva | pass | - |
| fr_long | split | konva | pass | - |
| teach_before | layout | fabric | pass | - |
| short_a | layout | fabric | pass | - |
| short_b | layout | fabric | pass | - |
| de_long_a | shrink | fabric | pass | - |
| de_long_a | split | fabric | pass | - |
| de_long_b | split | fabric | pass | - |
| fr_long | shrink | fabric | pass | - |
| fr_long | split | fabric | pass | - |

## Run status per banner (no saved preference)

| fixture | konva | fabric |
|---|---|---|
| short_a | ready | ready |
| short_b | ready | ready |
| de_long_a | question | question |
| de_long_b | question | question |
| fr_long | question | question |
| missing_role | needs_roles | needs_roles |
| duplicate_role | needs_roles | needs_roles |
