# Plan 9E: Nemotron in the Campaign lane (role mapping, overflow explanations, native procedures)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nemotron does three jobs in the Campaign lane that deterministic search cannot do well, each with a deterministic check and a labelled fallback, and each measured against that fallback in one capped live run: (1) propose which layer plays which role in an untagged banner, for the owner to confirm; (2) explain the overflow question in plain language, never contradicting the measured facts; (3) write the native apply procedure for Konva and Fabric, accepted only if the independent verifier passes it against gold on a retained and a fresh banner.

**Architecture:** One small model-call helper (`campaign/model.py`) wraps `Provider.complete_json` with the repo's truncation-retry pattern and a per-job token cap. Each job has a pure checker and a deterministic baseline: `heuristic_roles`, `template_explanation`, and the existing reference procedure. Model output is used only if its check passes; otherwise the baseline is used and the response says so (`origin: model | heuristic | template | reference`). The procedure check needs the verifier, so it lives on the evaluator side and is called by the API. Everything is mock-tested; the only paid step is one owner-approved measurement run through the existing `SpendGuard`.

**Tech Stack:** existing providers (`NebiusProvider`, `MockProvider`, `providers/spend.SpendGuard`), Nemotron-3-Super (`nvidia/nemotron-3-super-120b-a12b`, the production model), restricted interpreter, campaign/evaluation packages, FastAPI, React tab.

**Spec:** `docs/superpowers/specs/2026-10-22-promo-story-card-design.md` §7.4 ("Nemotron may propose…, origin tagged"; "Nemotron-written procedures are optional; … identified by source … evaluated separately against the reference procedure. No reference-procedure result is credited to Nemotron.") and §5 (mock default, capped live calls).

## Budget (binding)

- Owner-reported Nebius balance **$12.37** (2026-10-22). The $10 reserve for the live demo and judging stays. Spendable ≈ **$2.37**; the ledger runs ~13% below real spend.
- **This plan's only paid run is capped at $1.00 ledger (~$1.13 real)**, through `SpendGuard` with `results/redesign/budget.json`. Before it, the agent resets `funded_usd` to ledger spend + the owner's latest balance (owner confirms in chat) and asks for approval of the run.
- Estimate (documented in Task 6): role mapping ~9 calls × ~3k tokens, explanations ~3 calls × ~1.5k, procedures 2 backends × ≤3 attempts × ~7k (output-heavy, ~$3.5/M) ≈ **$0.20-0.35 real**. Above the cap, the guard stops the run, and the run is reported as stopped, not as a result.
- All development and CI use `MockProvider`. The public demo keeps `DEMO_MODEL_ENABLED=0` unless the owner turns it on, and the production per-instance cap remains.

## Global Constraints

- Every model output passes its deterministic check before it has any effect; the check never calls the model. A failed check falls back to the baseline, and the response and UI say "Nemotron's proposal was rejected: <reason>; using <baseline>".
- Origins are always visible and separate: roles `model | heuristic | owner`, explanation `model | template`, procedure `model | reference`, plus the existing learned `search` and outcome `builtin`. No single badge.
- The owner confirms roles before a run; a proposal is never applied unconfirmed.
- Model text never decides fit, outcomes, or verification. The explanation is shown beside the measured facts table, not instead of it.
- Prompts live in repo `prompts/` and never include gold outputs or the private set. The badge lane's prompts and `environments/docs.py` stay unchanged.
- Development results only: public fixtures (and derived untagged copies), labelled so. No claim that Nemotron "improves" anything beyond what the measurement table shows.
- Python 3.12, black, conventional commits, explicit-path commits, engine tests outside the sandbox.

## Review Focus

1. A model role mapping that is plausible but wrong in one place (price and headline swapped): the check must catch type/content violations where it can, the owner must see the mapping before running, and a run must never start on an unconfirmed mapping.
2. An explanation that states a number or a role not in the facts ("the headline needs 5 lines" when it needs 4): rejected, template shown.
3. A model procedure that passes the teaching banner but fails a fresh one, or calls a tool outside the allowlist: not accepted; the reference procedure is used and labelled.
4. Budget exhaustion or a provider error mid-run: the run degrades to the baselines with a clear label, never a 500, and never spends past the cap.
5. Model mode off (`DEMO_MODEL_ENABLED=0`, no key): every feature works on its baseline with no error and no model call.

Each is pinned by a test in the owning task.

---

### Task 1: Campaign model-call helper

**Files:** Create `src/open_apprentice/campaign/model.py`; Test `tests/unit/campaign/test_model_call.py`

**Interfaces:**
- `@dataclass ModelResult: parsed: Any | None; error: str | None; tokens: int`
- `async def call_model(provider: Provider, ledger: Ledger, *, role: str, prompt: pathlib.Path, payload: dict, schema: type[StrictModel], max_tokens: int) -> ModelResult`: one `complete_json` call (`CallContext(role=role, category="inference")`), one retry with the repo's `RETRY_NUDGE` on `TruncatedOutput`; `ProviderError`/`BudgetExhausted`/validation failure → `ModelResult(None, "<plain reason>", tokens)`. It never raises, because every caller has a baseline.

