# Plan 9B: Campaign tools, layout rule, learner, overflow question and preference

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From one taught banner→story pair, the apprentice learns the base layout, applies it to other banners on real Konva through a checked procedure, detects overflow from the real renderer, offers the two built-in outcomes as applied previews, applies the owner's choice, and saves it as a scoped, versioned preference that the next matching banner reuses; every development fixture's result matches its gold under the 9A verifier.

**Architecture:** Konva gains the mutating tools the procedures need. `rules.py` gets an opt-in campaign dialect (new emit kinds, a `facts` root, an `ask` statement) evaluated by a `_Run` subclass in `campaign/layout_rule.py`, so the ~15 existing rule callers are untouched. The learner turns the role-matched teaching diff into a rule (deterministic, optional Nemotron candidates checked the same way). The rule's targets become a `LayoutPlan`; one reference JSON-AST procedure applies any plan through `skills/interpreter.py`. The built-in shrink/split outcomes are labelled Python plan transforms. `campaign/run.py` orchestrates scratch sessions, fit observation, the question, the answer and the preference store.

**Tech Stack:** Konva engine (`services/engine`), Python 3.12, existing `rules.py`, `skills/interpreter.py`, `environments/client.EngineSession`, `storage.Store`, `providers.MockProvider`.

**Spec:** `docs/superpowers/specs/2026-10-22-promo-story-card-design.md` (§7.2-7.6, §9 steps 4-7). Plan 9A (merged) supplies scene types, `observe_fit`, `campaign.limits/scene/fixtures`, `evaluation.campaign_verifier/campaign_gold`.

**Plan 2 of 4.** 9C: Campaign UI tab + API routes (verifier-gated commit, PNG previews, the 9A vendor-path prerequisite). 9D: Fabric contract and parity, private sealed set.

## Global Constraints

- Everything from Plan 9A's Global Constraints still holds (limits, roles, writable/non-writable fields, exact copy, fonts, import contracts, explicit-path commits, Python 3.12, engine tests run outside the sandbox).
- Built-in outcomes carry origin `"builtin"`; the learned layout carries `"search"` or `"model"`; the apply procedure carries `"reference"`. These strings appear in every result and preference record; nothing built-in is ever labelled learned or model.
- New card-2 nodes are named `<source id>-2` (9A verifier rule). The source artboard is removed once empty; result artboards are `story-1` (x 0) and `story-2` (x 1180, sequence 2).
- Preference scope key is `promo_card/9:16/overflow/<locale>`; another locale asks again.
- `PROVIDER_MODE=mock` in every test; no live Nemotron call in this plan.
- `open_apprentice.campaign` never imports `open_apprentice.evaluation`; tests may.

## Ruling carried from the spec

- **No offer group.** Spec §2 says headline/price/CTA are "regrouped into one offer group", but the approved 9A gold outputs (authoritative evidence) keep them as direct children of the card. Reading order comes from positions and z. Recorded in `docs/decisions.md` in Task 8. Cost if wrong: one `group_nodes` call in the plan and a gold edit.

## Review Focus

1. A banner whose preference says "shrink" but whose copy still overflows after shrinking (de_long_b): it must ask again with shrink shown "does not fit", never apply a half-fitting card.
2. Answering a question twice, or answering a stale run (source changed since the previews): the second answer is refused, the first result stands.
3. A model-proposed rule that reproduces the teaching pair but writes a non-writable field (text, link, asset) or targets a node outside the scene: rejected by validation, never applied.
4. A source with a missing or doubled role: the run stops with `needs_roles` and the named problems before any engine session is opened.
5. An engine tool error midway through applying a plan (e.g. a limit): the scratch session is discarded and the run reports `failed` with the tool error; the source scene is never mutated.

Each is pinned by a test in the owning task.

---

### Task 1: Konva campaign tools

**Files:**
- Modify: `services/engine/src/dispatcher.browser.js` (new tools, widened `resize_node`/`set_style`, `MUTATING`)
- Modify: `services/engine/src/engine.js` (`PUBLIC_TOOL_SCHEMAS.konva.tools`)
- Modify: `src/open_apprentice/environments/docs.py` (Konva doc string names the new tools)
- Test: `services/engine/test/campaign.test.js`

