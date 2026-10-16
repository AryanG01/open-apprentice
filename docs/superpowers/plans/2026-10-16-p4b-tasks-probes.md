# Cloud Tasks and Generated Probes Implementation Plan (Plan 4B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- When the batch documents cannot tell the surviving rules apart, the apprentice generates a small probe document (a resized node, an
  obstacle across a placement boundary, a narrower page). It renders the probe in the locked engine, checks that the render matches
  the geometry it selected, and asks on it.
- Background work can run through Cloud Tasks, with an OIDC-verified internal route, instead of the in-process thread pool.

**Architecture:**
- **Probes:**
  - Probe generation is pure (`teaching/probes.py`): scene edits plus a counted evaluation of every candidate, under the spec's limits
    (≤ 128 probes per round, 5,000,000 evaluator statements per round).
  - The step policy emits a new action, `RenderProbe`. The executor hands it to an injected `probe_renderer` that the API supplies. The
    renderer patches the source `.drawio`, renders it, re-measures it, and accepts the probe only if the measured geometry matches the
    selection geometry within 0.5.
  - An accepted probe is registered as a `probe` scene, and the existing ChooseOutput path asks on it.
- **Cloud Tasks:**
  - Background work becomes serialisable `Job`s.
  - `LocalDispatcher` runs them in-process, as today. `CloudTasksDispatcher` enqueues an HTTP task with an OIDC token to
    `POST /internal/tasks/{task_id}`.
  - That route verifies the token's audience and service account, takes a task claim (duplicate delivery returns the stored status),
    and runs the job under the same per-key lock.

**Tech Stack:** Python 3.12, existing `teaching`/`drawio`/`api.v2`; `google-auth` (already installed, 2.62) for OIDC verification;
**new dependency** `google-cloud-tasks` (pinned) for enqueueing.

**Spec:** `docs/superpowers/specs/2026-10-15-teach-correct-reuse-design.md`:
- section 4, rule 3: probe families, limits, usable-probe definition, score, tie-break, "generated probes are rendered and must match
  their selection geometry before display";
- section 3.7, budgets;
- section 8: `POST /internal/tasks/{action_id}`;
- section 10: staging Cloud Tasks dispatch.

## Global Constraints

- The step function stays pure: no I/O, the log is its only input. Probe rendering happens only in the executor through the injected
  renderer, and its result enters as events.
- **Probe limits** (spec 4 rule 3):
  - at most 128 generated probes per round, aggregate evaluator budget 5,000,000 statements per round (`StepConfig.max_evaluations`);
  - usable probe: 2–4 exact output groups pairwise separated per 3.6 (> 1 unit in at least one coordinate);
  - score: the number of candidate pairs the question separates;
  - tie-break, in order: batch document before probe, then fewer changed attributes, then fewer objects, then stable order;
  - a probe search that runs out of budget records `budget_exhausted`, which is never reported as "one behaviour" and never permits a
    commit.
- **Probe families in 4B:**
  - included: **node resize**, **obstacle across a placement boundary**, **narrower canvas**;
  - deferred, as allowed by scope cut (3) "fewer probe families": **observable role flip** and **small fresh arrangement**. The audit
    records this;
  - probes never change text.
- A probe is displayed only after its render matches its selection geometry. A mismatch or refusal is recorded as `ProbeRendered(ok=false,
  reason)`, and the probe is never shown.
- Probes are off unless the executor has a renderer (`StepConfig.probes=True` is set by the API only). Existing teaching tests keep
  their behaviour.
- `/internal/tasks/{task_id}`:
  - only Cloud Tasks may call it: an OIDC token whose audience is the configured service URL and whose `email` is the configured
    service account (`email_verified` true). Anything else gets 403, and the route is absent unless `OA_DISPATCH=cloudtasks`;
  - duplicate delivery returns the stored status and never re-runs a finished job;
  - before running, the job re-checks cancellation, and the executors' own claims and budget checks still apply.
- No GCP resource is created by this plan. The staging dispatch check is written and tested against a fake client; running it needs
  the owner's approval of the updated `docs/deploy_staging_proposal.md`.
- Python 3.12, black, ruff, type hints; no `eval`/`exec`. The `teaching` package must not import `drawio`, `api`, or the evaluator. The
  probe renderer lives in `api/v2`.

