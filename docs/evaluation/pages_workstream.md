# Pages workstream (product page -> grounded facts -> checked copy -> page check)

Built: `campaign/pages.py` (URL rules, `TavilyFetcher`, `MockPageFetcher`), `campaign/facts.py` (grounded facts, price parser),
`campaign/copy.py` (headline rules, template fallback), `evaluation/page_check.py` (independent price comparison),
`api/pages.py` (`POST /pages`, `POST /page-check`), prompts `campaign_facts.md` / `campaign_copy.md`, sample page
`apps/web/public/samples/halden-h7.html`. `POST /pages` also takes `copy: false` (no model calls, baseline facts only).
Everything is tested offline with MockProvider and MockPageFetcher (`tests/unit/campaign`, `tests/integration/test_campaign_pages.py`).

## Real Tavily Extract response (one live call, 26 Oct 2026)
Request: `POST https://api.tavily.com/extract`, Bearer auth, `{"urls":[url],"extract_depth":"basic","format":"markdown","include_usage":true}`
on a public demo bookshop page. HTTP 200, 2,119 bytes, 0.02 s. Top-level fields: `results` (list), `failed_results` (list, empty),
`response_time` (float), `usage` (`{"credits": 0}` for this one basic call: the meter did not show a whole credit), `request_id`.
Each result: `url`, `title` (the HTML title, not the H1), `raw_content` (markdown, 1,780 chars), `images` (empty list).
The markdown starts with the site header and breadcrumb links and contains image lines (`![alt](path)`), which we strip; the
product H1 and the price (`£51.77`) are plain lines. Trimmed copy: `tests/fixtures/tavily_extract_response.json`.

## Limits and deviations
- `draft_copy` takes an extra optional `page_text` argument: headlines are checked against the whole page, not only the facts.
- If the model returns no usable price, the deterministic price patterns from the page text are used (as grounded as a fact gets).
- The failure statuses 401/429/432/433/5xx and `failed_results` were exercised only against `httpx.MockTransport`, not live.
- Not verified live: a Tavily fetch of the sample page from the public demo URL (needs that URL deployed), real Nemotron output.
- Language guess for the no-model baseline is a small stop-word count (de/fr/es, else en); it is a fallback, not detection.
- `MockPageFetcher` reads the sample HTML from the repo path, so it needs `apps/web/public` present on the server.
- Page text is held in memory per workspace; no persistence.
