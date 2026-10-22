# Plan 9C: Campaign API and Campaign tab

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A person opens the "Campaign" tab, sees the taught banner→story pair, has the apprentice learn it, runs it on any development banner, sees the result (or answers the overflow question from two rendered, applied previews), and manages the saved per-language preference; every result shown as applied has passed the independent verifier against its authored gold.

**Architecture:** A new FastAPI router `api/campaign.py` (`/api/campaign`) holds in-memory workspaces (one learned layout + a preference namespace) with the same TTL/eviction pattern as `api/teach.py`. Runs call `campaign.run.start_run/answer` through the evaluator harness; the API immediately snapshots each result/preview session (PNG via `export_scene`, native state via the evaluator route) and closes it, so no engine session outlives a request. The API (allowed to import the evaluator) verifies committed results with `verify_story` + `load_gold`. A new `CampaignLane.tsx` tab follows `SvgLane.tsx`.

**Tech Stack:** FastAPI, existing `api/teach.py` helpers (`_engine`, `_rate_limit`), `EvaluatorHarness`, `storage.factory.store_from_env`, React + TS (Vite), Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-10-22-promo-story-card-design.md` (§2 goal 5, §7.5-7.7, §9 step 7-8). Plans 9A/9B (merged) supply everything below the API.

**Plan 3 of 4.** 9D: Fabric contract and parity, then the private sealed set.

## Global Constraints

- All Plan 9A/9B constraints hold (origins `search|model|reference|builtin`, preference scope per locale, explicit-path commits, Python 3.12, engine tests outside the sandbox).
- The campaign package still never imports the evaluator; only `api/campaign.py` calls `verify_story`/`load_gold`.
- No engine session survives a request: every session a run opens is snapshotted and closed before the response returns.
- Evidence stays separate (repo rule): the response and the UI show verifier checks, origins and fit violations as separate items; no single "verified" badge.
- Development only: every banner is a public development fixture, labelled "development fixture, not held out" in the UI. No live Nemotron in this plan (search learning only); the model path stays off.
- Public routes follow the lane pattern: `_rate_limit(request, "campaign")` on every engine-using POST, pydantic bounds on inputs, 404 unknown/expired, 409 wrong state, 422 refused input, 503 engine down.
- Web: named exports, no `any`, ESLint clean (`npm run lint`), build passes (`npm run build:web`).

## Review Focus

1. A workspace that expires while a question is open: the answer gets 404 "unknown or expired", nothing is applied, no preference written.
2. Two browser tabs on one workspace answering the same question: the second gets 409 (run no longer waiting), the first result stands.
3. A run whose committed result fails the verifier (e.g. no gold for that banner/outcome): the response says `blocked` with the failed checks and the UI shows it as not applied, never as a success.
4. The engine down or at its session cap mid-run: 503 with a plain message, the workspace survives, a retry works, and the engine's live session count returns to 0.
5. Rapid repeated clicks (double POST of the same run/answer): rate limit and run state keep it to one applied result and one preference version.

Each is pinned by a test in the owning task.

---

### Task 1: Namespaced preferences

**Files:**
- Modify: `src/open_apprentice/campaign/preferences.py`
- Test: `tests/unit/campaign/test_preferences.py`

**Interfaces:**
- `PreferenceStore(store: Store, namespace: str = "")` — keys become `campaign/{namespace}/preferences/{scope}/...` when `namespace` is set (`campaign/preferences/...` unchanged when empty). `namespace` must match `^[a-f0-9]{8,64}$` when non-empty, else `ValueError`.

- [ ] **Step 1: Failing tests:** two stores over one `LocalStore` with namespaces `"a"*16` and `"b"*16` keep independent histories; a bad namespace (`"../x"`) raises `ValueError`; an empty namespace reads what 9B wrote.
- [ ] **Step 2-4:** run (fail), implement, run (pass).
- [ ] **Step 5: Commit** `feat(campaign): namespaced preference stores`.

### Task 2: Campaign router, workspaces and learning

**Files:**
- Create: `src/open_apprentice/api/campaign.py`
- Modify: `src/open_apprentice/api/app.py` (include router before the static mount; `app.state.campaign = {}` in lifespan), `src/open_apprentice/api/teach.py` (`RATE_LIMITS["campaign"] = 60`)
- Test: `tests/integration/test_campaign_api.py` (with a `client` fixture like `test_svg_lane_api.py` plus `OA_STORE_DIR=tmp_path`)

**Interfaces (routes, JSON):**
- `GET /api/campaign/fixtures` → `{fixtures: [{id, locale, kind: "teaching"|"banner"|"broken", png}]}` for every `FIXTURE_IDS` entry except `teach_after`; `png` is a `data:image/png` URL rendered once per process (cached) via a throwaway session.
- `POST /api/campaign/workspaces` (rate-limited) → learns from `teach_before`/`teach_after` (`learn_layout`, no provider) → `{workspace_id, learned: {origin, candidates: [{origin, reproduces, reason}]}, teaching: {before_png, after_png}}`. `workspace_id` = 32 hex chars.
- Workspace registry: `app.state.campaign: dict[str, Workspace]`; `@dataclass Workspace: id, learned: Learned, prefs: PreferenceStore (namespace = id), runs: dict[str, RunRecord], touched: float, lock: asyncio.Lock`. TTL 30 min, max 20 (evict least recently touched), same sweep shape as `teach._get`; `_ws(request, wid)` → 404 `"unknown or expired workspace"`.

- [ ] **Step 1: Failing tests:** fixtures list has 8 entries with PNG data URLs and correct kinds; creating a workspace returns origin `search` and two teaching PNGs; an unknown workspace id → 404; the 21st workspace evicts the oldest (its id then 404s); after these calls the engine's `/health/live` reports `sessions: 0` (Review Focus 4, partial).
- [ ] **Step 2-4:** run (fail), implement, run (pass, outside the sandbox).
- [ ] **Step 5: Commit** `feat(api): campaign workspaces and learning`.

### Task 3: Runs, answers, verifier gate and preferences over HTTP

**Files:**
- Modify: `src/open_apprentice/api/campaign.py`
- Test: `tests/integration/test_campaign_api.py`

**Interfaces:**
- `RunRecord: run: CampaignRun, fixture_id: str, snapshots: dict[str, {png, native}]` (keyed by session id), `verification: dict | None`.
- `POST /api/campaign/workspaces/{wid}/runs` body `{fixture_id}` (rate-limited) → `start_run` in `asyncio.to_thread` under the workspace lock, then snapshot every session in `run.sessions` (`export_scene` png + `harness.native`) and `close_run(run)`. Response `RunOut`:
  `{run_id, fixture_id, locale, status, problems, provenance, result: {png, verification} | null, previews: [{outcome, origin, fits, violations, png}], preference: {outcome, version} | null}`.
- Verifier gate: when status is `ready` or `applied`, `verify_story(source, snapshot.native, gold)` with `gold = load_gold(fixture, "layout" if ready else outcome)` (missing key → `None`). Failed → status `blocked`, `result.verification = {passed: false, failed: [...], checks: [...]}`; passed → `{passed: true, checks: [{name, passed}]}`. A blocked result is never presented as applied (Review Focus 3).
- `POST /api/campaign/workspaces/{wid}/runs/{rid}/answer` body `{choice: "builtin_shrink_hero"|"builtin_split_two_cards"|"neither", expected_version: int | null}` → `answer(..., current_source_hash=hash of the fixture scene)`; `ValueError` → 409; `PreferenceConflict` → 409 with the active version; then the same verifier gate on the chosen preview's snapshot → `RunOut`.
- `GET /api/campaign/workspaces/{wid}/preferences` → `{scopes: [{scope, active: {outcome, version} | null, history: [{version, outcome, parent}]}]}` for `de`, `en`, `fr`.
- `POST /api/campaign/workspaces/{wid}/preferences/rollback` body `{locale, to_version, expected_version}` → the scope entry; conflict → 409.

- [ ] **Step 1: Failing tests** (all through HTTP, outside the sandbox), each committed result also re-checked in the test with the evaluator: `short_a` → `ready` with `verification.passed`; `de_long_a` → `question` with two fitting previews (PNG data URLs, origin `builtin`); answer shrink → `applied`, passed; `de_long_b` → question with shrink not fitting; answer split with `expected_version: 1` → applied; `de_long_a` again → `applied` with `preference.outcome == "builtin_split_two_cards"`, no previews; `fr_long` → question; `missing_role` → `needs_roles` naming price; answering the same run twice → 409 (Review Focus 2/5); answering after the workspace expired (force `touched` back) → 404 (Review Focus 1); a `teach_before` run → `ready` and passes (it has gold `layout`), while a monkeypatched `load_gold` returning `None` turns a ready run into `blocked` with `matches_gold` failed (Review Focus 3); rollback to v1 returns shrink active; engine `/health/live` sessions 0 after every call (Review Focus 4).
- [ ] **Step 2-4:** run (fail), implement, run (pass).
- [ ] **Step 5: Commit** `feat(api): campaign runs, answers, verifier gate and preferences`.

### Task 4: Campaign tab

**Files:**
- Create: `apps/web/src/CampaignLane.tsx`
- Modify: `apps/web/src/App.tsx` (mode `"Campaign"`, `MODES`, `MODE_HELP`, `HASH` (`campaign`), `pickMode`, backend-missing banner, body switch, footer), `apps/web/src/types.ts` (`CampaignFixture`, `CampaignWorkspace`, `CampaignRun`, `CampaignPreview`, `CampaignVerification`, `CampaignPreferences`), `apps/web/src/styles.css` (`.campaign` lane block)

**Interfaces:** `export function CampaignLane(): JSX.Element`. Layout follows the approved mockup (`https://claude.ai/artifact/3L3fUAacAH16gqmCxgWsj5`):
1. "Teaching example": before/after PNGs side by side, "Learn this layout" button → shows `learned.origin` as a pill (`search`), and the candidate list.
2. "Run on a banner": fixture buttons (thumbnail + id + locale; "development fixture, not held out" note). Result: PNG, status, verifier checks table (name / passed), origin pills (`learned`, `procedure: reference`, `outcome: built-in` when used) as separate items; `blocked` and `needs_roles` render as `callout bad` with the reasons.
3. Question: the sentence "Which tradeoff should this rule make when the offer does not fit?", two preview cards (PNG, "built-in" pill, fits/does-not-fit chip, violations list), buttons "Shrink the product image", "Split across two cards", "Neither (leave unchanged)"; a non-fitting card's button is disabled with the reason.
4. "Saved preferences": per locale active outcome + version, history table, "Roll back" buttons.
All network calls through a local `call<T>(path, body?)` like `SvgLane.tsx`; busy/error state like `SvgLane`.

