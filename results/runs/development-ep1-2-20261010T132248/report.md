# Report (development-pilot)
**MEASURED (live model rows + non-model reference rows; split and n stated below)**

Rows: 90 over 2 independent episodes. Repetitions do not add independent samples.

| method | correct / scheduled (transfer+composition) | conditional | false success | failures |
|---|---|---|---|---|
| enumerative_reference | 8/8 | 8/8 | 0/8 | {} |
| full_v1_2 | 0/8 | 0/3 | 3/3 | {"wrong_output": 3, "abstained": 5} |
| fresh_full_context | 0/8 | 0/0 | 0/0 | {"abstained": 8} |
| text_memory | 1/8 | 1/1 | 0/1 | {"abstained": 7} |
| structured_procedure | 1/8 | 1/1 | 0/1 | {"abstained": 7} |

Primary: full_v1_2 - structured_procedure over 2 episodes: diff=-0.125, 95% CI=[-0.25, 0]. episode-clustered percentile bootstrap; with few episodes uncertainty is substantial

Gates (spec 27.5, prospective): evaluated. prospective goals from spec 27.5; passing them would support considering an exceptional score, not guarantee one