**Interfaces (Produces, all mutating, all on Konva only):**
- `create_artboard({artboard_id, x, y, width, height, format, safe, sequence})` → publicProps; `format` ∈ `"9:16"|"16:9"`; id must be fresh; respects `MAX_NODES`.
- `remove_artboard({artboard_id})` → `{removed}`; refuses (`INVALID_ARGUMENT`) if the artboard has children.
- `reparent_nodes({node_ids, parent_id})` → `{moved}`; target must be an artboard or group; keeps world position (same as `group_nodes`).
- `set_order({node_id, z})` → publicProps; `zIndex(z)` within the parent, `z` an integer in range.
- `resize_node` also accepts `shape`, `text`, `image` (never `group`/`artboard`).
- `set_style` per-kind allowlist: rect/shape `fill, stroke, strokeWidth, opacity, cornerRadius`; text `fontSize` only (≥ 1); image nothing.
- `fit_image_contain({node_id, x, y, width, height})` → publicProps; places the image at the largest size with its natural aspect inside the box, centred; never touches `crop`.

- [ ] **Step 1: Write failing tests** (one per tool plus): `create_artboard` then `nativeState` shows the artboard with format/safe/sequence; `remove_artboard` on a non-empty artboard → `INVALID_ARGUMENT`; `reparent_nodes` moves a text node into a new artboard keeping its world position; `set_order` changes `z`; `resize_node` on a text node changes its frame; `set_style` on text with `fill` → `INVALID_ARGUMENT` (text fill is non-writable) and with `fontSize: 44` → ok; `set_style` on shape `cornerRadius: 16` → ok; `fit_image_contain` of the 1:1 hero into a 936×720 box → 720×720 at x+108; every new tool bumps the revision.
- [ ] **Step 2: Run** `npm test -w services/engine`; new tests fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npm test -w services/engine`; all pass (existing badge/drift/Fabric tests unchanged).
- [ ] **Step 5: Commit** `feat(engine): campaign layout tools for Konva`.

### Task 2: Campaign rule dialect and evaluator

**Files:**
- Modify: `src/open_apprentice/concepts/rules.py` (`validate_rule(body, *, campaign: bool = False)`)
- Modify: `src/open_apprentice/concepts/symbolic.py` (new kinds/statements raise `Unsupported`)
- Create: `src/open_apprentice/campaign/layout_rule.py`
- Test: `tests/unit/campaign/test_layout_rule.py`; existing `tests/unit/test_rules_concrete.py` must stay green.

**Interfaces:**
- With `campaign=True` only, the validator additionally accepts:
  - emit kind `place`: required `x, y, w, h`; optional `parent` (string literal), `z` (int);
  - emit kind `style`: optional `fontSize`, `cornerRadius` (at least one);
  - emit kind `fit_image`: required `x, y, w, h` (contain-fit box);
  - ref root `facts` with exactly `facts.output_format` (string), `facts.overflows` (bool);
  - statement `{"ask": ["builtin_shrink_hero", "builtin_split_two_cards"]}` (exactly these names).
  With `campaign=False` all of these are rejected exactly as today.
- `campaign/layout_rule.py`:
  - `@dataclass Target: node_id: str; x, y, w, h: Fraction | None; parent: str | None; z: int | None; font_size: Fraction | None; corner_radius: Fraction | None; contain: bool`
  - `@dataclass LayoutOutcome: targets: dict[str, Target]; ask: tuple[str, ...] | None`
  - `def objects_for_rule(scene: dict, artboard_id: str) -> list[dict]` — role nodes of the artboard plus CTA children with pseudo-roles `cta/shape`, `cta/text`; parent-local geometry; every field as Fraction.
  - `def evaluate_layout(body: list, objects: list[dict], facts: dict) -> LayoutOutcome` — canvas is always `{w: 1080, h: 1920}`; reaching `ask` stops evaluation and returns the outcome with `ask` set and no targets.
  - `def wrap_learned(body: list) -> list` — the fixed, built-in wrapper `if output_format == "9:16" then (if overflows then ask(...) else body)`; unknown formats emit nothing.

- [ ] **Step 1: Write failing tests:** `campaign=True` accepts each new construct and `campaign=False` rejects each with `RuleError`; `place` with a field outside its allowlist (e.g. `text`) is rejected; `evaluate_layout(wrap_learned(body), objs, {"output_format": "9:16", "overflows": False})` returns the body's targets; with `overflows: True` returns `ask == ("builtin_shrink_hero", "builtin_split_two_cards")` and no targets; with `"16:9"` returns no targets and no ask; symbolic compilation of a campaign rule raises `Unsupported`; `objects_for_rule(load_fixture("short_a")["scene"], "banner")` yields 7 roles plus `cta/shape`, `cta/text`.
- [ ] **Step 2: Run** `PYTHONPATH=src:. $V/python -m pytest -q tests/unit/campaign/test_layout_rule.py tests/unit/test_rules_concrete.py`; new tests fail.
- [ ] **Step 3: Implement** (subclass `rules._Run`, override statement dispatch for `ask` and `emit` for the new kinds).
- [ ] **Step 4: Run** the same tests plus `tests/unit` whole; pass.
- [ ] **Step 5: Commit** `feat(campaign): layout rule dialect with facts, ask and placement emits`.

### Task 3: Layout plan and reference apply procedure

**Files:**
- Create: `src/open_apprentice/campaign/plan.py`, `src/open_apprentice/campaign/procedures.py`
- Test: `tests/unit/campaign/test_plan.py`, `tests/integration/test_campaign_apply.py`

**Interfaces:**
- `plan.py`:
  - `@dataclass LayoutPlan: source_artboard: str; artboards: list[dict]` (each `{id, x, sequence}`, 1080×1920, `format "9:16"`, `safe` = `limits.SAFE`)`; clones: list[tuple[str, str]]` (source id, new id)`; targets: list[Target]; origin: str`
  - `def plan_from_layout(outcome: LayoutOutcome, source_artboard: str, origin: str) -> LayoutPlan` — one artboard `story-1`, every role target parented to it unless the target says otherwise; CTA children keep their group parent.
- `procedures.py`:
  - `APPLY_PLAN: list` — the reference JSON-AST program (origin `"reference"`): create artboards, clone, reparent, then per target `move_node`, `resize_node` or `fit_image_contain`, `set_style`, `set_order`; finally `remove_artboard(source)`. Must validate under `interpreter.validate_program` with the tool allowlist below and stay within its caps for 2 cards.
  - `APPLY_TOOLS = frozenset({...})` — exactly the tools the program calls.
  - `def plan_inputs(plan: LayoutPlan) -> dict` — JSON-safe inputs (Fractions → float).
  - `def apply_plan(session: EngineSession, plan: LayoutPlan) -> dict` — runs `run_program(APPLY_PLAN, plan_inputs(plan), session.tools(APPLY_TOOLS))`; returns `{"origin": "reference", "actions": n}`; any `EngineToolError` propagates.

- [ ] **Step 1: Write failing tests:** unit: `APPLY_PLAN` validates against `APPLY_TOOLS`; `plan_inputs` is JSON-serialisable. Integration (`engine_url`): build the teaching plan directly from the teach_after fixture's boxes (a hand-built `LayoutOutcome`), open a session on `teach_before` with `EvaluatorHarness`, `apply_plan`, read `native`, and `verify_story(teach_before, native, load_gold("teach_before","layout")["scene"])` passes. A plan with a target id absent from the scene raises `EngineToolError` (Review Focus 5 at procedure level).
- [ ] **Step 2: Run**; fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** unit + integration (outside the sandbox); pass.
- [ ] **Step 5: Commit** `feat(campaign): layout plan and reference apply procedure`.

### Task 4: Learner for the base layout

**Files:**
- Create: `src/open_apprentice/campaign/learn.py`, `src/open_apprentice/prompts/campaign_layout.md`
- Test: `tests/unit/campaign/test_learn.py`

**Interfaces:**
- `@dataclass CandidateReport: origin: str ("search"|"model"); rule: list; reproduces: bool; reason: str`
- `@dataclass Learned: rule: list` (the learned body, unwrapped)`; origin: str; candidates: list[CandidateReport]`
- `class LearnError(Exception)` with `.reason`.
- `async def learn_layout(before: dict, after: dict, *, provider: Provider | None = None, ledger: Ledger | None = None) -> Learned`
  - Role-match `before`/`after` with `role_map` (RoleError propagates); the after scene must have exactly one `9:16` artboard.
  - Search candidate: per role (and CTA pseudo-roles) a `place`/`fit_image` emit of the after box as constants, `style` emits for `fontSize`/`cornerRadius` that differ from the before scene, inside a `for_each` over objects keyed on `get(o,"role")`. Deterministic.
  - Model candidates (only when `provider` is given): one `complete_json` call, role `"campaign_layout"`, category `"inference"`, output schema `{candidates: [{rule: list, summary: str}]}` (≤ 3), prompt from `prompts/campaign_layout.md` with the role-matched before/after boxes.
  - Every candidate: `validate_rule(wrap_learned(rule), campaign=True)`, then `evaluate_layout` on `objects_for_rule(before)` must reproduce the after scene's role boxes, font sizes and corner radii exactly; anything else is rejected with a reason (Review Focus 3).
  - Choice: the search candidate when it reproduces; otherwise the first reproducing model candidate; otherwise `LearnError`. All candidates are reported with origin.

- [ ] **Step 1: Write failing tests:** search-only learning on the teaching pair reproduces teach_after; applying the learned rule to `objects_for_rule(short_a)` gives the gold `short_a` boxes (role-matched, different ids); a `MockProvider` model candidate identical in behaviour is reported `reproduces=True, origin="model"` while the search candidate is chosen; a model candidate emitting `text` is rejected by validation; one that targets a box 4 px off is rejected as not reproducing; `missing_role` as `before` raises `RoleError` without calling the provider (`provider.calls == []`).
- [ ] **Step 2: Run**; fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `tests/unit/campaign`; pass.
- [ ] **Step 5: Commit** `feat(campaign): learn the base story layout from one teaching pair`.

### Task 5: Built-in overflow outcomes

**Files:**
- Create: `src/open_apprentice/campaign/builtins.py`
- Test: `tests/unit/campaign/test_builtins.py`

**Interfaces:**
- `BUILTINS = ("builtin_shrink_hero", "builtin_split_two_cards")`; `ORIGIN = "builtin"`.
- `def shrink_hero(base: LayoutPlan) -> LayoutPlan` — hero width → `limits.MIN_HERO_W`, aspect kept, centred horizontally, same top; headline top = hero bottom + 40, headline bottom unchanged; everything else unchanged; origin `"builtin"`.
- `def split_two_cards(base: LayoutPlan) -> LayoutPlan` — artboards `story-1` (x 0, seq 1) and `story-2` (x 1180, seq 2); clones `(<bg>, <bg>-2)`, `(<logo>, <logo>-2)`. Card 1: brand mark and hero at their base boxes, headline at its base top, bottom at `1920 - SAFE.bottom`. Card 2: background `<bg>-2` covering the card (0, 0, 1080, 1920), brand mark `<logo>-2` at the base logo box, price top 800, CTA top = price bottom + 32, legal bottom-anchored at `1920 - SAFE.bottom` with height 320; widths and font sizes from the base plan.

- [ ] **Step 1: Write failing tests:** for `de_long_a`, `shrink_hero(base)` targets equal the `de_long_a/shrink` gold boxes for every role; `split_two_cards(base)` targets equal the `de_long_a/split` gold boxes (both cards, including `-2` ids) — where `base` comes from the Task 4 learned rule applied to `de_long_a`; both plans have origin `"builtin"`; neither function mutates its input.
- [ ] **Step 2: Run**; fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run**; pass.
- [ ] **Step 5: Commit** `feat(campaign): built-in shrink and split outcomes`.

### Task 6: Preference store

**Files:**
- Create: `src/open_apprentice/campaign/preferences.py`
- Test: `tests/unit/campaign/test_preferences.py`

**Interfaces:**
- `def scope_key(locale: str) -> str` → `"promo_card/9:16/overflow/<locale>"`.
- `@dataclass Preference: scope: str; outcome: str; version: int; parent: int | None; provenance: dict`
- `class PreferenceConflict(Exception)`
- `class PreferenceStore(store: Store)`:
  - `get(scope) -> Preference | None` (the active version);
  - `set(scope, outcome, provenance, expected_version: int | None) -> Preference` — appends a version (`campaign/preferences/<scope>/v<n>.json`), moves the pointer with compare-and-set; `PreferenceConflict` if the active version is not `expected_version`; `outcome` must be in `BUILTINS`;
  - `rollback(scope, to_version, expected_version) -> Preference` — pointer move, history kept;
  - `history(scope) -> list[Preference]`.

- [ ] **Step 1: Write failing tests** on `LocalStore(tmp_path)`: set then get; second set with stale `expected_version` → `PreferenceConflict`; rollback restores the earlier outcome and history keeps both; unknown outcome → `ValueError`; `scope_key("de") != scope_key("fr")`.
- [ ] **Step 2-4:** run (fail), implement, run (pass).
- [ ] **Step 5: Commit** `feat(campaign): versioned overflow preferences`.

### Task 7: Run orchestration, question and answer

**Files:**
- Create: `src/open_apprentice/campaign/run.py`
- Test: `tests/unit/campaign/test_run_states.py`, `tests/integration/test_campaign_run.py`

**Interfaces:**
- `OpenSession = Callable[[dict], EngineSession]` (the caller decides agent route or evaluator harness).
- `@dataclass Preview: outcome: str; origin: str; session_id: str; fits: bool; violations: list[dict]`
- `@dataclass CampaignRun: run_id: str; fixture_locale: str; status: str` (`ready | question | applied | unchanged | needs_roles | unsupported_format | failed`)`; source_hash: str; result_session: str | None; previews: dict[str, Preview]; preference: Preference | None; problems: list[str]; provenance: dict`
- `def start_run(source: dict, locale: str, learned: Learned, open_session: OpenSession, prefs: PreferenceStore) -> CampaignRun`
  1. `role_map` on the source artboard; `RoleError` → `needs_roles` with problems, no session opened (Review Focus 4).
  2. Evaluate `wrap_learned(learned.rule)` with `overflows=False`; no targets → `unsupported_format`.
  3. Open a scratch session, `apply_plan(base)`, `observe_fit(story-1, fit_limits())`. Fits → `ready` with `result_session`.
  4. Overflow → evaluate with `overflows=True` (ask). If a preference exists for `scope_key(locale)`: build that built-in plan in a fresh session, observe every card; fits → `applied` with the preference recorded in provenance; does not fit → fall through to the question with that outcome marked not fitting (Review Focus 1).
  5. Question: one scratch session per built-in, each observed; `status = question`, `previews` filled.
  Any `EngineToolError` → close sessions, `failed` with the error (Review Focus 5).
- `def answer(run: CampaignRun, choice: str, prefs: PreferenceStore, expected_version: int | None) -> CampaignRun` — only from `question`; `"neither"` → `unchanged` (no preference written); a built-in whose preview fits → `applied`, `result_session` = that preview's session, preference set with provenance (`run_id`, `source_hash`, previews' fits/violations, choice, origins); choosing a non-fitting preview → `ValueError`; a second answer → `ValueError` (Review Focus 2).
- `provenance` always carries `learned_origin`, `procedure_origin: "reference"`, and the outcome origin `"builtin"` when a built-in was used.

- [ ] **Step 1: Write failing tests.** Unit (fake sessions are not used; state rules only): answering twice raises; `neither` writes no preference; `needs_roles` opens no session (an `open_session` that raises if called). Integration (`engine_url`, `open_session` built on `EvaluatorHarness.open_session`, learned from the teaching pair, `LocalStore(tmp_path)`), each result checked with `verify_story(source, harness.native(result_session), gold)`:
  - `short_a`, `short_b` → `ready`, verify against `layout` gold passes;
  - `de_long_a` → `question`; shrink and split previews both fit; `answer("builtin_shrink_hero")` → `applied`, verifies against `de_long_a/shrink` gold; preference `de` = shrink v1;
  - `de_long_b` with that preference → `question` (shrink does not fit), shrink preview `fits=False`; `answer("builtin_split_two_cards", expected_version=1)` → verifies against `de_long_b/split`; preference v2 = split;
  - a fresh `de_long_a` run with preference split → `applied` without a question, verifies against `de_long_a/split`;
  - `fr_long` with the `de` preference → `question`;
  - `missing_role` → `needs_roles` naming `price`.
- [ ] **Step 2: Run**; fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** unit + integration (outside the sandbox); pass.
- [ ] **Step 5: Commit** `feat(campaign): run orchestration with overflow question and preference reuse`.

### Task 8: Records and full check

**Files:** `docs/status.md`, `docs/decisions.md` (the no-offer-group ruling; origins vocabulary; preference scope).

- [ ] **Step 1:** full Python suite on 3.12 with `OA_ENGINE_TESTS=1`, `npm test -w services/engine`, `lint-imports`, `black --check src tests`; report exact counts and that the agent ran them outside the sandbox.
- [ ] **Step 2:** update status (what works, what is development-only, what 9C needs: verifier-gated commit route, PNG previews, vendor path in the API image) and add the decision.
- [ ] **Step 3: Commit** `docs: plan 9B status and decisions`.