- [ ] **Step 1:** `npm run lint` and `npm run build:web` pass before the change (baseline).
- [ ] **Step 2:** implement types, component, wiring, styles.
- [ ] **Step 3:** `npm run lint` (0 errors; the pre-existing `App.tsx` warning may remain), `npm run build:web` passes.
- [ ] **Step 4: Commit** `feat(web): campaign tab`.

(The tab's behaviour is tested end to end in Task 5; there is no web unit-test runner in this repo.)

### Task 5: Browser tests

**Files:**
- Modify: `tests/e2e/ui.test.mjs` (add `"Campaign"` to the every-tab list and the no-backend static-copy list)
- Create: `tests/e2e/campaign.test.mjs` (same server bootstrap as `journey.test.mjs`)
- Modify: root `package.json` `test:e2e` script to include the new file

- [ ] **Step 1: Write the failing journey:** open `#campaign`; click "Learn this layout" → pill `search` visible; click `short_a` → result image and "15 of 15 checks passed" text; click `de_long_a` → question with two preview images; click "Shrink the product image" → applied, checks passed, preferences show `de` shrink v1; click `de_long_b` → shrink button disabled with "does not fit"; click "Split across two cards" → applied; preferences `de` v2 split; click `de_long_a` → applied without a question, "Saved preference" shown; click `missing_role` → alert naming `price`; no console errors.
- [ ] **Step 2: Run** `npm run build:web && npm run test:e2e` (outside the sandbox); the campaign test fails before Task 4's tab exists or on any missing behaviour, then passes.
- [ ] **Step 3: Commit** `test(e2e): campaign tab journey`.

### Task 6: Container, records, full check

**Files:**
- Modify: `docker/api.Dockerfile` (`COPY services/engine/vendor services/engine/vendor` and `COPY prompts prompts`), `docs/status.md`, `docs/decisions.md`

- [ ] **Step 1:** confirm `docker/demo.Dockerfile` already ships `services/engine` and `prompts` (no change), add the two COPY lines to `api.Dockerfile`, and `docker compose build api` if Docker is available (report if not run).
- [ ] **Step 2:** full checks: Python suite on 3.12 with `OA_ENGINE_TESTS=1`, `npm test -w services/engine`, `npm run lint`, `npm run build:web && npm run test:e2e`, `lint-imports`, `black --check src tests`. Report exact counts and who ran them.
- [ ] **Step 3:** status (what works, development-only scope, workspace-scoped preferences, no live model) and a decision entry (workspace-namespaced preferences; snapshot-and-close sessions; verifier gate uses development gold).
- [ ] **Step 4: Commit** `docs: plan 9C status and decisions` (and `build: ship engine vendor and prompts in the api image`).
