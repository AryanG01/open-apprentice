# Report (development-pilot)
**MEASURED (live model rows + non-model reference rows; split and n stated below)**

Rows: 117 over 3 independent episodes. Repetitions do not add independent samples.

| method | correct / scheduled (transfer+composition) | conditional | false success | failures |
|---|---|---|---|---|
| enumerative_reference | 12/12 | 12/12 | 0/12 | {} |
| full_v1_2 | 0/12 | 0/4 | 4/4 | {"wrong_output": 4, "abstained": 8} |
| fresh_full_context | 3/12 | 3/5 | 2/5 | {"wrong_output": 2, "abstained": 7} |
| text_memory | 1/8 | 1/2 | 1/2 | {"abstained": 5, "wrong_output": 1, "budget_exhausted:tokens": 1} |
| structured_procedure | 1/8 | 1/5 | 4/5 | {"wrong_output": 4, "abstained": 3} |

Primary: full_v1_2 - structured_procedure over 2 episodes: diff=-0.125, 95% CI=[-0.25, 0]. episode-clustered percentile bootstrap; with few episodes uncertainty is substantial

Gates (spec 27.5, prospective): evaluated. prospective goals from spec 27.5; passing them would support considering an exceptional score, not guarantee one