## Review Focus

1. **Probe geometry that cannot be rendered as selected:** a probe whose rendered measurement differs from its selected scene by more
   than 0.5 (for example, a node resize that wraps a node's text and changes the label it measures) is never shown. The session
   continues as if that probe did not exist. (Task 4 and Task 6 tests.)
2. **Budget exhaustion:** with a tiny `max_evaluations`, the search stops, records `budget_exhausted`, and the session can neither commit
   nor claim "no distinguishing alternative found". (Task 3 test.)
3. **Forged internal call:** a request to `/internal/tasks/…` without a token, with a token for another audience, or with a token from
   another service account is refused (403) and runs nothing. (Task 7 test.)
4. **Duplicate task delivery:** the same task delivered twice, or concurrently, runs the job once. The second delivery returns the first
   one's status. (Task 7 test.)
5. **Probe document ownership:** a probe document is owned by the session's owner, never listed among that owner's imported documents,
   and another owner gets 404 for its preview and scene. (Task 6 test.)

---

### Task 1: Counted rule evaluation

**Files:** Modify `src/open_apprentice/concepts/rules.py`, `src/open_apprentice/teaching/step.py`; Test `tests/unit/test_rules_counted.py`

**Interfaces:**
- `concepts.rules.evaluate_rule_counted(body, objects, canvas) -> tuple[dict, int]`: the same result as `evaluate_rule`, plus the number of statements executed (the evaluator's existing `steps` counter). `evaluate_rule` becomes `evaluate_rule_counted(...)[0]`.
- `teaching.step.run_output_counted(rule, scene) -> tuple[Optional[Output], int]` (0 statements when the rule errors before running).

- [ ] Test: for a two-label scene and the right-gap rule, `evaluate_rule_counted` returns the same output as `evaluate_rule` and a positive count; a nested-loop rule over 3 objects reports more statements than over 2. RED (ImportError) → implement → GREEN → commit `feat(concepts): counted rule evaluation for the probe budget`.

---

### Task 2: Pure probe generation

**Files:** Create `src/open_apprentice/teaching/probes.py`, `tests/unit/teaching/test_probes.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class Probe:
    probe_id: str                      # codec.digest of (source_scene_id, family, edits, canvas_w)
    source_scene_id: str               # a registered demo/batch scene
    family: str                        # "node_resize" | "obstacle" | "narrow_canvas"
    edits: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]  # cell id -> ((attr, exact value), ...), attrs x|y|w|h
    canvas_w: Optional[str]            # exact rational as string, or None
    scene: dict                        # the selection geometry (source scene with the edits applied)
    changed_attrs: int

def candidate_probes(scenes: dict[str, dict], roles: dict[str, str], cands: list[dict], limit: int = 128) -> list[Probe]: ...

@dataclass(frozen=True)
class ProbeSearch:
    best: Optional[Probe]
    groups: list                        # output groups on best.scene (as step._groups returns)
    statements: int
    outcome: str                        # "found" | "completed_no_disagreement" | "budget_exhausted" | "candidates_failed_on_inputs"

def search(probes: list[Probe], cands: list[dict], budget: int) -> ProbeSearch: ...
```

- The **families** are deterministic edits of each demo/batch scene:
  - **node_resize:** each node attached to a movable label gets its width × {0.5, 2} and its height × {0.5, 2}, kept inside the page.
  - **obstacle:** for each candidate pair whose outputs on the source scene differ, move one *other* node (not the label's own node) so
    its box overlaps the first candidate's placement of that label, and nothing else.
  - **narrow_canvas:** the page width becomes the rightmost object edge, plus 1 for each label output that would cross it.

  Any probe whose edited scene puts an object outside its page, or makes two nodes overlap, is dropped. Probes are capped at `limit`, in
  family order, then source scene id, then cell id.
- **Search:**
  - evaluate every candidate on each probe with `run_output_counted`, summing statements;
  - stop when the sum would exceed `budget` (outcome `budget_exhausted`);
  - group outputs with the step's grouping and keep usable probes (2–4 groups pairwise separated by more than 1);
  - pick the best by (pairs separated desc, changed attrs asc, object count asc, probe_id);
  - if any candidate fails on a probe input, the outcome is `candidates_failed_on_inputs` unless a usable probe was also found;
  - with no usable probe and no failures, the outcome is `completed_no_disagreement`.

- [ ] Tests (`tests/unit/teaching/test_probes.py`):
  - Two candidates that agree on the batch scene but disagree when the node is wider ("right of node, gap 12" vs "fixed x = 200"):
    `search` finds a `node_resize` probe with 2 usable groups, and its scene differs from the source only in that node's width.
  - Probes never move text, never leave the page, and are capped at the limit.
  - `budget=1` gives `budget_exhausted`, with `best` None.
  - Identical candidates give `completed_no_disagreement`.
  - Probe ids are stable across calls.

  RED → implement → GREEN → commit `feat(teaching): pure probe generation and budgeted disagreement search`.

---

### Task 3: Step policy uses probes when batch documents cannot separate the rules

**Files:** Modify `src/open_apprentice/teaching/step.py`, `src/open_apprentice/teaching/constraints.py` (role `probe` scenes count as searched scenes); Test `tests/unit/teaching/test_step_probes.py`

**Interfaces:**
- `StepConfig` gains `probes: bool = False`, `max_probes: int = 128` (`max_evaluations` already exists).
- New action `RenderProbe(action_id: str, probe: Probe)`.
- **Events consumed:**
  - `ProbeRendered {action_id, probe_id, ok: bool, reason?: str, scene_id?: str}`, origin system;
  - `SceneRegistered {…, role: "probe", probe_id}` for accepted probes;
  - no separate search event: the outcome travels in `Abstain.reason` (`budget_exhausted` / `candidates_failed_on_inputs`), and
    the commit claim counts the registered probe scenes.
    the outcome inside `RenderProbe`/`Abstain`, and the executor records it).
- **Rule 3 extension:** if the batch scenes give no usable question, `config.probes` is on and the question budget remains:
  1. Search probes whose id has no `ProbeRendered` yet.
  2. If one is found, return `RenderProbe`.
  3. Accepted probe scenes (role `probe`) join the batch-scene loop, so the next step asks `ChooseOutput` on them through the existing
     code.
  4. `budget_exhausted` and `candidates_failed_on_inputs` are carried to rule 6, which then returns `Abstain` with that outcome. Commit
     requires `completed_no_disagreement`.
  5. The commit claim counts the searched documents plus the accepted probes ("… over M searched scenes").

- [ ] Tests:
  - With `probes=True`, two candidates that agree on the batch scene give `RenderProbe` first.
  - After a `ProbeRendered(ok)` and a `SceneRegistered(role=probe)`, the next step is an `AskTeacher(ChooseOutput)` on the probe scene.
  - After `ProbeRendered(ok=false)`, the step searches the next probe and never asks on the failed one.
  - With `max_evaluations=1`, the session abstains with reason `budget_exhausted` and never commits (Review Focus 2).
  - With `probes=False`, every existing `test_step.py` expectation is unchanged.

  RED → implement → GREEN (run `tests/unit/teaching`) → commit `feat(teaching): rule 3 asks on rendered probes when batch documents cannot separate the rules`.

---

### Task 4: Executor performs RenderProbe through an injected renderer

**Files:** Modify `src/open_apprentice/teaching/executor.py`; Test `tests/unit/teaching/test_executor_probes.py`

**Interfaces:**
- `Executor(..., probe_renderer: Optional[Callable[[Probe], ProbeResult]] = None)`.
- `@dataclass(frozen=True) class ProbeResult: ok: bool; scene_id: Optional[str] = None; scene: Optional[dict] = None; reason: str = ""` (in `teaching/probes.py`).
- On `RenderProbe` (claimed like every action):
  1. Append `ActionIssued`.
  2. Call the renderer:
     - on ok, append `SceneRegistered(role=probe, scene=result.scene, scene_hash, probe_id)` and then `ProbeRendered(ok=True, scene_id)`;
     - on failure, append `ProbeRendered(ok=False, reason)`.
  3. A renderer exception becomes `ProbeRendered(ok=False, reason="render failed: …")`.
- Recovery: an issued `RenderProbe` with no `ProbeRendered` is re-run once on restart (rendering is idempotent).

- [ ] Tests (fake renderers):
  - The accept path leads to a ChooseOutput on the probe scene.
  - A geometry-mismatch result (`ok=False`, reason "measured geometry differs by 3.0") means no question is asked on that probe and the
    next probe is tried (Review Focus 1).
  - A raising renderer is recorded, not crashed on.
  - A crash after `ActionIssued` is recovered.

  RED → implement → GREEN → commit `feat(teaching): executor renders probes through an injected renderer`.

---

### Task 5: General geometry patch for probe documents

**Files:** Modify `src/open_apprentice/drawio/patch.py`; Test `tests/unit/drawio/test_patch_geometry.py`

**Interfaces:**
- `apply_geometry(f: DrawioFile, page_index: int, cells: dict[str, dict[str, Fraction]], page_width: Optional[Fraction], source_hash: str) -> bytes`.
  - Sets any of `x`, `y`, `width`, `height` on the named cells' `<mxGeometry>`, inserting missing attributes.
  - Optionally sets the page's `pageWidth`.
  - Values are serialized in whole units, half rounding up, as in the label patch, and the serialized values are returned for the
    renderer's geometry check.
  - Byte-span replacement, compressed pages rewritten uncompressed, other pages untouched. A source-hash mismatch is refused.
- The label patcher is unchanged.

- [ ] Tests: resize a node (width, height); move a node; narrow the page; a missing attribute is inserted; other bytes are identical; a stale hash is refused. RED → implement → GREEN → commit `feat(drawio): geometry patch for probe documents (node size/position, page width)`.

---

### Task 6: API probe renderer and probe documents

**Files:** Modify `src/open_apprentice/api/v2/service.py`, `context.py`; Test `tests/unit/api_v2/test_probes_api.py`, `tests/integration/test_api_v2_probes.py`

**Interfaces:**
- `def make_probe_renderer(v: V2, owner: str, sid: str) -> Callable[[Probe], ProbeResult]`:
  1. Resolve the probe's source scene to its document ref.
  2. `apply_geometry` the edits.
  3. Import the result as a **probe document**: `documents/{id}.json` with `probe_of: {sid, probe_id}`, owned by the session owner. It
     is never added to the owner's visible documents list, and its mapping is copied from the source (same cell ids) and confirmed.
  4. Render it with `v.render`.
  5. `build_scene` with that mapping, then compare every object's measured box with the probe's selection scene. If any coordinate
     differs by more than 0.5, return `ok=False` with the largest difference as the reason.
  6. Otherwise return `ok=True`, `scene_id=f"{probe_doc}:{page}"` and the measured scene.
  7. Append the probe ref to the session meta's `probe_refs` (CAS update), so `_ref_for_scene` and the item PNGs resolve probe scenes.
- `advance(...)` passes `StepConfig(probes=True)` and the renderer when a renderer is available (always in the app; in unit tests with
  the fake renderer).
- `GET /documents/{id}` for a probe document works for its owner. Probe documents never appear in localStorage lists, because the
  client never receives their ids except through question items.

- [ ] Tests:
  - **Unit, fake renderer:**
    - a session whose two candidates agree on the batch documents asks a ChooseOutput whose scene is a probe document, and its item PNG
      route answers 200 for the owner and 404 for another owner (Review Focus 5);
    - a fake render that returns a node 3 units off makes the probe fail with a reason, and no question on it appears (Review Focus 1).
  - **Integration, real engine:** the same flow on the corpus `d1` + `d2`, with two hand-written candidate rules injected through a
    scripted proposer: the probe document renders, matches within 0.5, and the question is answerable to commit.

  RED → implement → GREEN → commit `feat(api-v2): probe documents rendered and checked in the locked engine before asking`.

---

### Task 7: Jobs, Cloud Tasks dispatcher, OIDC-verified internal route

**Files:** Modify `src/open_apprentice/api/v2/context.py`, `service.py`, `routes.py`, `pyproject.toml` (+ `uv.lock`); Create `src/open_apprentice/api/v2/tasks.py`; Test `tests/unit/api_v2/test_tasks.py`

**Interfaces:**
- `@dataclass(frozen=True) class Job: kind: str; key: str; args: dict` (kinds `render`, `advance`, `apply`, `ping`); `service.run_job(v, job)` dispatches to `render_document`, `advance`, `run_apply`. Every existing `v.dispatcher.submit(key, lambda: …)` call becomes `v.dispatcher.submit(Job(...))`.
- `LocalDispatcher.submit(job)` keeps today's per-key coalescing, calling `run_job`.
- `CloudTasksDispatcher(client, queue_path, service_url, service_account)` builds the task:
  - `HttpRequest(POST, f"{service_url}/internal/tasks/{task_id}", body=json(job), oidc_token=OidcToken(service_account_email, audience=service_url))`;
  - `task_id` is `sha256(job.key + nonce)`: every submit is its own task. Overlapping deliveries for one key are serialized by the
    route's per-key lock, and the executors' claims make a redundant advance a no-op. Tasks are never deduplicated by name, because
    that would drop a legitimate second advance within the dedup window.
- `tasks.verify(request, audience, service_account) -> None` raises `Forbidden`:
  - uses `google.oauth2.id_token.verify_oauth2_token(token, google.auth.transport.requests.Request(), audience=audience)`;
  - requires `email == service_account` and `email_verified`;
  - the verifier is injectable for tests.
- `POST /internal/tasks/{task_id}` (installed only when `OA_DISPATCH=cloudtasks`):
  1. Verify the token.
  2. Create the claim `tasks/{task_id}.json` with `{state: running}`. If it already exists, return its state with 200 (a delivery
     marked failed does not re-run).
  3. Run the job under the in-process per-key lock.
  4. Store `done` or `failed` with the reason.

  Errors return 200 with `failed` so Cloud Tasks does not retry jobs whose failure is recorded. Unexpected crashes before the claim
  return 500, so they are retried.
- `make_v2` picks `CloudTasksDispatcher` when `OA_DISPATCH=cloudtasks` (env `OA_TASKS_QUEUE`, `OA_TASKS_SERVICE_URL`, `OA_TASKS_SERVICE_ACCOUNT`), otherwise `LocalDispatcher`.
- Dependency: add `google-cloud-tasks==2.19.*` (check the latest 2.x on PyPI at execution time and pin it), then `uv lock`.

- [ ] Tests:
  - **Fake tasks client:**
    - `submit` creates a task with the right URL, OIDC audience and service account;
    - a missing token, the wrong audience (verifier raises) or the wrong `email` gets 403 and runs nothing (Review Focus 3);
    - the same `task_id` delivered twice runs the job once, and concurrent deliveries in threads run it once (Review Focus 4);
    - a failing job returns 200 with `failed` and a stored reason.
  - **Off by default:** without `OA_DISPATCH=cloudtasks`, the route is 404.

  RED → implement → GREEN → commit `feat(api-v2): Cloud Tasks dispatch with an OIDC-verified internal task route`.

---

### Task 8: Staging dispatch check and proposal

**Files:** Modify `src/open_apprentice/cli.py` (`staging-check --only tasks`), `docs/deploy_staging_proposal.md`, `docs/implementation_audit.md`; Test `tests/unit/drawio/test_cli.py`

**Interfaces:**
- `oa staging-check --only tasks` uses the configured dispatcher to submit a `ping` job (`run_job` writes `staging/ping-{id}`), polls the store for up to 60 s, and prints `{"check": "tasks", "ok": bool, "seconds": n}`. With the local dispatcher it exercises the same path in-process.
- Proposal:
  - restore check 3 with exact commands: the staging service with `OA_DISPATCH=cloudtasks`, the queue `oa-staging`, and the service
    account as task invoker (`roles/run.invoker` on the service, `roles/cloudtasks.enqueuer` on the queue, and
    `iam.serviceAccounts.actAs` on itself);
  - add the cost line (Cloud Tasks free tier);
  - teardown unchanged.
- Audit: section 4 probe rows (implemented families, deferred families), section 8 `/internal/tasks` row, and section 10 staging rows
  (still "proposed, not created").

- [ ] Tests: `staging-check --only tasks` with the local store and dispatcher prints `ok: true`. Run every CI step and the full suite on 3.13 and 3.12. Commit `feat(cli): staging dispatch check; proposal and audit updated for Cloud Tasks and probes`.

---

## Final verification

- Full pytest on 3.13 and 3.12 with `OA_ENGINE_TESTS=1`; `npm test`; `npm run lint`; `npm run build:web && npm run test:e2e` (the
  journey must still pass with probes on: when batch documents already separate the rules, probes are never generated).
- Demo image builds and starts with `OA_DISPATCH` unset (local dispatcher).
- Nothing touches GCP.
