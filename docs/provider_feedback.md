# Provider feedback: Nebius Token Factory + NVIDIA Nemotron

Measured observations only (probe run 2026-10-09, `oa provider probe --live`, raw data in `docs/capabilities.json`).
Separate from expectations. No credentials or account data here.

## Worked as documented
- `GET /models` lists 25 models; `nvidia/nemotron-3-super-120b-a12b` is present and every response returns that exact id.
- `max_tokens` is accepted (the documented `max_completion_tokens` was not needed).
- `response_format: {"type":"json_object"}` returns parseable JSON.
- `usage` is reported with `prompt_tokens`, `completion_tokens`, `total_tokens`, `prompt_cache_hit/miss_tokens`, and
  `completion_tokens_details.reasoning_tokens`.
- `seed` and `temperature: 0` are accepted. (Determinism of the output was NOT tested.)
- `reasoning_effort` (`none`, `low`, ...) is accepted and changes hidden reasoning spend for an identical small task:
  default 23 reasoning tokens, `low` 7, `none` 0.

## Documentation mismatches
- The chat-completion reference lists `json_schema` in the `response_format.type` enum but its prose says only
  `json_object` and `text` are supported. In practice `json_schema` with `strict: true` WORKED (valid output) once the
  token budget was large enough.
- `seed` is not listed on the chat-completion reference page, but the endpoint accepts it.

## Surprises that affect design
- Nemotron Super returns `reasoning` / `reasoning_content` on every message and spends hidden reasoning tokens against the
  completion limit. With `max_tokens: 32` a trivial request returned **zero visible characters** and
  `finish_reason: "length"`; a schema request needed ~220 completion tokens, ~211 of them reasoning.
  Consequence: a too-small cap looks like "unsupported feature" or "model failure" unless truncation is classified separately.
  The first probe run misreported `json_schema` as failing for exactly this reason.
- Error bodies and pricing: the reference page lists no prices or numeric rate limits (only 402 for exhausted budget and 429).

## Not yet measured
- Latency under load, rate-limit behaviour, determinism with a fixed seed, native tool calling, vision input, quality impact
  of `reasoning_effort` on rule synthesis (this is a tuning question for development data, applied identically to all methods).