- [ ] Tests (mock): parsed result; truncation then success uses exactly 2 calls; `BudgetExhausted` → `error` mentions budget; schema mismatch → error, no exception.
- [ ] Implement, pass, commit `feat(campaign): model-call helper with truncation retry and plain failures`.

### Task 2: Role mapping for untagged banners

**Files:** Create `src/open_apprentice/campaign/roles.py`, `prompts/campaign_roles.md`, `src/open_apprentice/campaign/fixture_data/untagged_*.json` (derived: `short_b`, `de_long_a`, `fr_long` with every `role` removed and the provenance "derived from <id>, roles removed"); Modify `campaign/fixtures.py` (`FIXTURE_IDS` gains the three, kind `untagged`); Test `tests/unit/campaign/test_roles.py`

**Interfaces:**
- `def role_candidates(scene, artboard) -> list[dict]`: the nodes directly in the artboard with type, box, text (truncated to 200 chars), asset id, child types (for groups). This is exactly what the model sees.
- `def check_role_mapping(scene, artboard, mapping: dict[str, str]) -> list[str]`: every role exactly once; types consistent (`background` a rect covering ≥ 90% of the artboard; `brand_mark`/`product_image` images; `headline`/`price`/`legal` text; `cta` a group holding a shape and a text); `price` text contains a digit; ids exist.
- `def heuristic_roles(scene, artboard) -> dict[str, str]`: deterministic baseline (largest rect = background; widest image = product, other image = brand; group = cta; among text, the one with a currency symbol or digit = price, the largest font = headline, the smallest font = legal).
- `async def propose_roles(provider | None, ledger | None, scene, artboard) -> RoleProposal(mapping, origin, problems)`: model first when a provider is given; if the model fails its check, the heuristic is used (origin `heuristic`, problems listed); with no provider, the heuristic.
- `def apply_roles(scene, artboard, mapping) -> dict`: a copy of the scene with roles set. Applied only after owner confirmation (Task 5).

- [ ] Tests: the heuristic recovers the original roles on all three untagged fixtures (it must, or this test documents where it fails); a mock model returning the true mapping is accepted (origin `model`); a mock mapping with price/headline swapped is rejected by `check_role_mapping` (price without a digit) and falls back (Review Focus 1); a mapping missing `legal` is rejected; no provider → heuristic and no call.
- [ ] Implement, pass, commit `feat(campaign): Nemotron role proposals with a checked heuristic fallback`.

### Task 3: Plain-language overflow explanation

**Files:** Create `src/open_apprentice/campaign/explain.py`, `prompts/campaign_explain.md`; Test `tests/unit/campaign/test_explain.py`

**Interfaces:**
- `def overflow_facts(run: CampaignRun) -> dict`: from `provenance["base_violations"]` and the previews: per violating role its kind and measured numbers (text height vs frame, line counts), and per built-in whether it fits.
- `def template_explanation(facts) -> str`: deterministic sentence(s).
- `def check_explanation(text, facts) -> list[str]`: ≤ 320 characters; every number in the text appears in the facts (after rounding to integers); every role or outcome named exists in the facts; every violating role is mentioned; no claim that a non-fitting outcome fits (keyword check against "does not fit" outcomes).
- `async def explain(provider | None, ledger | None, facts) -> Explanation(text, origin, problems)`.

- [ ] Tests: the template passes its own check; a mock explanation with a wrong line count is rejected and the template is used (Review Focus 2); one naming a role not in the facts is rejected; one claiming shrink fits when it does not is rejected; no provider → template.
- [ ] Implement, pass, commit `feat(campaign): checked plain-language overflow explanations`.

### Task 4: Model-written native procedures

**Files:** Create `src/open_apprentice/campaign/model_procedures.py`, `prompts/campaign_procedure.md` (the campaign tool contract for Konva and Fabric, the `plan_inputs` schema, and the reference program as one worked example), `src/open_apprentice/evaluation/campaign_procedure_check.py`; Modify `campaign/procedures.py` (`apply_plan(session, plan, program=APPLY_PLAN, origin=ORIGIN)`), `campaign/run.py` (`start_run(..., procedure: tuple[list, str] | None = None)` records `procedure_origin`), `pyproject.toml` (forbid the new evaluation module in agent packages); Test `tests/unit/campaign/test_model_procedures.py`, `tests/integration/test_campaign_procedure_check.py`

