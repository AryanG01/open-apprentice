# Report (development-pilot)
**MEASURED (live model rows + non-model reference rows; split and n stated below)**

Rows: 36 over 1 independent episodes. Repetitions do not add independent samples.

| method | correct / scheduled (transfer+composition) | conditional | false success | failures |
|---|---|---|---|---|
| enumerative_reference | 4/4 | 4/4 | 0/4 | {} |
| full_v1_2 | 0/4 | 0/0 | 0/0 | {"abstained": 4} |
| fresh_full_context | 0/4 | 0/0 | 0/0 | {"abstained": 4} |
| text_memory | 0/0 | 0/0 | 0/0 | {} |
| structured_procedure | 0/4 | 0/0 | 0/0 | {"abstained": 4} |

Primary: full_v1_2 - structured_procedure over 1 episodes: diff=None, 95% CI=None. fewer than 2 paired episodes: no uncertainty can be estimated

Gates (spec 27.5, prospective): evaluated. prospective goals from spec 27.5; passing them would support considering an exceptional score, not guarantee one