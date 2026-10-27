# Final sprint audit, 27 Oct 2026

Reconciles the outside source review (done at `9dd33a9`) with this branch (`sprint/final-quality`, cut from `2c8d409`, which
differs from `9dd33a9` by docs only). Status vocabulary: **implemented + verified**, **implemented + not verified**, **absent**, **blocked**.
Evidence levels: *reproduced offline*, *regression test*, *source-confirmed, integration pending*, *reported historical result*.

## Findings and what was done

| # | Finding | Reproduced by me | Status after this branch |
|---|---|---|---|
| A1 | Deleting the product image (or background, logo, headline, price, button, small print) still gave an all-pass without gold | Yes, offline: `True, 14, []` for all three deletions | **implemented + verified.** New check `source_complete` in `evaluation/campaign_verifier.py`: every source node must survive under its own id or as the `-2` copy of a repeated brand mark/background; no other duplicates; no orphan parents. Regression tests (`tests/unit/evaluation/test_campaign_verifier.py`): 7 role deletions, CTA-label deletion, duplicate, forbidden clone, missing parent, all valid gold results incl. split clones. Real engine results on Konva and Fabric pass the new check (`OA_ENGINE_TESTS=1` integration suite). Check count is now 16 with gold, 15 without; UI shows the real count. |
| A2 | The code never rejected an absent product name, a dropped qualifier, a negation or a savings claim, although README/submission/video said names were rejected | Yes (all four drafts return no problems) | **implemented + verified, narrower claim.** Hard checks unchanged. New `review_notes` (copy.py) attaches advisory notes to each draft (new capitalised word not on the page, dropped "up to", "not/no" sentence, stated saving); the UI lists them as "Check: ..." and the label says "read it and approve it". README, submission, video narration/captions, provenance panel and the UI heading no longer claim names are verified. This is heuristic and will miss cases; it is not entailment. |
| A2b | Page check said `match` for the wrong product's price and for an old price | Yes | **implemented + verified.** `evaluation/page_check.py`: an amount introduced as previous ("was", "statt"...) no longer matches a current banner price; if the headline names a product and the page puts a different current price right after that name, status is `mismatch`. Row now has `scope: "amount_on_page"`; UI label is "Amount found on page" with a line saying it is not proof of today's price. |
| A3 | Adapt did not send `expected_version`, so replacing a saved choice failed with a 409 | Store behaviour reproduced; browser sequence not run | **implemented + verified at API level.** Run output carries `preference_seen`; Adapt sends it; the server also falls back to the run's own snapshot when a client omits it; a question asked before a preference changed still gets a 409 and saves nothing (`test_the_question_carries_the_preference_version...`, `test_an_answer_without_a_version...`). **Not done:** a main-Adapt browser test for the full v1 shrink, fresh split-only banner, v2 sequence. |
| A4 | Workspaces are process memory (30 min, 20 per process), preferences are scoped to the workspace | Source-confirmed | **implemented + not verified in a browser.** Copy now says "remembered for this workspace ... about 30 minutes; a reload or restart starts fresh". An expired-workspace 404 shows a clear message and drops the stale id. No persistence added (out of scope). |
| A5 | Real-sketch runner: one workspace for all sketches (5th upload 409), automatic curl retries on a paid POST, filename order | Source-confirmed | **implemented + not run.** Runner opens a workspace per sketch, never retries, uses `manifest.txt` order, saves raw boxes/status. Protocol amended (dated, before any call). No real sketch has been read. |
| A6 | History orphans; global spend cap not atomic in this lane; learning language; no final layered editor; evidence labels | Source-confirmed by reviewer (history orphan reproduced by reviewer, not by me) | **absent / documented only.** Not changed this sprint (P2). The role-assignment comparison is hybrid vs heuristic (17/24 vs 7/24), not "rule vs text model"; see `docs/evaluation/campaign_roles_v2.md`. |

## Still open (not done)

- Owner inputs: real banners, real sketches, comparator task, listening pass (checklist in the sprint handoff).
- Real-input visual quality pass (WP1), preference reuse proof R1-R4 on fresh input (WP2), verifier mutation table through the real engine (WP3 6.1: only the omission class is covered), four-banner evaluation (WP4).
- Video re-record with corrected narration; audio loudness pass on the master.
- Judge-access and budget gate (WP7); deployment is owner-run.
- Trust-boundary check `lint-imports` could not be re-run in this sandbox earlier today (no PyPI access).

## Gates run on this branch (27 Oct)
Python (3.12, engine on): 1793 tests, all pass after fixing 2 stale assertions this branch caused; browser e2e (real Chromium + engine, axe scans): 18 passed, 0 failed, 1 skipped; ruff clean; black clean on `src tests scripts`; tsc clean; web lint 0 errors, 1 pre-existing warning (`App.tsx:169`).
`lint-imports` still not run here (no PyPI access in the sandbox): run `uv run lint-imports` before release.