**Interfaces:**
- `async def propose_procedures(provider, ledger, backend, failures: list[str] | None = None) -> list[list]`: ≤ 2 candidate programs per call; each must pass `validate_program(program, APPLY_TOOLS)` locally before it is even tried (Review Focus 3).
- Evaluator side: `def check_procedure(program, backend, engine_url, token) -> ProcedureCheck(passed, cases: list[{fixture, outcome, passed, failed_checks}])`. It runs the program on `teach_before` (layout, the retained case) and `short_b` (layout) plus the `de_long_a` split (fresh cases) on that backend, verifying each against gold.
- Acceptance policy: up to 3 attempts per backend (the first plus up to 2 with the failing cases fed back); the first passing program is accepted (origin `model`); otherwise the reference program (origin `reference`) with the attempts reported.

- [ ] Tests: unit (mock), a program calling a non-allowlisted tool is filtered out before any engine use; feedback includes the failed checks. Integration (engine): the reference program passes `check_procedure` on both backends (sanity); a mock "model" program identical to the reference passes and is labelled `model`; a mock program that hard-codes the teaching banner's ids passes nothing and the reference is used (Review Focus 3); `start_run` with an accepted model procedure records `procedure_origin: "model"`.
- [ ] Implement, pass, commit `feat(campaign): Nemotron-written native procedures, verified before use`.

### Task 5: API and Campaign tab

**Files:** Modify `src/open_apprentice/api/campaign.py`, `apps/web/src/CampaignLane.tsx`, `apps/web/src/types.ts`; Test `tests/integration/test_campaign_api.py`, `tests/e2e/campaign.test.mjs`

**Interfaces:**
- Model availability = `app.state.provider` set (`DEMO_MODEL_ENABLED=1`), wrapped per workspace in a `Ledger` capped at 60k tokens; the existing global demo spend meter applies.
- `POST /workspaces/{wid}/roles` `{fixture_id}` → `{mapping, origin, problems, candidates}`; `RunIn.roles: dict[str,str] | None` (required for untagged banners; validated with `check_role_mapping`, 422 on problems; recorded as origin `owner` in provenance).
- A `question` response gains `explanation: {text, origin, problems}`.
- `POST /workspaces/{wid}/procedures` `{backend}` → `{origin, attempts: [{passed, cases}], accepted}`; later runs on that backend use the accepted procedure.
- Tab: untagged banners show a "Propose roles" step (a table of layer → role, editable selects, "Confirm roles"); the run button stays disabled until confirmed (Review Focus 1). The question shows the explanation with its origin pill above the facts. A "Write the native procedure with Nemotron" button per engine shows attempts and the accepted origin. With model mode off, the buttons say "Nemotron is off on this server" and the baselines run (Review Focus 5).

- [ ] Tests (mock provider via the app's provider hook; engine-backed): untagged run refused without roles (422), works after confirmation with model-proposed roles; explanation present with origin; procedure endpoint accepts a mock correct program and the next run records `procedure_origin: model`; with no provider all three return baselines; a provider raising `BudgetExhausted` degrades to baselines with a label, never 5xx (Review Focus 4). e2e: untagged banner → propose → confirm → run passes the checks (mock mode).
- [ ] Implement, `npm run lint`, `npm run build:web`, e2e, commit `feat: Nemotron role proposals, explanations and procedures in the Campaign tab`.

### Task 6: One capped live measurement (owner-approved)

**Files:** Create `src/open_apprentice/evaluation/campaign_nemotron.py`; Modify `cli.py` (`oa eval campaign-nemotron --cap-usd 1.00 --live`); Output `docs/evaluation/campaign_nemotron.md`

**Interfaces:** `def measure(provider_factory, engine_url, token) -> dict`:
- roles: on the 3 untagged fixtures plus all 6 tagged banners with roles stripped (9 banners); exact-match accuracy of the model versus the heuristic, and check-rejection counts;
- explanations: on the 3 overflowing banners (`de_long_a`, `de_long_b`, `fr_long`); check pass rate versus the template;
- procedures: per backend, attempts, accepted origin, and cases passed.

Plus tokens, ledger USD, model id, and date. Without `--live` it runs on the mock (so the table format is tested).

- [ ] Step 1: mock run in CI produces the table; unit test on its shape.
- [ ] Step 2 (paid; **ask the owner first**): confirm the current balance, set `funded_usd`, state the estimate, and run with `--live --cap-usd 1.00` under `caffeinate -i`. Commit the table as produced (failures and a stopped run included), and report the spend and the new balance to the owner.

### Task 7: Records and full check

**Files:** `docs/status.md`, `docs/decisions.md`, `README.md` (Campaign paragraph: what Nemotron does there, the measured table, the fallbacks).

- [ ] Full checks (Python with `OA_ENGINE_TESTS=1`, engine, lint, build + e2e, lint-imports, black); counts and who ran them.
- [ ] README states only what the measurement table shows (e.g. "Nemotron matched the owner's roles on N of 9 development banners; the heuristic on M"), development fixtures, no generalization.
- [ ] Commit `docs: plan 9E status, decisions and README`.
