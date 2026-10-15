# Plan 2: Versions and Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A committed skill becomes an immutable, self-contained version with an activation history; a user's correction of an applied result runs as its own transactional cycle (scope interpretations → clarification → affected-example approval → revision preview → commit → compare-and-set activation) that never weakens the active version's evidence and reports retention explicitly; the GCS backend implements the store contract; generated state sequences check the core invariants.

**Architecture:** Builds on Plan 1's event log, teacher protocol and executor. Evidence becomes a list of identified `EvidenceItem`s (full, masked, excludes) derived from committed events. `skills/versions.py` stores immutable version artifacts and an activation record chain behind a compare-and-set pointer. A correction is a separate session log whose pure policy (`teaching/correction_step.py`) works on a draft constraint set built from the base version's embedded evidence plus correction events; a `CorrectionExecutor` performs its actions and activates the new version against the pointer generation captured at the start.

**Tech Stack:** Python 3.12/3.13, pytest, Hypothesis 6.168 (installed), `google-cloud-storage` (new dependency; approved in the design), existing rule language and evaluator.

**Spec:** `docs/superpowers/specs/2026-10-15-teach-correct-reuse-design.md` sections 3.1 (activation records), 3.4–3.7 (ConfirmCorrectionScope, correction budgets), 5 (corrections), 9 B (stateful tests), 10 (staging proposal). Plan 1: `docs/superpowers/plans/2026-10-15-p1-foundations.md` (merged at `73b106b`).

## Global Constraints

- All Plan 1 global constraints apply (black 100, type hints, no eval/exec, `teaching`/`storage`/`skills` never import `open_apprentice.evaluation`, Fractions as `"n/d"`, full suite before every push, `&&` after tests).
- Tolerance `TOL = 1/2` (max coordinate error over identical label ids); `ChooseOutput` separation `> 1`.
- Correction cycle budget: the triggering edit is the cycle's one corrective demonstration; ≤ **2 clarification interactions in total** (`ConfirmCorrectionScope` + `ChooseOutput`), ≤ 1 `ConfirmPreview(affected_examples)` of ≤ 6 items, ≤ 1 `ConfirmPreview(revision_preview)` of ≤ 3 documents, ≤ **4** provider attempts (retries count); one revision round per cycle.
- Scope selectors are rule-language boolean expressions over the label `o` and `object(o.attached)` only (role, attachment, original geometry); evaluated on the ORIGINAL input with the fixed mapping; no branch feature.
- Untouched labels in a partial correction get no new intent approval; existing evidence stays active unless explicitly superseded by a teacher event.
- Activation is a compare-and-set against the pointer generation captured when the correction began; on any failure "this correction does not change the active pointer".
- The GCS backend is never exercised against a real bucket in this plan; staging resources need the owner's approval (Task 11 writes the proposal only).

## Review Focus

1. **The pointer moves away from k and back to k during a correction**: activation must still be rejected (generation, not version, is compared). Test in Task 2 (`test_activation_compares_generation_not_version`).
2. **A correction that is cancelled after affected-example approvals**: the active version's evidence must be untouched (approvals live only in the draft). Test in Task 7 (`test_cancel_after_affected_approval_leaves_base_untouched`).
3. **A model interpretation whose program changes a label outside its own selector and outside any conflict item**: rejected as a scope violation before the user sees it. Test in Task 7 (`test_scope_violating_interpretation_is_never_shown`).
4. **Two corrections of the same skill started from the same pointer generation**: the second activation is rejected, not silently overwriting the first. Test in Task 8 (`test_second_concurrent_correction_is_rejected`).
5. **A selector text containing braces, newlines or a loop**: refused at parse time, never wrapped into a program. Test in Task 3 (`test_selector_injection_is_refused`).

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/open_apprentice/teaching/evidence.py` | `EvidenceItem`, `item_fits`, (de)serialization |
| `src/open_apprentice/teaching/constraints.py` (modify) | also derive identified `items` |
| `src/open_apprentice/skills/__init__.py` (exists) / `skills/versions.py` | `SkillStore`: immutable versions, activation records, CAS pointer, history, reconciliation |
| `src/open_apprentice/teaching/scope.py` | selector parsing/validation and member computation |
| `src/open_apprentice/teaching/teacher.py` (modify) | `ConfirmCorrectionScope` request/response, validation, JSON |
| `src/open_apprentice/evaluation/teacher_sim.py` (modify) | scope answers by meaning on a diagnostic set |
| `src/open_apprentice/teaching/retention.py` | behaviour diff buckets and retention report |
| `src/open_apprentice/teaching/corrections.py` | correction draft derivation from events |
| `src/open_apprentice/teaching/correction_step.py` | pure correction policy |
| `src/open_apprentice/teaching/correction_executor.py` | performs correction actions, stores and activates versions |
| `src/open_apprentice/teaching/executor.py` (modify) | learning commits store skill v1 through `SkillStore` |
| `src/open_apprentice/storage/gcs.py` | `GcsStore` (generation preconditions) |
| `prompts/correction_scope.md` | proposal prompt for scope interpretations (live use in later plans) |
| `docs/deploy_staging_proposal.md` | staging resources, costs, commands (not executed) |
| `tests/unit/teaching/test_*.py`, `tests/unit/storage/test_store_contract.py`, `tests/unit/teaching/test_stateful.py` | tests |

---

### Task 1: Identified evidence items and masked fits

**Files:**
- Create: `src/open_apprentice/teaching/evidence.py`
- Modify: `src/open_apprentice/teaching/constraints.py` (add `items` to `Evidence`, fill it in `derive`)
- Test: `tests/unit/teaching/test_evidence.py`

**Interfaces:**
- Consumes: `Output`, `TOL`, `max_error`, `_out_json`/`_out_parse` (teacher.py), `run_output` (step.py), `codec`.
- Produces:
  - `@dataclass(frozen=True) class EvidenceItem: id: str; kind: str; scene_id: str; scene: dict; output: Output | None = None; mask: tuple[str, ...] = (); excluded: tuple[Output, ...] = (); source: str = ""` with `kind ∈ {"full","masked","excludes"}`
  - `item_fits(rule: list, item: EvidenceItem) -> tuple[bool, str]` (full: every label within TOL; masked: masked labels within TOL; excludes: no excluded output reproduced within TOL; runtime failure → False)
  - `item_to_json(item) -> dict`, `item_from_json(d) -> EvidenceItem`
  - `Evidence.items: list[EvidenceItem]`, ids `f"{event_id}:{k}"` (k = position within the event)

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import derive
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.evidence import EvidenceItem, item_fits, item_from_json, item_to_json
from open_apprentice.teaching.step import run_output

SCENE = {"objects": [
    {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
    {"id": "n1", "kind": "node", "role": "", "attached": "", "x": 0, "y": 200, "w": 100, "h": 50},
    {"id": "l0", "kind": "label", "role": "note", "attached": "n0", "x": 0, "y": 60, "w": 40, "h": 20},
    {"id": "l1", "kind": "label", "role": "warning", "attached": "n1", "x": 0, "y": 260, "w": 40, "h": 20}],
    "canvas": {"w": 600, "h": 400}}
RIGHT = rule_for_spec(Spec("right", None, "all", F(12)))


def test_full_item_fits_its_own_output_and_rejects_another():
    out = run_output(RIGHT, SCENE)
    item = EvidenceItem("e1:0", "full", "s", SCENE, output=out)
    assert item_fits(RIGHT, item)[0]
    other = dict(out, l1=(F(0), F(260)))
    assert not item_fits(RIGHT, EvidenceItem("e1:1", "full", "s", SCENE, output=other))[0]


def test_masked_item_checks_only_masked_labels():
    out = run_output(RIGHT, SCENE)
    masked = EvidenceItem("e2:0", "masked", "s", SCENE, output={"l0": out["l0"]}, mask=("l0",))
    assert item_fits(RIGHT, masked)[0]
    notes_only = rule_for_spec(Spec("right", None, "notes", F(12)))  # leaves l1 alone
    assert item_fits(notes_only, masked)[0]


def test_excludes_item_rejects_a_reproduced_output():
    out = run_output(RIGHT, SCENE)
    assert not item_fits(RIGHT, EvidenceItem("e3:0", "excludes", "s", SCENE, excluded=(out,)))[0]


def test_json_round_trip():
    item = EvidenceItem("e4:0", "masked", "s", SCENE, output={"l0": (F(1, 3), F(2))}, mask=("l0",), source="correction")
    assert item_from_json(codec.loads(codec.dumps(item_to_json(item)))) == item_from_json(item_to_json(item))


def test_derive_produces_identified_items():
    evs = [Event("e1", None, 1, "SceneRegistered", "system",
                 {"scene_id": "d", "scene_hash": codec.digest(SCENE), "scene": codec.loads(codec.dumps(SCENE)), "role": "demo"}),
           Event("e2", "e1", 2, "DemonstrationRecorded", "human",
                 {"scene_id": "d", "output": codec.loads(codec.dumps(run_output(RIGHT, SCENE)))})]
    items = derive(evs).items
    assert [(i.id, i.kind, i.scene_id) for i in items] == [("e2:0", "full", "d")]
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_evidence.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'open_apprentice.teaching.evidence'`

- [ ] **Step 3: Implement `evidence.py`**

```python
"""Identified evidence items. A version stores its evidence as a list of these, so a correction can rebuild, supersede and
replace individual pieces of evidence by id."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from open_apprentice.teaching.constraints import scene_from_payload
from open_apprentice.teaching.step import run_output
from open_apprentice.teaching.teacher import TOL, Output, _out_json, _out_parse, max_error


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    kind: str  # full | masked | excludes
    scene_id: str
    scene: dict
    output: Optional[Output] = None
    mask: tuple[str, ...] = ()
    excluded: tuple[Output, ...] = ()
    source: str = ""


def item_fits(rule: list, item: EvidenceItem) -> tuple[bool, str]:
    out = run_output(rule, item.scene)
    if out is None:
        return False, f"{item.id}: the program fails to run on {item.scene_id}"
    if item.kind == "full":
        e = max_error(out, item.output or {})
        return (e is not None and e <= TOL), f"{item.id}: differs from the approved output on {item.scene_id}"
    if item.kind == "masked":
        sub = {k: out[k] for k in item.mask}
        e = max_error(sub, item.output or {})
        return (e is not None and e <= TOL), f"{item.id}: corrected labels differ on {item.scene_id}"
    for bad in item.excluded:
        e = max_error(out, bad)
        if e is not None and e <= TOL:
            return False, f"{item.id}: reproduces a rejected output on {item.scene_id}"
    return True, ""


def item_to_json(item: EvidenceItem) -> dict:
    return {
        "id": item.id,
        "kind": item.kind,
        "scene_id": item.scene_id,
        "scene": item.scene,
        "output": _out_json(item.output) if item.output is not None else None,
        "mask": list(item.mask),
        "excluded": [_out_json(o) for o in item.excluded],
        "source": item.source,
    }


def item_from_json(d: dict) -> EvidenceItem:
    return EvidenceItem(
        d["id"],
        d["kind"],
        d["scene_id"],
        scene_from_payload(d["scene"]),
        _out_parse(d["output"]) if d.get("output") is not None else None,
        tuple(d.get("mask", [])),
        tuple(_out_parse(o) for o in d.get("excluded", [])),
        d.get("source", ""),
    )
```

Note: `evidence.py` imports `constraints.scene_from_payload` and `step.run_output`; `constraints.py` must therefore NOT import `evidence.py` at module level. Define `EvidenceItem` creation inside `constraints.derive` via a local import (Step 4).

- [ ] **Step 4: Fill `items` in `derive`** — in `constraints.py` add `items: list = field(default_factory=list)` to `Evidence`, and in `derive`, after each positive/negative is created, append an item. Replace `_positive` and the excludes branches with:

```python
def _positive(e: Evidence, sid: str, out: Output, source: str, item_id: str) -> None:
    from open_apprentice.teaching.evidence import EvidenceItem  # local: evidence imports this module

    sc = e.scenes[sid]
    e.positives.append(Constraint("positive", sc, to_state(apply_output(sc, out)), source=source))
    e.approved[sid] = out
    e.items.append(EvidenceItem(item_id, "full", sid, sc, output=out, source=source))


def _excludes(e: Evidence, sid: str, outs: list[Output], source: str, item_id: str) -> None:
    from open_apprentice.teaching.evidence import EvidenceItem

    sc = e.scenes[sid]
    excl = tuple(to_state(apply_output(sc, o)) for o in outs)
    e.negatives.append(Constraint("excludes", sc, excluded=excl, source=source))
    e.rejected.setdefault(sid, []).extend(outs)
    e.items.append(EvidenceItem(item_id, "excludes", sid, sc, excluded=tuple(outs), source=source))
```

and pass `f"{ev.event_id}:{k}"` ids (k = 0 for single-item events; the item index for previews). Update every call site in `derive` accordingly (demonstration, choose, none, preview approve/reject, requested demonstration).

- [ ] **Step 5: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching -q`
Expected: all pass (55 existing + 5 new).

- [ ] **Step 6: Commit**

```bash
git add src/open_apprentice/teaching/evidence.py src/open_apprentice/teaching/constraints.py tests/unit/teaching/test_evidence.py
git commit -m "feat(teaching): identified evidence items (full, masked, excludes) with tolerance fits"
```

---

### Task 2: Immutable versions and the activation record chain

**Files:**
- Create: `src/open_apprentice/skills/versions.py`
- Test: `tests/unit/teaching/test_versions.py`

**Interfaces:**
- Consumes: `Store`, `PreconditionFailed` (storage), `codec`, `SessionLog` (events).
- Produces:
  - `class ActivationRejected(Exception)`
  - `class SkillStore`: `__init__(self, store: Store)`;
    `store_version(self, skill_id: str, artifact: dict) -> int` (assigns `version = latest + 1` unless `artifact["version"]` is set; writes `skills/<id>/v<n>.json` with `artifact_hash`; idempotent when the same content is stored again; returns the version);
    `version(self, skill_id: str, n: int) -> dict`;
    `active(self, skill_id: str) -> tuple[int | None, str | None, int | None]` (version, record_id, pointer generation; all None when never activated);
    `activate(self, skill_id: str, version: int, expected_generation: int | None, operation_id: str, session_id: str) -> str` (writes immutable `skills/<id>/activations/<record_id>.json` then CAS on `active.json`; raises `ActivationRejected` on a generation mismatch; returns record_id);
    `history(self, skill_id: str) -> list[dict]` (committed activation records, oldest first, walking `prev_record_id` from the pointer);
    `reconcile(self, skill_id: str, logs: dict[str, SessionLog]) -> int` (appends any missing `VersionActivated{operation_id, from, to, record_id}` to the originating session's log, idempotently; returns how many were appended)

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from open_apprentice.skills.versions import ActivationRejected, SkillStore
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.events import SessionLog


def art(rule="r1"):
    return {"skill_id": "k", "program": {"rule": [rule]}, "evidence": [], "superseded": {}, "retention_report": {}}


def test_store_is_immutable_and_versions_increase(tmp_path):
    s = SkillStore(LocalStore(tmp_path))
    assert s.store_version("k", art("a")) == 1
    assert s.store_version("k", art("b")) == 2
    assert s.version("k", 1)["program"]["rule"] == ["a"] and s.version("k", 1)["artifact_hash"]


def test_activate_and_rollback_keep_a_committed_history(tmp_path):
    s = SkillStore(LocalStore(tmp_path))
    s.store_version("k", art("a")); s.store_version("k", art("b"))
    s.activate("k", 1, None, "op1", "s1")
    _, _, g = s.active("k")
    s.activate("k", 2, g, "op2", "s2")
    _, _, g = s.active("k")
    s.activate("k", 1, g, "op3", "s3")  # rollback
    assert [(h["from_version"], h["to_version"]) for h in s.history("k")] == [(None, 1), (1, 2), (2, 1)]
    assert s.active("k")[0] == 1


def test_activation_compares_generation_not_version(tmp_path):
    s = SkillStore(LocalStore(tmp_path))
    s.store_version("k", art("a")); s.store_version("k", art("b"))
    s.activate("k", 1, None, "op1", "s1")
    _, _, g_start = s.active("k")  # a correction starts here, at version 1
    s.activate("k", 2, g_start, "op2", "s2")
    s.activate("k", 1, s.active("k")[2], "op3", "s3")  # pointer back at version 1, new generation
    with pytest.raises(ActivationRejected):
        s.activate("k", 2, g_start, "op4", "s4")


def test_failed_cas_leaves_its_record_unreachable(tmp_path):
    s = SkillStore(LocalStore(tmp_path))
    s.store_version("k", art("a"))
    s.activate("k", 1, None, "op1", "s1")
    with pytest.raises(ActivationRejected):
        s.activate("k", 1, 999, "op2", "s2")
    assert [h["operation_id"] for h in s.history("k")] == ["op1"]


def test_reconcile_recovers_two_unlogged_activations_including_a_rollback(tmp_path):
    store = LocalStore(tmp_path)
    s = SkillStore(store)
    logs = {}
    for sid in ("s1", "s2", "s3"):
        logs[sid] = SessionLog(store, sid)
        logs[sid].create(owner="o")
    s.store_version("k", art("a")); s.store_version("k", art("b"))
    s.activate("k", 1, None, "op1", "s1")
    logs["s1"].append("VersionActivated", "system", {"operation_id": "op1", "from": None, "to": 1, "record_id": s.active("k")[1]})
    s.activate("k", 2, s.active("k")[2], "op2", "s2")  # crash before logging
    s.activate("k", 1, s.active("k")[2], "op3", "s3")  # rollback, crash before logging
    pointer_before = s.active("k")
    assert s.reconcile("k", logs) == 2
    assert s.reconcile("k", logs) == 0  # idempotent
    assert s.active("k") == pointer_before
    assert [e.payload["to"] for e in logs["s2"].events() if e.type == "VersionActivated"] == [2]
    assert [e.payload["to"] for e in logs["s3"].events() if e.type == "VersionActivated"] == [1]
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_versions.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'open_apprentice.skills.versions'`

- [ ] **Step 3: Implement `skills/versions.py`**

```python
"""Immutable skill versions and their activation history. A version object is written once; the active pointer moves only
by compare-and-set and always references an immutable activation record (operation, originating session, from/to,
predecessor), so history can be rebuilt from the pointer even if a session crashed before logging. Spec 3.1."""

from __future__ import annotations

import uuid
from typing import Optional

from open_apprentice.storage.store import PreconditionFailed, Store
from open_apprentice.teaching import codec
from open_apprentice.teaching.events import SessionLog


class ActivationRejected(Exception):
    """The active pointer is not at the generation the caller started from."""


class SkillStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    def _latest(self, skill_id: str) -> int:
        n = 0
        while self.store.get(f"skills/{skill_id}/v{n + 1}.json") is not None:
            n += 1
        return n

    def store_version(self, skill_id: str, artifact: dict) -> int:
        body = {k: v for k, v in artifact.items() if k not in ("version", "artifact_hash")}
        h = codec.digest(body)
        for n in range(1, self._latest(skill_id) + 1):
            if self.version(skill_id, n)["artifact_hash"] == h:
                return n  # same content already stored: idempotent
        while True:
            n = artifact.get("version") or self._latest(skill_id) + 1
            doc = dict(body, skill_id=skill_id, version=n, artifact_hash=h)
            if self.store.create(f"skills/{skill_id}/v{n}.json", codec.dumps(doc)):
                return n
            if artifact.get("version"):
                raise ValueError(f"version {n} of {skill_id} already exists with different content")

    def version(self, skill_id: str, n: int) -> dict:
        b = self.store.get(f"skills/{skill_id}/v{n}.json")
        if b is None:
            raise KeyError(f"{skill_id} v{n} not stored")
        return codec.loads(b.data)

    def active(self, skill_id: str) -> tuple[Optional[int], Optional[str], Optional[int]]:
        b = self.store.get(f"skills/{skill_id}/active.json")
        if b is None:
            return None, None, None
        d = codec.loads(b.data)
        return d["version"], d["record_id"], b.generation

    def activate(
        self, skill_id: str, version: int, expected_generation: Optional[int], operation_id: str, session_id: str
    ) -> str:
        self.version(skill_id, version)  # must exist
        b = self.store.get(f"skills/{skill_id}/active.json")
        cur = codec.loads(b.data) if b else None
        if (b.generation if b else None) != expected_generation:
            raise ActivationRejected(f"pointer at generation {b and b.generation}, expected {expected_generation}")
        record_id = uuid.uuid4().hex
        record = {
            "record_id": record_id,
            "operation_id": operation_id,
            "session_id": session_id,
            "from_version": cur["version"] if cur else None,
            "to_version": version,
            "prev_record_id": cur["record_id"] if cur else None,
        }
        self.store.create(f"skills/{skill_id}/activations/{record_id}.json", codec.dumps(record))
        try:
            self.store.put(
                f"skills/{skill_id}/active.json",
                codec.dumps({"version": version, "record_id": record_id}),
                if_generation=expected_generation,
            )
        except PreconditionFailed as e:
            raise ActivationRejected(str(e)) from e  # the record stays unreachable
        return record_id

    def history(self, skill_id: str) -> list[dict]:
        _, rid, _ = self.active(skill_id)
        out = []
        while rid is not None:
            b = self.store.get(f"skills/{skill_id}/activations/{rid}.json")
            if b is None:
                raise RuntimeError(f"committed activation record {rid} missing")
            r = codec.loads(b.data)
            out.append(r)
            rid = r["prev_record_id"]
        return list(reversed(out))

    def reconcile(self, skill_id: str, logs: dict[str, SessionLog]) -> int:
        added = 0
        for r in self.history(skill_id):
            log = logs.get(r["session_id"])
            if log is None:
                continue
            seen = {e.payload.get("operation_id") for e in log.events() if e.type == "VersionActivated"}
            if r["operation_id"] in seen:
                continue
            log.append(
                "VersionActivated",
                "system",
                {"operation_id": r["operation_id"], "from": r["from_version"], "to": r["to_version"],
                 "record_id": r["record_id"], "reconciled": True},
            )
            added += 1
        return added
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_versions.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/skills/versions.py tests/unit/teaching/test_versions.py
git commit -m "feat(skills): immutable versions, activation record chain, CAS pointer, reconciliation"
```

---

### Task 3: Scope selectors

**Files:**
- Create: `src/open_apprentice/teaching/scope.py`
- Test: `tests/unit/teaching/test_scope.py`

**Interfaces:**
- Consumes: `concepts.rule_text.parse_rule_text`, `concepts.rules.RuleError`, `step.run_output`.
- Produces:
  - `class SelectorError(Exception)`
  - `parse_selector(text: str) -> list` (returns a membership program; raises `SelectorError` on braces, newlines, `objects`, `for`, `let`, `move`, or text longer than 300 chars)
  - `members(selector_text: str, scene: dict) -> frozenset[str]` (label ids for which the selector holds, evaluated on the given ORIGINAL scene)

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from open_apprentice.teaching.scope import SelectorError, members, parse_selector

SCENE = {"objects": [
    {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 200, "h": 50},
    {"id": "n1", "kind": "node", "role": "", "attached": "", "x": 0, "y": 200, "w": 80, "h": 50},
    {"id": "l0", "kind": "label", "role": "note", "attached": "n0", "x": 0, "y": 60, "w": 40, "h": 20},
    {"id": "l1", "kind": "label", "role": "warning", "attached": "n1", "x": 0, "y": 260, "w": 40, "h": 20},
    {"id": "l2", "kind": "label", "role": "warning", "attached": "n0", "x": 50, "y": 60, "w": 40, "h": 20}],
    "canvas": {"w": 600, "h": 400}}


def test_role_selector():
    assert members('o.role == "warning"', SCENE) == {"l1", "l2"}


def test_attachment_geometry_selector():
    assert members("object(o.attached).w > 100", SCENE) == {"l0", "l2"}


def test_everything_selector():
    assert members('o.kind == "label"', SCENE) == {"l0", "l1", "l2"}


@pytest.mark.parametrize("bad", ['o.role == "w" } for p in objects { move p to (0, 0)', "true\nmove o to (0,0)",
                                 "for p in objects", "x" * 400])
def test_selector_injection_is_refused(bad):
    with pytest.raises(SelectorError):
        parse_selector(bad)
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_scope.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scope.py`**

```python
"""Correction scope selectors: a boolean rule-language expression over the label `o` (and `object(o.attached)`).
Membership is computed by running a tiny marker program through the existing evaluator on the ORIGINAL input with the
fixed mapping, so the candidate program never influences its own scope. Spec 5."""

from __future__ import annotations

import re

from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.concepts.rules import RuleError
from open_apprentice.teaching.step import run_output

MAX_LEN = 300
FORBIDDEN = re.compile(r"[{}\n\r;]|\b(objects|for|let|move|resize|clone)\b")
MARK = 1  # members are moved by one unit in the marker program


class SelectorError(Exception):
    pass


def parse_selector(text: str) -> list:
    if len(text) > MAX_LEN or FORBIDDEN.search(text):
        raise SelectorError("a selector is one expression over o and object(o.attached)")
    src = f'for o in objects {{\n  if o.kind == "label" and ({text}) {{\n    move o to (o.x + {MARK}, o.y)\n  }}\n}}'
    try:
        return parse_rule_text(src)
    except RuleError as e:
        raise SelectorError(f"selector does not parse: {e}") from e


def members(selector_text: str, scene: dict) -> frozenset[str]:
    out = run_output(parse_selector(selector_text), scene)
    if out is None:
        raise SelectorError("selector fails to evaluate on this document")
    labels = {o["id"]: o for o in scene["objects"] if o["kind"] == "label"}
    return frozenset(k for k, (x, _) in out.items() if x != labels[k]["x"])
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_scope.py -q`
Expected: 7 passed. If `parse_rule_text` has no `true` literal and the injection case with a newline is accepted, the `FORBIDDEN` pattern already rejects newlines before parsing; if `object(o.attached).w` does not parse, check `rule_text.py`'s grammar for `object(EXPR)` field access (it supports `object(EXPR).field` per Era 2) and adjust only the test expression, recording a ruling.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/teaching/scope.py tests/unit/teaching/test_scope.py
git commit -m "feat(teaching): scope selectors evaluated on the original input with a marker program"
```

---

### Task 4: ConfirmCorrectionScope request type and simulator answers by meaning

**Files:**
- Modify: `src/open_apprentice/teaching/teacher.py`, `src/open_apprentice/evaluation/teacher_sim.py`
- Test: `tests/unit/teaching/test_scope_request.py`

**Interfaces:**
- Consumes: `members` (Task 3), `Output`, `_scene_ok`, JSON helpers.
- Produces:
  - `@dataclass(frozen=True) class Interpretation: interp_id: str; kind: str; selector: str | None; summary: str; consequences: tuple[tuple[str, str, Output], ...]` (`kind ∈ {"revise","override","accidental"}`; consequences = (scene_id, scene_hash, displayed output))
  - `@dataclass(frozen=True) class ConfirmCorrectionScope: request_id: str; interpretations: tuple[Interpretation, ...]`
  - validation: 2–4 interpretations; unique ids; no two with identical (kind, selector, consequence outputs); every consequence scene registered; responses `select` (with `selected` ∈ ids) / `none` / `unsure` / `cancel`
  - JSON: `request_to_json`/`request_from_json` handle `"ConfirmCorrectionScope"`
  - `SimTeacher(spec, scenes, scope_intent: dict | None = None)` where `scope_intent = {"kind": "revise"|"override"|"accidental", "selector": str, "diagnostic_scenes": list[str], "new_spec": Spec}`; a `revise` interpretation matches when its selector's members equal the intent selector's members on every diagnostic scene AND each consequence output matches `new_spec`'s oracle within TOL; more than one match → protocol error; none → `none`

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction as F

import pytest

from open_apprentice.evaluation.labels import Spec, oracle
from open_apprentice.evaluation.teacher_sim import SimTeacher
from open_apprentice.teaching import codec
from open_apprentice.teaching.teacher import (
    ConfirmCorrectionScope, Interpretation, ProtocolError, Response, request_from_json, request_to_json,
    validate_request, validate_response,
)

SCENE = {"objects": [
    {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
    {"id": "n1", "kind": "node", "role": "", "attached": "", "x": 0, "y": 200, "w": 100, "h": 50},
    {"id": "l0", "kind": "label", "role": "note", "attached": "n0", "x": 0, "y": 60, "w": 40, "h": 20},
    {"id": "l1", "kind": "label", "role": "warning", "attached": "n1", "x": 0, "y": 260, "w": 40, "h": 20}],
    "canvas": {"w": 600, "h": 400}}
H = codec.digest(SCENE)
NEW = Spec("right", None, "notes", F(12))  # intended: warnings stay put


def labels_out(spec):
    moved = oracle(spec, SCENE)
    return {o["id"]: moved.get(o["id"], (F(o["x"]), F(o["y"]))) for o in SCENE["objects"] if o["kind"] == "label"}


def req():
    right_all = labels_out(Spec("right", None, "all", F(12)))
    notes = labels_out(NEW)
    return ConfirmCorrectionScope("c1", (
        Interpretation("i1", "revise", 'o.role == "warning"', "warnings stay", (("s", H, notes),)),
        Interpretation("i2", "revise", 'o.kind == "label"', "nothing changes", (("s", H, right_all),)),
        Interpretation("i3", "override", None, "only this document", ()),
        Interpretation("i4", "accidental", None, "undo my edit", ())))


def test_validation_and_json_round_trip():
    r = req()
    validate_request(r, {"s": H})
    assert request_from_json(request_to_json(r)) == r
    validate_response(r, Response("c1", "select", selected="i1"))
    with pytest.raises(ProtocolError):
        validate_response(r, Response("c1", "select", selected="zz"))
    with pytest.raises(ProtocolError):
        validate_request(ConfirmCorrectionScope("c2", req().interpretations[:1]), {"s": H})


def test_simulator_selects_by_meaning():
    intent = {"kind": "revise", "selector": 'o.role == "warning"', "diagnostic_scenes": ["s"], "new_spec": NEW}
    t = SimTeacher(NEW, {"s": SCENE}, scope_intent=intent)
    assert t.answer(req()).selected == "i1"


def test_simulator_says_none_when_no_interpretation_means_the_intent():
    intent = {"kind": "revise", "selector": 'o.role == "note"', "diagnostic_scenes": ["s"], "new_spec": NEW}
    t = SimTeacher(NEW, {"s": SCENE}, scope_intent=intent)
    assert t.answer(req()).kind == "none"


def test_simulator_chooses_override_when_that_is_the_intent():
    t = SimTeacher(NEW, {"s": SCENE}, scope_intent={"kind": "override"})
    assert t.answer(req()).selected == "i3"
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_scope_request.py -q`
Expected: FAIL with `ImportError: cannot import name 'ConfirmCorrectionScope'`.

- [ ] **Step 3: Implement in `teacher.py`** — add after `RequestDemonstration`:

```python
@dataclass(frozen=True)
class Interpretation:
    interp_id: str
    kind: str  # revise | override | accidental
    selector: Optional[str]
    summary: str
    consequences: tuple[tuple[str, str, Output], ...]


@dataclass(frozen=True)
class ConfirmCorrectionScope:
    request_id: str
    interpretations: tuple[Interpretation, ...]
```

Extend `Request = Union[ChooseOutput, ConfirmPreview, RequestDemonstration, ConfirmCorrectionScope]`. In `validate_request` add:

```python
    elif isinstance(req, ConfirmCorrectionScope):
        its = req.interpretations
        if not 2 <= len(its) <= 4:
            raise ProtocolError("ConfirmCorrectionScope needs 2-4 interpretations")
        if len({i.interp_id for i in its}) != len(its):
            raise ProtocolError("duplicate interpretation ids")
        keys = [(i.kind, i.selector, tuple((s, tuple(sorted(o.items()))) for s, _, o in i.consequences)) for i in its]
        if len(set(keys)) != len(keys):
            raise ProtocolError("two interpretations are identical")
        for i in its:
            if i.kind not in ("revise", "override", "accidental"):
                raise ProtocolError(f"unknown interpretation kind {i.kind}")
            for sid, sh, _ in i.consequences:
                _scene_ok(sid, sh, registered)
```

(place it before the final `else`). In `validate_response` add:

```python
    elif isinstance(req, ConfirmCorrectionScope):
        if resp.kind not in ("select", "none", "unsure", "cancel"):
            raise ProtocolError(f"bad scope response {resp.kind}")
        if resp.kind == "select" and resp.selected not in {i.interp_id for i in req.interpretations}:
            raise ProtocolError("selection names an interpretation that was not shown")
```

JSON (add branches to `request_to_json` / `request_from_json`):

```python
    if isinstance(req, ConfirmCorrectionScope):
        return {"type": "ConfirmCorrectionScope", "request_id": req.request_id,
                "interpretations": [{"interp_id": i.interp_id, "kind": i.kind, "selector": i.selector,
                                     "summary": i.summary,
                                     "consequences": [[s, h, _out_json(o)] for s, h, o in i.consequences]}
                                    for i in req.interpretations]}
```

```python
    if d["type"] == "ConfirmCorrectionScope":
        return ConfirmCorrectionScope(d["request_id"], tuple(
            Interpretation(i["interp_id"], i["kind"], i["selector"], i["summary"],
                           tuple((s, h, _out_parse(o)) for s, h, o in i["consequences"]))
            for i in d["interpretations"]))
```

- [ ] **Step 4: Simulator** — in `teacher_sim.py`, change the constructor to `def __init__(self, spec: Spec, scenes: dict[str, dict], scope_intent: Optional[dict] = None)` (store `self.scope_intent`), import `members` from `open_apprentice.teaching.scope` and `ConfirmCorrectionScope`, and add to `answer` before the final raise:

```python
        if isinstance(req, ConfirmCorrectionScope):
            intent = self.scope_intent or {}
            if intent.get("kind") in ("override", "accidental"):
                hits = [i.interp_id for i in req.interpretations if i.kind == intent["kind"]]
            else:
                hits = [i.interp_id for i in req.interpretations if i.kind == "revise" and self._means(i, intent)]
            if len(hits) > 1:
                raise ProtocolError("more than one interpretation matches the intended change")
            if hits:
                return Response(req.request_id, "select", selected=hits[0], source=SOURCE)
            return Response(req.request_id, "none", source=SOURCE)
```

and the helper:

```python
    def _means(self, interp: Interpretation, intent: dict) -> bool:
        if not intent or interp.selector is None:
            return False
        for sid in intent["diagnostic_scenes"]:
            if members(interp.selector, self.scenes[sid]) != members(intent["selector"], self.scenes[sid]):
                return False
        new = SimTeacher(intent["new_spec"], self.scenes)
        return all(new._matches(out, sid) for sid, _, out in interp.consequences)
```

(import `Interpretation` and `Optional` as needed). The diagnostic scenes are the scenario's predefined set; the check is bounded and labelled as such in the evaluation protocol (Plan 5).

- [ ] **Step 5: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/open_apprentice/teaching/teacher.py src/open_apprentice/evaluation/teacher_sim.py tests/unit/teaching/test_scope_request.py
git commit -m "feat(teaching): ConfirmCorrectionScope request; simulator answers scope by meaning on a diagnostic set"
```

---

### Task 5: Behaviour diff and retention report

**Files:**
- Create: `src/open_apprentice/teaching/retention.py`
- Test: `tests/unit/teaching/test_retention.py`

**Interfaces:**
- Consumes: `run_output` (step), `members` (scope), `EvidenceItem`, `item_fits` (evidence).
- Produces:
  - `behaviour_diff(base_rule: list, cand_rule: list, scenes: dict[str, dict], selector: str, exceptions: frozenset[tuple[str, str]]) -> dict` → `{"in_scope": [(scene_id, label_id)], "exception": [...], "unexplained": [...]}` (a changed label is `in_scope` if it is a selector member on that scene, `exception` if `(scene_id, label_id)` is in `exceptions`, else `unexplained`)
  - `retention_report(cand_rule: list, active: list[EvidenceItem], superseded: dict[str, dict], replacements: list[EvidenceItem], diff: dict, scenes_searched: int) -> dict` → `{"retained": [{"id", "ok"}], "superseded": [{"id", "by", "approved_by"}], "replacements": [ids], "scope_violations": [...], "unexplained_regressions": [...], "coverage": {"scenes": n}}` where `scope_violations = diff["unexplained"]` and `unexplained_regressions` = ids of active items the candidate no longer fits

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.teaching.evidence import EvidenceItem
from open_apprentice.teaching.retention import behaviour_diff, retention_report
from open_apprentice.teaching.step import run_output

SCENE = {"objects": [
    {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
    {"id": "n1", "kind": "node", "role": "", "attached": "", "x": 0, "y": 200, "w": 100, "h": 50},
    {"id": "n2", "kind": "node", "role": "", "attached": "", "x": 300, "y": 0, "w": 100, "h": 50},
    {"id": "l0", "kind": "label", "role": "note", "attached": "n0", "x": 0, "y": 60, "w": 40, "h": 20},
    {"id": "l1", "kind": "label", "role": "warning", "attached": "n1", "x": 0, "y": 260, "w": 40, "h": 20},
    {"id": "l2", "kind": "label", "role": "warning", "attached": "n2", "x": 300, "y": 60, "w": 40, "h": 20}],
    "canvas": {"w": 600, "h": 400}}
BASE = rule_for_spec(Spec("right", None, "all", F(12)))
NOTES_ONLY = rule_for_spec(Spec("right", None, "notes", F(12)))


def test_correcting_one_warning_updates_other_warnings_in_scope_and_leaves_notes():
    d = behaviour_diff(BASE, NOTES_ONLY, {"s": SCENE}, 'o.role == "warning"', frozenset())
    assert sorted(d["in_scope"]) == [("s", "l1"), ("s", "l2")]
    assert d["unexplained"] == []
    assert run_output(NOTES_ONLY, SCENE)["l0"] == run_output(BASE, SCENE)["l0"]


def test_change_outside_selector_is_unexplained_unless_an_approved_exception():
    d = behaviour_diff(BASE, NOTES_ONLY, {"s": SCENE}, 'o.role == "note"', frozenset())
    assert sorted(d["unexplained"]) == [("s", "l1"), ("s", "l2")]
    d2 = behaviour_diff(BASE, NOTES_ONLY, {"s": SCENE}, 'o.role == "note"', frozenset({("s", "l1"), ("s", "l2")}))
    assert d2["unexplained"] == [] and len(d2["exception"]) == 2


def test_retention_report_flags_regressions_and_counts_retained():
    keep = EvidenceItem("a", "full", "s", SCENE, output=run_output(NOTES_ONLY, SCENE))
    lost = EvidenceItem("b", "full", "s", SCENE, output=run_output(BASE, SCENE))
    d = behaviour_diff(BASE, NOTES_ONLY, {"s": SCENE}, 'o.role == "warning"', frozenset())
    rep = retention_report(NOTES_ONLY, [keep, lost], {}, [], d, 1)
    assert [r["id"] for r in rep["retained"] if r["ok"]] == ["a"]
    assert rep["unexplained_regressions"] == ["b"] and rep["scope_violations"] == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_retention.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `retention.py`**

```python
"""Behaviour difference between the active program and a correction candidate, and the retention report stored with every
new version. Claims are bounded: "no unexplained regressions on the checked evidence and scenes". Spec 5."""

from __future__ import annotations

from open_apprentice.teaching.evidence import EvidenceItem, item_fits
from open_apprentice.teaching.scope import members
from open_apprentice.teaching.step import run_output


def behaviour_diff(
    base_rule: list, cand_rule: list, scenes: dict[str, dict], selector: str, exceptions: frozenset[tuple[str, str]]
) -> dict:
    out: dict[str, list[tuple[str, str]]] = {"in_scope": [], "exception": [], "unexplained": []}
    for sid in sorted(scenes):
        sc = scenes[sid]
        a, b = run_output(base_rule, sc) or {}, run_output(cand_rule, sc) or {}
        inside = members(selector, sc)
        for lid in sorted(set(a) | set(b)):
            if a.get(lid) == b.get(lid):
                continue
            key = (sid, lid)
            if lid in inside:
                out["in_scope"].append(key)
            elif key in exceptions:
                out["exception"].append(key)
            else:
                out["unexplained"].append(key)
    return out


def retention_report(
    cand_rule: list,
    active: list[EvidenceItem],
    superseded: dict[str, dict],
    replacements: list[EvidenceItem],
    diff: dict,
    scenes_searched: int,
) -> dict:
    retained = [{"id": it.id, "ok": item_fits(cand_rule, it)[0]} for it in active]
    return {
        "retained": retained,
        "superseded": [{"id": k, **v} for k, v in sorted(superseded.items())],
        "replacements": [r.id for r in replacements],
        "scope_violations": list(diff["unexplained"]),
        "unexplained_regressions": [r["id"] for r in retained if not r["ok"]],
        "coverage": {"scenes": scenes_searched},
        "claim": "no unexplained regressions on the checked evidence and scenes",
    }
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_retention.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/teaching/retention.py tests/unit/teaching/test_retention.py
git commit -m "feat(teaching): behaviour diff buckets and retention report"
```

---

### Task 6: Learning commits store skill version 1 with its evidence

**Files:**
- Modify: `src/open_apprentice/teaching/executor.py` (the `CommitVersion` branch of `_perform`)
- Test: `tests/unit/teaching/test_executor_versions.py`

**Interfaces:**
- Consumes: `SkillStore` (Task 2), `item_to_json` (Task 1), `derive`.
- Produces: `Executor.__init__(..., skill_id: str = "skill")`; on commit the executor stores version 1 of `skill_id` with `{"skill_id", "program": {"rule", "hash", "summary", "claim"}, "evidence": [item_to_json(i) for i in derive(events).items], "superseded": {}, "retention_report": {}, "parent_version": None, "created_by_session": sid}` and appends `VersionStored{action_id, skill_id, version, program_hash}`. Activation stays a separate step (`SkillStore.activate`).

- [ ] **Step 1: Write the failing test**

```python
from fractions import Fraction as F

from open_apprentice.skills.versions import SkillStore
from tests.unit.teaching.test_executor import ApprovingTeacher, CountingProposer, start
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.executor import Executor
from open_apprentice.teaching.step import StepConfig


def test_learning_commit_stores_version_one_with_its_evidence(tmp_path):
    store, log = start(tmp_path)
    ex = Executor(store, log, CountingProposer(), ApprovingTeacher(), Ledger(store, F(5)), StepConfig(), skill_id="k")
    assert ex.run() == "committed"
    skills = SkillStore(store)
    v1 = skills.version("k", 1)
    assert v1["program"]["rule"] and {e["kind"] for e in v1["evidence"]} == {"full"}
    assert skills.active("k")[0] is None  # storing is not activating
    stored = next(e for e in log.events() if e.type == "VersionStored")
    assert stored.payload["skill_id"] == "k" and stored.payload["version"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/teaching/test_executor_versions.py -q`
Expected: FAIL with `TypeError: Executor.__init__() got an unexpected keyword argument 'skill_id'`

- [ ] **Step 3: Implement** — add `skill_id: str = "skill"` as the last `__init__` parameter (`self.skill_id = skill_id`), import `SkillStore` and `item_to_json`, and replace the `CommitVersion` branch:

```python
        elif isinstance(action, CommitVersion):
            self._issue(action.action_id, "CommitVersion")
            items = derive(self.log.events()).items
            artifact = {
                "skill_id": self.skill_id,
                "program": {"rule": action.rule, "hash": action.program_hash, "summary": action.summary,
                            "claim": action.claim},
                "evidence": [item_to_json(i) for i in items],
                "superseded": {},
                "retention_report": {},
                "parent_version": None,
                "created_by_session": self.log.sid,
            }
            version = SkillStore(self.store).store_version(self.skill_id, artifact)
            self.log.append(
                "VersionStored",
                "system",
                {"action_id": action.action_id, "skill_id": self.skill_id, "version": version,
                 "program_hash": action.program_hash},
            )
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/teaching -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/teaching/executor.py tests/unit/teaching/test_executor_versions.py
git commit -m "feat(teaching): learning commits store skill version 1 with identified evidence"
```

---

### Task 7: Correction draft and the pure correction policy

**Files:**
- Create: `src/open_apprentice/teaching/corrections.py`, `src/open_apprentice/teaching/correction_step.py`
- Test: `tests/unit/teaching/test_correction_step.py`

**Interfaces:**
- Consumes: `Event`, `EvidenceItem`, `item_fits`, `item_from_json`, `members`, `parse_selector`, `SelectorError`, `behaviour_diff`, `retention_report`, `run_output`, step action classes (`WaitForResult`, `RequestModelProposal`, `AskTeacher`, `PresentPreview`, `Abstain`, `Error`, `_aid`, `_forbidden_effect`, `_groups`, `_usable`), teacher types.
- Produces:
  - `corrections.Draft` dataclass: `base: dict` (base artifact), `base_items: list[EvidenceItem]`, `corrective: EvidenceItem`, `scenes: dict[str, dict]`, `scene_hashes: dict[str, str]`, `authorized: dict | None` (`{"selector", "interp_id"}`), `override: bool`, `dismissed: bool`, `cancelled: bool`, `superseded: dict[str, dict]` (old item id → `{"by", "approved_by"}`), `replacements: list[EvidenceItem]`, `kept_against_supersession: set[str]`, `preview_items: list[EvidenceItem]`, `rejected_items: list[EvidenceItem]`, `clarifications: int`, `affected_used: bool`, `revision_preview_used: bool`, `rounds: list[str]`, `attempts: int`
  - `corrections.derive_draft(events: list[Event]) -> Draft` (reads `CorrectionStarted` (must be first; payload `{skill_id, base_version, base_pointer_generation, base_artifact, scene_id, scene, scene_hash, corrected_output, mask, full_approval}`), `SceneRegistered`, `RequestIssued`, `ResponseRecorded`, `ActionIssued`)
  - `corrections.draft_items(d: Draft) -> list[EvidenceItem]` = base items minus superseded, plus replacements, the corrective item, preview approvals and rejections
  - `correction_step.CorrectionConfig(max_clarifications=2, max_attempts=4, max_affected=6, max_revision_preview=3)`
  - actions (frozen dataclasses with `action_id`): `CommitCorrection(action_id, rule, summary, selector, artifact: dict)`, `RecordOverride(action_id)`, `Dismiss(action_id)`, plus reuse of `WaitForResult`, `RequestModelProposal` (`round_kind ∈ {"scope","revision"}`), `AskTeacher`, `PresentPreview`, `Abstain`, `Error`
  - `correction_step.correction_step(events: list[Event], config: CorrectionConfig) -> Action`

Policy (spec 5, in order): terminal events → Wait; outstanding → Wait; no proposals → `RequestModelProposal("scope")`; filter candidates `{rule, selector, summary}` (valid program, valid selector, no forbidden effect, fits the corrective item, conflict set = base items it violates, behaviour diff vs base on registered scenes has no unexplained change outside selector ∪ conflict-item scenes); not authorized → if clarifications < 2: `AskTeacher(ConfirmCorrectionScope)` with ≤ 2 revise interpretations (distinct selectors/behaviour) + override + accidental (consequences: the corrected scene plus one registered scene where the two revise interpretations differ); responses → select revise: authorized; override → `RecordOverride`; accidental → `Dismiss`; none → revision if unused else `Abstain`; unsure/cancel → `Abstain("correction cancelled; the active version is unchanged")`; authorized with ≥ 2 distinguishable programs inside scope → `ChooseOutput` if clarifications < 2 else `Abstain("unresolved disagreement")`; selected program's conflict items not yet reviewed → `PresentPreview(affected_examples)` (≤ 6 items: each conflict item's scene with the candidate's new output; > 6 → `Abstain`); revision preview unused → `PresentPreview(revision_preview)` (≤ 3: one scene where a selector member changes, one unaffected scene, one more registered scene); commit check (fits all draft items, `scope_violations == []`, `unexplained_regressions == []`, every conflict item superseded by an approval, ≥ 1 approved revision-preview item, no unresolved rejection) → `CommitCorrection`; else `Abstain` with the failed condition.

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.teaching import codec
from open_apprentice.teaching.correction_step import (
    CommitCorrection, CorrectionConfig, Dismiss, RecordOverride, correction_step,
)
from open_apprentice.teaching.corrections import derive_draft
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.evidence import EvidenceItem, item_to_json
from open_apprentice.teaching.step import Abstain, AskTeacher, PresentPreview, RequestModelProposal, run_output
from open_apprentice.teaching.teacher import Response, request_to_json, response_to_json

SCENE = {"objects": [
    {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
    {"id": "n1", "kind": "node", "role": "", "attached": "", "x": 0, "y": 200, "w": 100, "h": 50},
    {"id": "n2", "kind": "node", "role": "", "attached": "", "x": 300, "y": 0, "w": 100, "h": 50},
    {"id": "l0", "kind": "label", "role": "note", "attached": "n0", "x": 0, "y": 60, "w": 40, "h": 20},
    {"id": "l1", "kind": "label", "role": "warning", "attached": "n1", "x": 0, "y": 260, "w": 40, "h": 20},
    {"id": "l2", "kind": "label", "role": "warning", "attached": "n2", "x": 300, "y": 60, "w": 40, "h": 20}],
    "canvas": {"w": 600, "h": 400}}
OTHER = {"objects": [o for o in SCENE["objects"] if o["id"] not in ("n2", "l2")], "canvas": SCENE["canvas"]}
BASE = rule_for_spec(Spec("right", None, "all", F(12)))
NOTES = rule_for_spec(Spec("right", None, "notes", F(12)))
CFG = CorrectionConfig()


class Log:
    def __init__(self):
        self.evs = []

    def add(self, t, payload, origin="system"):
        n = len(self.evs) + 1
        self.evs.append(Event(f"e{n}", f"e{n-1}" if n > 1 else None, n, t, origin, payload))


def scene_json(sc):
    return codec.loads(codec.dumps(sc))


def started(log, base_items):
    base = {"skill_id": "k", "version": 1, "program": {"rule": BASE, "summary": "right"},
            "evidence": [item_to_json(i) for i in base_items], "superseded": {}}
    applied = run_output(BASE, SCENE)
    corrected = dict(applied, l1=(F(0), F(260)))  # the user moves warning l1 back below its node
    log.add("CorrectionStarted", {"skill_id": "k", "base_version": 1, "base_pointer_generation": 1,
                                  "base_artifact": base, "scene_id": "c", "scene": scene_json(SCENE),
                                  "scene_hash": codec.digest(SCENE),
                                  "corrected_output": {"l1": [0, 260]}, "mask": ["l1"], "full_approval": False}, "human")
    for sid, sc in (("c", SCENE), ("o1", OTHER)):
        log.add("SceneRegistered", {"scene_id": sid, "scene_hash": codec.digest(sc), "scene": scene_json(sc), "role": "batch"})
    return corrected


def propose(log, cands, kind="scope"):
    a = correction_step(log.evs, CFG)
    assert isinstance(a, RequestModelProposal) and a.round_kind == kind
    log.add("ActionIssued", {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": kind})
    log.add("ModelProposalReturned", {"action_id": a.action_id, "usage": {}, "candidates": cands}, "model")


def answer(log, action, resp):
    log.add("ActionIssued", {"action_id": action.action_id, "kind": type(action).__name__})
    log.add("RequestIssued", {"request": request_to_json(action.request), "action_id": action.action_id})
    log.add("ResponseRecorded", {"response": response_to_json(resp)}, "simulator")


def base_items():
    return [EvidenceItem("b1", "full", "o1", OTHER, output=run_output(BASE, OTHER))]


def test_scope_affected_and_revision_preview_complete_within_budget():
    log = Log()
    started(log, base_items())
    propose(log, [{"rule": NOTES, "selector": 'o.role == "warning"', "summary": "warnings stay below"}])
    a = correction_step(log.evs, CFG)
    assert isinstance(a, AskTeacher) and type(a.request).__name__ == "ConfirmCorrectionScope"
    revise = next(i.interp_id for i in a.request.interpretations if i.kind == "revise")
    answer(log, a, Response(a.request.request_id, "select", selected=revise))
    b = correction_step(log.evs, CFG)  # base item b1 (warning l1 to the right on o1) now conflicts
    assert isinstance(b, PresentPreview) and b.request.purpose == "affected_examples"
    answer(log, b, Response(b.request.request_id, "items", per_item=tuple((i[0], "approve") for i in b.request.items)))
    c = correction_step(log.evs, CFG)
    assert isinstance(c, PresentPreview) and c.request.purpose == "revision_preview"
    answer(log, c, Response(c.request.request_id, "items", per_item=tuple((i[0], "approve") for i in c.request.items)))
    d = correction_step(log.evs, CFG)
    assert isinstance(d, CommitCorrection)
    rep = d.artifact["retention_report"]
    assert rep["scope_violations"] == [] and rep["unexplained_regressions"] == []
    assert list(d.artifact["superseded"]) == ["b1"]
    assert derive_draft(log.evs).clarifications == 1


def test_scope_violating_interpretation_is_never_shown():
    log = Log()
    started(log, base_items())
    propose(log, [{"rule": NOTES, "selector": 'o.role == "note"', "summary": "claims notes but moves warnings"}])
    a = correction_step(log.evs, CFG)
    assert isinstance(a, AskTeacher)
    assert all(i.kind != "revise" for i in a.request.interpretations)  # only override / accidental remain


def test_cancel_after_affected_approval_leaves_base_untouched():
    log = Log()
    started(log, base_items())
    propose(log, [{"rule": NOTES, "selector": 'o.role == "warning"', "summary": "warnings stay below"}])
    a = correction_step(log.evs, CFG)
    revise = next(i.interp_id for i in a.request.interpretations if i.kind == "revise")
    answer(log, a, Response(a.request.request_id, "select", selected=revise))
    b = correction_step(log.evs, CFG)
    answer(log, b, Response(b.request.request_id, "items", per_item=tuple((i[0], "approve") for i in b.request.items)))
    c = correction_step(log.evs, CFG)
    answer(log, c, Response(c.request.request_id, "items", per_item=tuple((i[0], "unsure") for i in c.request.items)))
    end = correction_step(log.evs, CFG)
    assert isinstance(end, Abstain)
    base_evidence = log.evs[0].payload["base_artifact"]["evidence"]
    assert [e["id"] for e in base_evidence] == ["b1"]  # the base artifact in the log is never rewritten


def test_override_and_accidental_are_not_learning():
    for kind, expected in (("override", RecordOverride), ("accidental", Dismiss)):
        log = Log()
        started(log, base_items())
        propose(log, [])
        a = correction_step(log.evs, CFG)
        if isinstance(a, RequestModelProposal):  # revision round for the empty pool
            propose(log, [], kind="revision")
            a = correction_step(log.evs, CFG)
        pick = next(i.interp_id for i in a.request.interpretations if i.kind == kind)
        answer(log, a, Response(a.request.request_id, "select", selected=pick))
        assert isinstance(correction_step(log.evs, CFG), expected)
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_correction_step.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `corrections.py`**

```python
"""Correction drafts. Everything a correction does lives in its own session log; the base version is embedded in the
CorrectionStarted event and never modified. The draft constraint set is the base evidence minus approved supersessions,
plus replacements, the corrective edit and preview verdicts. Spec 5."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import TEACHER_ORIGINS, scene_from_payload
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.evidence import EvidenceItem, item_from_json
from open_apprentice.teaching.teacher import (
    ChooseOutput, ConfirmCorrectionScope, ConfirmPreview, Output, Request, _out_parse, request_from_json,
    response_from_json,
)


@dataclass
class Draft:
    base: dict
    base_items: list[EvidenceItem]
    corrective: EvidenceItem
    scenes: dict[str, dict] = field(default_factory=dict)
    scene_hashes: dict[str, str] = field(default_factory=dict)
    authorized: Optional[dict] = None
    override: bool = False
    dismissed: bool = False
    cancelled: bool = False
    none_answered: int = 0
    superseded: dict[str, dict] = field(default_factory=dict)
    replacements: list[EvidenceItem] = field(default_factory=list)
    kept_against_supersession: set[str] = field(default_factory=set)
    preview_items: list[EvidenceItem] = field(default_factory=list)
    preview_unsure: int = 0
    rejected_items: list[EvidenceItem] = field(default_factory=list)
    chosen_outputs: list[EvidenceItem] = field(default_factory=list)
    clarifications: int = 0
    affected_used: bool = False
    revision_preview_used: bool = False
    rounds: list[str] = field(default_factory=list)
    attempts: int = 0


def derive_draft(events: list[Event]) -> Draft:
    first = events[0]
    if first.type != "CorrectionStarted":
        raise ValueError("a correction log starts with CorrectionStarted")
    p = first.payload
    base = p["base_artifact"]
    scene = scene_from_payload(p["scene"])
    corrected: Output = _out_parse(p["corrected_output"])
    if p.get("full_approval"):
        corrective = EvidenceItem(f"{first.event_id}:0", "full", p["scene_id"], scene, output=corrected,
                                  source="correction")
    else:
        corrective = EvidenceItem(f"{first.event_id}:0", "masked", p["scene_id"], scene,
                                  output={k: corrected[k] for k in p["mask"]}, mask=tuple(p["mask"]), source="correction")
    d = Draft(base, [item_from_json(e) for e in base["evidence"]], corrective)
    d.scenes[p["scene_id"]] = scene
    d.scene_hashes[p["scene_id"]] = p["scene_hash"]
    requests: dict[str, tuple[Request, str]] = {}
    responded: set[str] = set()
    for ev in events[1:]:
        q = ev.payload
        if ev.type == "SceneRegistered":
            d.scenes[q["scene_id"]] = scene_from_payload(q["scene"])
            d.scene_hashes[q["scene_id"]] = q["scene_hash"]
        elif ev.type == "ActionIssued" and q.get("kind") == "RequestModelProposal":
            d.rounds.append(q.get("round_kind", "scope"))
            d.attempts += 1
        elif ev.type == "ModelCallFailed" and not q.get("terminal"):
            d.attempts += 1
        elif ev.type == "RequestIssued":
            req = request_from_json(q["request"])
            requests[req.request_id] = (req, ev.event_id)
            if isinstance(req, (ConfirmCorrectionScope, ChooseOutput)):
                d.clarifications += 1
            elif isinstance(req, ConfirmPreview) and req.purpose == "affected_examples":
                d.affected_used = True
            elif isinstance(req, ConfirmPreview) and req.purpose == "revision_preview":
                d.revision_preview_used = True
        elif ev.type == "ResponseRecorded" and ev.origin in TEACHER_ORIGINS:
            r = response_from_json(q["response"])
            if r.request_id in responded or r.request_id not in requests:
                continue
            responded.add(r.request_id)
            req, _ = requests[r.request_id]
            if isinstance(req, ConfirmCorrectionScope):
                if r.kind == "select":
                    it = next(i for i in req.interpretations if i.interp_id == r.selected)
                    if it.kind == "revise":
                        d.authorized = {"selector": it.selector, "interp_id": it.interp_id}
                    elif it.kind == "override":
                        d.override = True
                    else:
                        d.dismissed = True
                elif r.kind == "none":
                    d.none_answered += 1
                else:
                    d.cancelled = True
            elif isinstance(req, ChooseOutput) and r.kind == "choose" and r.selected is not None:
                out = dict(req.alternatives)[r.selected]
                d.chosen_outputs.append(EvidenceItem(f"{ev.event_id}:0", "full", req.scene_id,
                                                     d.scenes[req.scene_id], output=out, source="answer"))
            elif isinstance(req, ConfirmPreview):
                verdicts = dict(r.per_item)
                for k, (item_id, sid, _, out) in enumerate(req.items):
                    v = verdicts.get(item_id)
                    new = EvidenceItem(f"{ev.event_id}:{k}", "full", sid, d.scenes[sid], output=out,
                                       source=req.purpose)
                    if req.purpose == "affected_examples":
                        old_id = item_id  # affected-example items are named after the base item they would replace
                        if v == "approve":
                            d.replacements.append(new)
                            d.superseded[old_id] = {"by": new.id, "approved_by": ev.event_id}
                        else:
                            d.kept_against_supersession.add(old_id)
                    elif v == "approve":
                        d.preview_items.append(new)
                    elif v == "reject":
                        d.rejected_items.append(EvidenceItem(new.id, "excludes", sid, d.scenes[sid],
                                                             excluded=(out,), source="revision_reject"))
                    else:
                        d.preview_unsure += 1
    return d


def draft_items(d: Draft) -> list[EvidenceItem]:
    base = [i for i in d.base_items if i.id not in d.superseded]
    return base + d.replacements + [d.corrective] + d.chosen_outputs + d.preview_items + d.rejected_items


def canonical(o: object) -> str:
    return codec.digest(o)
```

- [ ] **Step 4: Implement `correction_step.py`**

```python
"""Pure correction policy (spec 5). Same discipline as step.py: deterministic, no I/O, the log is the only input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from open_apprentice.concepts.rules import RuleError, validate_rule
from open_apprentice.teaching import codec
from open_apprentice.teaching.corrections import Draft, derive_draft, draft_items
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.evidence import EvidenceItem, item_fits, item_to_json
from open_apprentice.teaching.retention import behaviour_diff, retention_report
from open_apprentice.teaching.scope import SelectorError, members, parse_selector
from open_apprentice.teaching.step import (
    Abstain, AskTeacher, Error, PresentPreview, RequestModelProposal, WaitForResult, _aid, _forbidden_effect,
    _groups, _usable, run_output,
)
from open_apprentice.teaching.teacher import ChooseOutput, ConfirmCorrectionScope, ConfirmPreview, Interpretation

TERMINAL = ("VersionStored", "OverrideRecorded", "CorrectionDismissed", "Abstained", "Errored")


@dataclass(frozen=True)
class CorrectionConfig:
    max_clarifications: int = 2
    max_attempts: int = 4
    max_affected: int = 6
    max_revision_preview: int = 3


@dataclass(frozen=True)
class CommitCorrection:
    action_id: str
    rule: list
    summary: str
    selector: str
    artifact: dict


@dataclass(frozen=True)
class RecordOverride:
    action_id: str


@dataclass(frozen=True)
class Dismiss:
    action_id: str


CorrectionAction = Union[WaitForResult, RequestModelProposal, AskTeacher, PresentPreview, CommitCorrection,
                         RecordOverride, Dismiss, Abstain, Error]


def _candidates(events: list[Event]) -> list[dict]:
    seen: dict[str, dict] = {}
    for e in events:
        if e.type == "ModelProposalReturned":
            for c in e.payload["candidates"]:
                key = codec.digest([c.get("rule"), c.get("selector")])
                seen.setdefault(key, {"key": key, **c})
    return list(seen.values())


def _admissible(c: dict, d: Draft) -> Optional[dict]:
    """Return the candidate with its conflict set, or None when it must never be shown."""
    try:
        validate_rule(c["rule"])
        parse_selector(c["selector"])
    except (RuleError, SelectorError, KeyError, TypeError):
        return None
    if any(_forbidden_effect(c["rule"], sc) for sc in d.scenes.values()):
        return None
    if not item_fits(c["rule"], d.corrective)[0]:
        return None
    conflicts = [i.id for i in d.base_items if not item_fits(c["rule"], i)[0]]
    conflict_scenes = {i.scene_id for i in d.base_items if i.id in conflicts}
    exceptions = frozenset((i.scene_id, lid) for i in d.base_items if i.id in conflicts
                           for lid in (i.output or {}))
    base_rule = d.base["program"]["rule"]
    diff = behaviour_diff(base_rule, c["rule"], d.scenes, c["selector"], exceptions)
    if diff["unexplained"]:
        return None
    return {**c, "conflicts": conflicts, "conflict_scenes": conflict_scenes, "diff": diff}


def _selected(cands: list[dict]) -> dict:
    return min(cands, key=lambda c: (len(codec.dumps(c["rule"])), c["key"]))


def correction_step(events: list[Event], config: CorrectionConfig) -> CorrectionAction:
    if any(e.type in TERMINAL or e.type == "ActivationRejected" for e in events):
        return WaitForResult("terminal")
    for e in events:
        if e.type == "ModelCallFailed" and e.payload.get("terminal"):
            return Error(_aid(events, "Error"), f"provider: {e.payload['reason']}")
    issued = {e.payload["action_id"] for e in events if e.type == "ActionIssued"}
    done = {e.payload.get("action_id") for e in events if e.type in ("ModelProposalReturned", "ModelCallFailed")}
    req_actions = {e.payload["action_id"] for e in events if e.type == "RequestIssued"}
    answered = {e.payload["response"]["request_id"] for e in events if e.type == "ResponseRecorded"}
    open_requests = [e for e in events if e.type == "RequestIssued"
                     and e.payload["request"]["request_id"] not in answered]
    outstanding = [a for a in issued if a not in done and a not in req_actions]
    if outstanding or open_requests:
        return WaitForResult(outstanding[0] if outstanding else open_requests[0].payload["action_id"])

    d = derive_draft(events)
    if d.override:
        return RecordOverride(_aid(events, "RecordOverride"))
    if d.dismissed:
        return Dismiss(_aid(events, "Dismiss"))
    if d.cancelled:
        return Abstain(_aid(events, "Abstain"), "correction cancelled; the active version is unchanged")
    if not d.rounds:
        return RequestModelProposal(_aid(events, "RequestModelProposal"), "scope")

    cands = [a for c in _candidates(events) if (a := _admissible(c, d)) is not None]
    if d.authorized is None:
        if not cands and "revision" not in d.rounds and d.attempts < config.max_attempts:
            return RequestModelProposal(_aid(events, "RequestModelProposal"), "revision")
        if d.none_answered:
            if "revision" not in d.rounds and d.attempts < config.max_attempts:
                return RequestModelProposal(_aid(events, "RequestModelProposal"), "revision")
            return Abstain(_aid(events, "Abstain"), "no acceptable interpretation; the active version is unchanged")
        if d.clarifications >= config.max_clarifications:
            return Abstain(_aid(events, "Abstain"), "clarification budget exhausted")
        return _ask_scope(events, d, cands)

    inside = [c for c in cands if all(members(c["selector"], sc) == members(d.authorized["selector"], sc)
                                      for sc in d.scenes.values())]
    inside = [c for c in inside if all(item_fits(c["rule"], i)[0] for i in d.chosen_outputs + d.rejected_items)]
    if not inside:
        return Abstain(_aid(events, "Abstain"), "no program fits the authorized scope")
    for sid in sorted(d.scenes):
        groups = _groups(inside, d.scenes[sid])
        if len(groups) >= 2:
            if _usable(groups) and d.clarifications < config.max_clarifications:
                alts = tuple((chr(65 + k), out) for k, (out, _) in enumerate(groups))
                aid = _aid(events, "AskTeacher")
                return AskTeacher(aid, ChooseOutput(f"q-{aid}", sid, d.scene_hashes[sid], alts))
            return Abstain(_aid(events, "Abstain"), "unresolved disagreement inside the authorized scope")
    sel = _selected(inside)

    pending = [i for i in d.base_items if i.id in sel["conflicts"] and i.id not in d.superseded]
    if pending and not d.affected_used:
        if len(pending) > config.max_affected:
            return Abstain(_aid(events, "Abstain"), "too many affected examples to review")
        aid = _aid(events, "PresentPreview")
        items = tuple((i.id, i.scene_id, d.scene_hashes.get(i.scene_id, codec.digest(i.scene)),
                       run_output(sel["rule"], i.scene) or {}) for i in pending)
        return PresentPreview(aid, ConfirmPreview(f"p-{aid}", "affected_examples", items), sel["key"])
    if pending:
        return Abstain(_aid(events, "Abstain"), "an affected example was not approved; the active version is unchanged")

    if not d.revision_preview_used:
        base_rule = d.base["program"]["rule"]
        changed = [s for s in sorted(d.scenes) if s != d.corrective.scene_id
                   and run_output(base_rule, d.scenes[s]) != run_output(sel["rule"], d.scenes[s])]
        same = [s for s in sorted(d.scenes) if s != d.corrective.scene_id and s not in changed]
        chosen = (changed[:1] + same[:1] + [s for s in changed[1:] + same[1:]])[: config.max_revision_preview]
        if not chosen:
            return Abstain(_aid(events, "Abstain"), "no document available for the revision preview")
        aid = _aid(events, "PresentPreview")
        items = tuple((f"r{k}", s, d.scene_hashes[s], run_output(sel["rule"], d.scenes[s]) or {})
                      for k, s in enumerate(chosen))
        return PresentPreview(aid, ConfirmPreview(f"p-{aid}", "revision_preview", items), sel["key"])

    items = draft_items(d)
    misses = [i.id for i in items if not item_fits(sel["rule"], i)[0]]
    active_after = [i for i in d.base_items if i.id not in d.superseded]
    report = retention_report(sel["rule"], active_after, d.superseded, d.replacements, sel["diff"], len(d.scenes))
    if misses or report["scope_violations"] or report["unexplained_regressions"] or not d.preview_items:
        reason = "revision preview not approved" if not d.preview_items else f"checks failed: {misses[:3]}"
        return Abstain(_aid(events, "Abstain"), f"{reason}; the active version is unchanged")
    base = d.base
    artifact = {
        "skill_id": base["skill_id"],
        "parent_version": base["version"],
        "program": {"rule": sel["rule"], "summary": sel.get("summary", ""), "selector": sel["selector"]},
        "evidence": [item_to_json(i) for i in items],
        "superseded": d.superseded,
        "retention_report": report,
    }
    return CommitCorrection(_aid(events, "CommitCorrection"), sel["rule"], sel.get("summary", ""), sel["selector"],
                            artifact)


def _ask_scope(events: list[Event], d: Draft, cands: list[dict]) -> AskTeacher:
    revise: list[dict] = []
    for c in sorted(cands, key=lambda c: (len(codec.dumps(c["rule"])), c["key"])):
        sig = tuple(sorted((sid, members(c["selector"], sc)) for sid, sc in d.scenes.items()))
        if all(sig != r["sig"] for r in revise):
            revise.append({**c, "sig": sig})
        if len(revise) == 2:
            break
    cid = d.corrective.scene_id
    extra = None
    if len(revise) == 2:
        extra = next((s for s in sorted(d.scenes) if s != cid and run_output(revise[0]["rule"], d.scenes[s])
                      != run_output(revise[1]["rule"], d.scenes[s])), None)
    interps = []
    for k, c in enumerate(revise):
        shown = [cid] + ([extra] if extra else [])
        cons = tuple((s, d.scene_hashes[s], run_output(c["rule"], d.scenes[s]) or {}) for s in shown)
        interps.append(Interpretation(f"r{k}", "revise", c["selector"], c.get("summary", ""), cons))
    interps.append(Interpretation("ov", "override", None, "Keep this edit on this document only", ()))
    interps.append(Interpretation("ac", "accidental", None, "That edit was a mistake", ()))
    aid = _aid(events, "AskTeacher")
    return AskTeacher(aid, ConfirmCorrectionScope(f"c-{aid}", tuple(interps)))
```

Note on affected-example item ids: `ConfirmPreview.items` carry the BASE item id as the item id, so `derive_draft` knows which old item each approval supersedes. Base item ids are unique (`event_id:k`) and do not collide with `i0…`/`r0…` preview ids.

- [ ] **Step 5: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/teaching/test_correction_step.py -q`
Expected: 4 passed. If `test_scope_affected_and_revision_preview_complete_within_budget` stops at an `Abstain("no document available…")`, check that `OTHER` (registered as `o1`) differs between `BASE` and `NOTES` (its warning `l1` moves) — it must, since the base item `b1` conflicts there.

- [ ] **Step 6: Commit**

```bash
git add src/open_apprentice/teaching/corrections.py src/open_apprentice/teaching/correction_step.py tests/unit/teaching/test_correction_step.py
git commit -m "feat(teaching): transactional correction drafts and the pure correction policy"
```

---

### Task 8: Correction executor with compare-and-set activation

**Files:**
- Create: `src/open_apprentice/teaching/correction_executor.py`
- Test: `tests/unit/teaching/test_correction_executor.py`

**Interfaces:**
- Consumes: `correction_step`, actions, `SkillStore`, `ActivationRejected`, `Ledger`, `Executor` helpers (`failure_kind`, `well_formed`, `MAX_TRIES`), teacher validation, `derive_draft`.
- Produces:
  - `class ScopeProposer(Protocol): def propose_scope(self, evidence_json: dict, round_kind: str) -> tuple[list[dict], dict, Fraction]` (candidates `[{rule, selector, summary}]`)
  - `start_correction(store: Store, sid: str, skill_id: str, scene_id: str, scene: dict, corrected_output: Output, mask: list[str], extra_scenes: dict[str, dict], full_approval: bool = False, owner: str = "o") -> SessionLog` (reads the ACTIVE version and pointer generation; embeds the base artifact; registers the corrected scene's siblings: every scene in the base evidence plus `extra_scenes`)
  - `class CorrectionExecutor`: `__init__(self, store, log, proposer: ScopeProposer, teacher, ledger, config=CorrectionConfig(), worst_usd=Fraction(1, 5))`; `run(self, max_steps: int = 50) -> str` → `activated | activation_rejected | override | dismissed | abstained | error | waiting`

On `CommitCorrection`: `SkillStore.store_version(skill_id, artifact)` → `VersionStored{action_id, skill_id, version}` → `SkillStore.activate(skill_id, version, base_pointer_generation, operation_id=action_id, session_id=log.sid)` → `VersionActivated{operation_id, from, to, record_id}`; on `ActivationRejected` → `ActivationRejected{action_id, reason}` (the stored version remains, inactive). `RecordOverride` → `OverrideRecorded{scene_id, output}`; `Dismiss` → `CorrectionDismissed`.

- [ ] **Step 1: Write the failing tests**

```python
from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.evaluation.teacher_sim import SimTeacher
from open_apprentice.skills.versions import SkillStore
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.correction_executor import CorrectionExecutor, start_correction
from open_apprentice.teaching.evidence import EvidenceItem, item_to_json
from open_apprentice.teaching.step import run_output
from tests.unit.teaching.test_correction_step import BASE, NOTES, OTHER, SCENE

NEW = Spec("right", None, "notes", F(12))


class ScriptedScope:
    def __init__(self):
        self.calls = 0

    def propose_scope(self, evidence_json, round_kind):
        self.calls += 1
        return [{"rule": NOTES, "selector": 'o.role == "warning"', "summary": "warnings stay below"}], {}, F(1, 100)


def install_base(store):
    skills = SkillStore(store)
    item = EvidenceItem("b1", "full", "o1", OTHER, output=run_output(BASE, OTHER))
    skills.store_version("k", {"skill_id": "k", "program": {"rule": BASE, "summary": "right"},
                               "evidence": [item_to_json(item)], "superseded": {}, "retention_report": {}})
    skills.activate("k", 1, None, "op0", "learn")
    return skills


def corrected():
    out = run_output(BASE, SCENE)
    return dict(out, l1=(F(0), F(260)))


def teacher():
    intent = {"kind": "revise", "selector": 'o.role == "warning"', "diagnostic_scenes": ["c", "o1"], "new_spec": NEW}
    return SimTeacher(NEW, {"c": SCENE, "o1": OTHER}, scope_intent=intent)


def test_full_correction_activates_a_new_version(tmp_path):
    store = LocalStore(tmp_path)
    skills = install_base(store)
    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})
    status = CorrectionExecutor(store, log, ScriptedScope(), teacher(), Ledger(store, F(5))).run()
    assert status == "activated"
    v, _, _ = skills.active("k")
    assert v == 2 and skills.version("k", 2)["parent_version"] == 1
    assert skills.version("k", 2)["retention_report"]["unexplained_regressions"] == []


def test_second_concurrent_correction_is_rejected(tmp_path):
    store = LocalStore(tmp_path)
    skills = install_base(store)
    log_a = start_correction(store, "ca", "k", "c", SCENE, corrected(), ["l1"], {})
    log_b = start_correction(store, "cb", "k", "c", SCENE, corrected(), ["l1"], {})  # same base generation
    assert CorrectionExecutor(store, log_a, ScriptedScope(), teacher(), Ledger(store, F(5))).run() == "activated"
    pointer = skills.active("k")
    status = CorrectionExecutor(store, log_b, ScriptedScope(), teacher(), Ledger(store, F(5))).run()
    assert status == "activation_rejected"
    assert skills.active("k") == pointer  # the first correction is not overwritten


def test_failed_correction_does_not_change_the_pointer(tmp_path):
    store = LocalStore(tmp_path)
    skills = install_base(store)
    pointer = skills.active("k")

    class NoScope(ScriptedScope):
        def propose_scope(self, evidence_json, round_kind):
            self.calls += 1
            return [], {}, F(0)

    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})
    status = CorrectionExecutor(store, log, NoScope(), teacher(), Ledger(store, F(5))).run()
    assert status in ("abstained", "dismissed", "override")
    assert skills.active("k") == pointer
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/teaching/test_correction_executor.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `correction_executor.py`**

```python
"""Runs a correction cycle: same claim/record discipline as the learning executor; commits store an immutable version and
activate it only by compare-and-set against the pointer generation captured when the correction started."""

from __future__ import annotations

import uuid
from fractions import Fraction
from typing import Optional, Protocol

from open_apprentice.skills.versions import ActivationRejected, SkillStore
from open_apprentice.storage.store import Store
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger, OverBudget
from open_apprentice.teaching.correction_step import (
    CommitCorrection, CorrectionConfig, Dismiss, RecordOverride, correction_step,
)
from open_apprentice.teaching.corrections import derive_draft
from open_apprentice.teaching.events import Conflict, SessionLog
from open_apprentice.teaching.constraints import scene_from_payload
from open_apprentice.teaching.executor import MAX_TRIES, TRANSIENT, failure_kind
from open_apprentice.teaching.step import Abstain, AskTeacher, Error, PresentPreview, RequestModelProposal, WaitForResult
from open_apprentice.teaching.teacher import (
    Output, ProtocolError, Response, Teacher, _out_json, request_from_json, request_to_json, response_from_json,
    response_to_json, validate_request, validate_response,
)


class ScopeProposer(Protocol):
    def propose_scope(self, evidence_json: dict, round_kind: str) -> tuple[list[dict], dict, Fraction]: ...


def start_correction(
    store: Store,
    sid: str,
    skill_id: str,
    scene_id: str,
    scene: dict,
    corrected_output: Output,
    mask: list[str],
    extra_scenes: dict[str, dict],
    full_approval: bool = False,
    owner: str = "o",
) -> SessionLog:
    skills = SkillStore(store)
    version, _, generation = skills.active(skill_id)
    if version is None:
        raise ValueError(f"{skill_id} has no active version to correct")
    base = skills.version(skill_id, version)
    log = SessionLog(store, sid)
    log.create(owner=owner)
    log.append("CorrectionStarted", "human", {
        "skill_id": skill_id, "base_version": version, "base_pointer_generation": generation,
        "base_artifact": base, "scene_id": scene_id, "scene": codec.loads(codec.dumps(scene)),
        "scene_hash": codec.digest(scene), "corrected_output": _out_json(corrected_output),
        "mask": list(mask), "full_approval": full_approval})
    scenes = {i["scene_id"]: i["scene"] for i in base["evidence"]}
    scenes.update({k: codec.loads(codec.dumps(v)) for k, v in extra_scenes.items()})
    for k in sorted(scenes):
        if k == scene_id:
            continue
        log.append("SceneRegistered", "system", {"scene_id": k, "scene_hash": codec.digest(scene_from_payload(scenes[k])),
                                                 "scene": scenes[k], "role": "batch"})
    return log


class CorrectionExecutor:
    def __init__(self, store: Store, log: SessionLog, proposer: ScopeProposer, teacher: Teacher, ledger: Ledger,
                 config: CorrectionConfig = CorrectionConfig(), worst_usd: Fraction = Fraction(1, 5)) -> None:
        self.store, self.log, self.proposer, self.teacher = store, log, proposer, teacher
        self.ledger, self.config, self.worst = ledger, config, worst_usd

    def _claim(self, action_id: str) -> bool:
        return self.store.create(f"claims/{self.log.sid}/{action_id}.json", b"{}")

    def _status(self) -> Optional[str]:
        types = [e.type for e in self.log.events()]
        for t, s in (("VersionActivated", "activated"), ("ActivationRejected", "activation_rejected"),
                     ("OverrideRecorded", "override"), ("CorrectionDismissed", "dismissed"),
                     ("Abstained", "abstained"), ("Errored", "error")):
            if t in types:
                return s
        return None

    def _submit(self, resp: Response) -> None:
        evs = self.log.events()
        reqs = {request_from_json(e.payload["request"]).request_id: request_from_json(e.payload["request"])
                for e in evs if e.type == "RequestIssued"}
        answered = {response_from_json(e.payload["response"]).request_id for e in evs if e.type == "ResponseRecorded"}
        req = reqs.get(resp.request_id)
        if req is None or resp.request_id in answered:
            return
        validate_response(req, resp)
        origin = "simulator" if resp.source in ("simulator", "deterministic_simulator") else "human"
        self.log.append("ResponseRecorded", origin, {"response": response_to_json(resp)})

    def _propose(self, action: RequestModelProposal) -> None:
        self.log.append("ActionIssued", "system", {"action_id": action.action_id, "kind": "RequestModelProposal",
                                                   "round_kind": action.round_kind})
        d = derive_draft(self.log.events())
        evidence = {"base_program": d.base["program"], "corrected_scene": d.corrective.scene_id,
                    "corrected_labels": list(d.corrective.mask)}
        for attempt_no in range(1, MAX_TRIES + 1):
            attempt = uuid.uuid4().hex
            try:
                self.ledger.reserve(attempt, action.action_id, self.worst)
            except OverBudget as e:
                self.log.append("ModelCallFailed", "system", {"action_id": action.action_id, "reason": f"budget: {e}",
                                                              "terminal": True})
                return
            self.ledger.dispatched(attempt)
            try:
                cands, usage, cost = self.proposer.propose_scope(evidence, action.round_kind)
            except Exception as e:
                self.ledger.mark_unknown(attempt)
                kind = failure_kind(e)
                terminal = attempt_no == MAX_TRIES or kind not in TRANSIENT
                self.log.append("ModelCallFailed", "system", {"action_id": action.action_id, "reason": kind,
                                                              "terminal": terminal})
                if terminal:
                    return
                continue
            self.ledger.settle(attempt, cost)
            kept = [c for c in cands if isinstance(c, dict) and isinstance(c.get("rule"), list)
                    and isinstance(c.get("selector"), str)]
            self.log.append("ModelProposalReturned", "model", {"action_id": action.action_id, "candidates": kept,
                                                               "malformed": len(cands) - len(kept), "usage": usage})
            return

    def _ask(self, action: AskTeacher | PresentPreview) -> None:
        d = derive_draft(self.log.events())
        try:
            validate_request(action.request, d.scene_hashes)
        except ProtocolError as e:
            self.log.append("Errored", "system", {"action_id": action.action_id, "reason": f"protocol: {e}"})
            return
        self.log.append("ActionIssued", "system", {"action_id": action.action_id, "kind": type(action).__name__})
        self.log.append("RequestIssued", "system", {"request": request_to_json(action.request),
                                                    "action_id": action.action_id})
        try:
            self._submit(self.teacher.ask(action.request))
        except ProtocolError as e:
            self.log.append("Errored", "system", {"action_id": action.action_id, "reason": f"protocol: {e}"})

    def _commit(self, action: CommitCorrection) -> None:
        start = self.log.events()[0].payload
        skills = SkillStore(self.store)
        version = skills.store_version(start["skill_id"], action.artifact)
        self.log.append("VersionStored", "system", {"action_id": action.action_id, "skill_id": start["skill_id"],
                                                    "version": version})
        try:
            rid = skills.activate(start["skill_id"], version, start["base_pointer_generation"],
                                  action.action_id, self.log.sid)
        except ActivationRejected as e:
            self.log.append("ActivationRejected", "system", {"action_id": action.action_id, "reason": str(e),
                                                             "stored_version": version})
            return
        self.log.append("VersionActivated", "system", {"operation_id": action.action_id,
                                                       "from": start["base_version"], "to": version, "record_id": rid})

    def run(self, max_steps: int = 50) -> str:
        for _ in range(max_steps):
            s = self._status()
            if s:
                return s
            action = correction_step(self.log.events(), self.config)
            if isinstance(action, WaitForResult):
                s = self._status()
                if s:
                    return s
                if any(e.type == "VersionStored" for e in self.log.events()):
                    return "stored"
                return "waiting"
            if not self._claim(action.action_id):
                continue
            try:
                if isinstance(action, RequestModelProposal):
                    self._propose(action)
                elif isinstance(action, (AskTeacher, PresentPreview)):
                    self._ask(action)
                elif isinstance(action, CommitCorrection):
                    self._commit(action)
                elif isinstance(action, RecordOverride):
                    start = self.log.events()[0].payload
                    self.log.append("OverrideRecorded", "system", {"action_id": action.action_id,
                                                                   "scene_id": start["scene_id"],
                                                                   "output": start["corrected_output"]})
                elif isinstance(action, Dismiss):
                    self.log.append("CorrectionDismissed", "system", {"action_id": action.action_id})
                elif isinstance(action, Abstain):
                    self.log.append("Abstained", "system", {"action_id": action.action_id, "reason": action.reason})
                elif isinstance(action, Error):
                    self.log.append("Errored", "system", {"action_id": action.action_id, "reason": action.reason})
            except Conflict:
                continue
        return "waiting"
```

The registered hash is `codec.digest` of the decoded scene; requests embed the same hash, so teacher validation agrees by construction.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/teaching/test_correction_executor.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/open_apprentice/teaching/correction_executor.py tests/unit/teaching/test_correction_executor.py
git commit -m "feat(teaching): correction executor; versions activate by compare-and-set against the starting generation"
```

---

### Task 9: GCS store backend and a shared store contract test

**Files:**
- Modify: `pyproject.toml` / `uv.lock` (add `google-cloud-storage`)
- Create: `src/open_apprentice/storage/gcs.py`, `tests/unit/storage/__init__.py`, `tests/unit/storage/test_store_contract.py`

**Interfaces:**
- Produces: `class GcsStore`: `__init__(self, bucket, prefix: str = "")` where `bucket` is a `google.cloud.storage.Bucket` (or a test double with the same `blob(name)` API); methods `get`, `create`, `put` with the `Store` contract, using `if_generation_match` (0 = must not exist) and mapping `google.api_core.exceptions.PreconditionFailed` / `NotFound` to the contract.

- [ ] **Step 1: Add the dependency** (needs network; sandbox disabled):

Run: `uv add "google-cloud-storage>=2.18,<3"` then `.venv/bin/python -c "import google.cloud.storage, google.api_core.exceptions; print('ok')"`
Expected: `ok`. If `uv add` cannot run, stop and report: the dependency was approved in the design, but adding it changes the lockfile.

- [ ] **Step 2: Write the failing contract test** (runs against `LocalStore` and `GcsStore` over an in-memory fake bucket that enforces generation preconditions exactly like GCS):

```python
import threading

import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed as GcsPrecondition

from open_apprentice.storage.gcs import GcsStore
from open_apprentice.storage.store import LocalStore, PreconditionFailed


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name, self.generation = bucket, name, None

    def download_as_bytes(self):
        with self.bucket.lock:
            if self.name not in self.bucket.data:
                raise NotFound(self.name)
            data, gen = self.bucket.data[self.name]
            self.generation = gen
            return data

    def reload(self):
        with self.bucket.lock:
            if self.name not in self.bucket.data:
                raise NotFound(self.name)
            self.generation = self.bucket.data[self.name][1]

    def upload_from_string(self, data, if_generation_match=None):
        with self.bucket.lock:
            cur = self.bucket.data.get(self.name)
            cur_gen = cur[1] if cur else 0
            if if_generation_match is not None and if_generation_match != cur_gen:
                raise GcsPrecondition(self.name)
            self.bucket.counter += 1
            self.bucket.data[self.name] = (bytes(data), self.bucket.counter)
            self.generation = self.bucket.counter


class FakeBucket:
    def __init__(self):
        self.data, self.counter, self.lock = {}, 1000, threading.Lock()

    def blob(self, name):
        return FakeBlob(self, name)


@pytest.fixture(params=["local", "gcs"])
def store(request, tmp_path):
    return LocalStore(tmp_path) if request.param == "local" else GcsStore(FakeBucket(), prefix="t/")


def test_create_is_atomic(store):
    assert store.create("a", b"1") and not store.create("a", b"2") and store.get("a").data == b"1"


def test_put_cas(store):
    g = store.put("m", b"1", if_generation=None)
    with pytest.raises(PreconditionFailed):
        store.put("m", b"x", if_generation=None)
    g2 = store.put("m", b"2", if_generation=g)
    assert store.get("m").generation == g2 and store.get("m").data == b"2"
    with pytest.raises(PreconditionFailed):
        store.put("m", b"stale", if_generation=g)


def test_missing_is_none(store):
    assert store.get("nope") is None


def test_one_winner_under_contention(store):
    g = store.put("m", b"0", if_generation=None)
    wins = []

    def w(i):
        try:
            store.put("m", str(i).encode(), if_generation=g)
            wins.append(i)
        except PreconditionFailed:
            pass

    ts = [threading.Thread(target=w, args=(i,)) for i in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(wins) == 1
```

- [ ] **Step 3: Run to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/storage/test_store_contract.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'open_apprentice.storage.gcs'`

- [ ] **Step 4: Implement `gcs.py`**

```python
"""Google Cloud Storage backend for the Store contract. Immutable create = upload with if_generation_match=0; compare-and-
set = upload with if_generation_match=<expected generation>. Generations are GCS object generations."""

from __future__ import annotations

from typing import Any, Optional

from google.api_core.exceptions import NotFound
from google.api_core.exceptions import PreconditionFailed as GcsPreconditionFailed

from open_apprentice.storage.store import Blob, PreconditionFailed


class GcsStore:
    def __init__(self, bucket: Any, prefix: str = "") -> None:
        self.bucket, self.prefix = bucket, prefix

    def _blob(self, key: str) -> Any:
        if key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"bad key {key!r}")
        return self.bucket.blob(self.prefix + key)

    def get(self, key: str) -> Optional[Blob]:
        b = self._blob(key)
        try:
            data = b.download_as_bytes()
        except NotFound:
            return None
        return Blob(data, int(b.generation))

    def create(self, key: str, data: bytes) -> bool:
        try:
            self._blob(key).upload_from_string(data, if_generation_match=0)
        except GcsPreconditionFailed:
            return False
        return True

    def put(self, key: str, data: bytes, if_generation: Optional[int]) -> int:
        b = self._blob(key)
        try:
            b.upload_from_string(data, if_generation_match=0 if if_generation is None else if_generation)
        except GcsPreconditionFailed as e:
            raise PreconditionFailed(f"{key}: generation precondition failed") from e
        return int(b.generation)
```

Note: `download_as_bytes` sets `blob.generation` to the generation of the bytes returned in the real client (`google-cloud-storage` reads it from the response headers); the fake mirrors that. Real-bucket behaviour is verified only in the staging integration (Plan 3), after the owner approves the staging resources.

- [ ] **Step 5: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/storage -q`
Expected: 8 passed (4 tests × 2 backends).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/open_apprentice/storage/gcs.py tests/unit/storage
git commit -m "feat(storage): GCS backend with generation preconditions; shared store contract test"
```

---

### Task 10: Generated state-sequence tests (Hypothesis)

**Files:**
- Create: `tests/unit/teaching/test_stateful.py`, modify `tests/conftest.py` (register Hypothesis profiles `ci` and `dev`)

**Interfaces:**
- Consumes: `SessionLog`, `LocalStore`, `Ledger`, `SkillStore`, `ActivationRejected`.
- Produces: three `RuleBasedStateMachine`s: event log (appends, orphan-crash injection, concurrent writers) with the invariant that replay returns a gap-free chain with increasing `seq` and no orphan; ledger (reserve/dispatch/settle/unknown/release with random worst and actual costs under a cap) with the invariants that every attempt is in exactly one state, `total == settled + reserved + uncertain`, and `reserved + uncertain + settled ≤ cap + overrun` where overrun is only from settlement above worst (recorded as deferred minor #13 of Plan 1); versions (store, activate with the current or a stale generation, rollback) with the invariants that the pointer always references a stored version and `history()` is a chain whose last `to_version` equals the active version.

- [ ] **Step 1: Register profiles** — append to `tests/conftest.py`:

```python
from hypothesis import settings

settings.register_profile("ci", max_examples=200, derandomize=True, deadline=None)
settings.register_profile("dev", max_examples=1000, deadline=None)
settings.load_profile("ci")
```

- [ ] **Step 2: Write the state machines**

```python
import tempfile
from fractions import Fraction as F

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from open_apprentice.skills.versions import ActivationRejected, SkillStore
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger, OverBudget
from open_apprentice.teaching.events import Conflict, SessionLog


class EventLogMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.store = LocalStore(tempfile.mkdtemp())
        self.log = SessionLog(self.store, "s")
        self.log.create(owner="o")
        self.expected: list[str] = []

    @rule(t=st.sampled_from(["SceneRegistered", "ActionIssued", "ResponseRecorded"]))
    def append(self, t):
        ev = self.log.append(t, "system", {"n": len(self.expected)})
        self.expected.append(ev.event_id)

    @rule()
    def crash_before_manifest(self):
        orphan = {"event_id": f"orphan{len(self.expected)}", "prev_event_id": None, "seq": 99, "type": "X",
                  "origin": "system", "payload": {}, "caused_by": None}
        self.store.create(f"sessions/s/events/{orphan['event_id']}.json", codec.dumps(orphan))

    @rule()
    def stale_writer_loses(self):
        rev = self.log.manifest()[0]["manifest_revision"]
        other = SessionLog(self.store, "s")
        ev = other.append("ActionIssued", "system", {}, expected_revision=rev)
        self.expected.append(ev.event_id)
        try:
            self.log.append("ActionIssued", "system", {}, expected_revision=rev)
            raise AssertionError("stale writer must lose")
        except Conflict:
            pass

    @invariant()
    def replay_is_the_committed_chain(self):
        evs = self.log.events()
        assert [e.event_id for e in evs] == self.expected
        assert [e.seq for e in evs] == list(range(1, len(evs) + 1))


class LedgerMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.ledger = Ledger(LocalStore(tempfile.mkdtemp()), F(1))
        self.states: dict[str, str] = {}
        self.n = 0

    @rule(worst=st.fractions(min_value=F(1, 100), max_value=F(1, 3)))
    def reserve(self, worst):
        self.n += 1
        aid = f"a{self.n}"
        try:
            self.ledger.reserve(aid, "act", worst)
            self.states[aid] = "reserved"
        except OverBudget:
            pass

    @precondition(lambda self: any(s == "reserved" for s in self.states.values()))
    @rule(data=st.data())
    def dispatch_or_release(self, data):
        aid = data.draw(st.sampled_from(sorted(a for a, s in self.states.items() if s == "reserved")))
        if data.draw(st.booleans()):
            self.ledger.dispatched(aid)
            self.states[aid] = "dispatched"
        else:
            self.ledger.fail_before_dispatch(aid)
            self.states[aid] = "released"

    @precondition(lambda self: any(s == "dispatched" for s in self.states.values()))
    @rule(data=st.data(), actual=st.fractions(min_value=F(0), max_value=F(1, 3)))
    def settle_or_lose(self, data, actual):
        aid = data.draw(st.sampled_from(sorted(a for a, s in self.states.items() if s == "dispatched")))
        if data.draw(st.booleans()):
            self.ledger.settle(aid, actual)
            self.states[aid] = "completed"
        else:
            self.ledger.mark_unknown(aid)
            self.states[aid] = "outcome_unknown"

    @invariant()
    def one_state_each_and_totals_add_up(self):
        for aid, s in self.states.items():
            assert self.ledger.state(aid) == s
        e = self.ledger.exposure()
        assert e["total"] == e["settled"] + e["reserved"] + e["uncertain"]


class VersionMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.skills = SkillStore(LocalStore(tempfile.mkdtemp()))
        self.stored = 0
        self.ops = 0

    @rule(tag=st.integers(0, 5))
    def store(self, tag):
        self.stored = max(self.stored, self.skills.store_version("k", {"skill_id": "k", "program": {"rule": [tag]},
                                                                       "evidence": [], "superseded": {}}))

    @precondition(lambda self: self.stored > 0)
    @rule(data=st.data(), stale=st.booleans())
    def activate(self, data, stale):
        v = data.draw(st.integers(1, self.stored))
        _, _, g = self.skills.active("k")
        self.ops += 1
        try:
            self.skills.activate("k", v, (g or 0) + 7 if stale else g, f"op{self.ops}", "s")
            assert not stale
        except ActivationRejected:
            assert stale

    @invariant()
    def pointer_references_a_stored_version_and_history_ends_there(self):
        v, _, _ = self.skills.active("k")
        if v is None:
            return
        self.skills.version("k", v)
        h = self.skills.history("k")
        assert h and h[-1]["to_version"] == v
        for a, b in zip(h, h[1:]):
            assert b["from_version"] == a["to_version"]


TestEventLog = EventLogMachine.TestCase
TestLedger = LedgerMachine.TestCase
TestVersions = VersionMachine.TestCase
```

- [ ] **Step 3: Run**

Run: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit/teaching/test_stateful.py -q`
Expected: 3 passed. A failure prints a minimal action sequence: treat it as a bug in the code under test (systematic-debugging), not in the machine, unless the machine asserts something the spec does not require (then record a ruling).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/teaching/test_stateful.py tests/conftest.py
git commit -m "test: generated state sequences for the event log, ledger and versions (Hypothesis ci profile)"
```

---

### Task 11: Staging proposal, prompt file, audit, full suite

**Files:**
- Create: `docs/deploy_staging_proposal.md`, `prompts/correction_scope.md`
- Modify: `docs/implementation_audit.md`

- [ ] **Step 1: Write `docs/deploy_staging_proposal.md`** with: purpose (spec §10 early staging integration: render+measure one diagram with the pinned viewer and bundled font, one real GCS conditional update and a lost race, one authenticated Cloud Tasks dispatch with a scripted provider, restart and verify persisted state); resources in project `oa-demo-1013-19737`, region `us-central1`: a bucket `oa-staging-<suffix>` (standard, uniform access, 7-day lifecycle delete), a Cloud Tasks queue `oa-staging` (max dispatch 1/s), a service account `oa-staging-worker` with `roles/storage.objectAdmin` on the bucket and `roles/run.invoker` on a staging Cloud Run service `open-apprentice-staging` (min instances 0, max 1, 1 GiB); exact `gcloud` commands; teardown commands; cost estimate (storage and Tasks free tier at this volume; Cloud Run idle at 0 instances; estimate under SGD 1 for the week, to be confirmed against the console); and the explicit statement that nothing is created until the owner approves.

- [ ] **Step 2: Write `prompts/correction_scope.md`** — the live proposal prompt for scope interpretations: explains the corrected document (original input, the labels the user moved and to where, which labels were NOT touched), the current program (text form), the grammar section (same as `prompts/hypotheses_labels.md`), and asks for up to 3 candidates `{"summary", "rule_text", "selector"}` where `selector` is ONE expression over `o` and `object(o.attached)` (role, attachment, original geometry), each candidate reproducing the corrected labels exactly and changing nothing outside its selector except where it states so in the summary. Include the instruction that untouched labels are not approvals.

- [ ] **Step 3: Update `docs/implementation_audit.md`** rows for §3.1 activation records, §3.4 ConfirmCorrectionScope, §3.5 corrective-edit rows, §5 (drafts, scope, supersession, retention, activation), §9 B (stateful tests), §10 (staging proposal: proposed, not created), with the new test names.

- [ ] **Step 4: Full suite and checks**

Run: `OA_ENGINE_TESTS=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q tests` (sandbox disabled), `.venv/bin/ruff check src tests scripts`, `.venv/bin/black --check src tests scripts`, `PYTHONPATH=src .venv/bin/lint-imports`, and the Python 3.12 run `PYTHONPATH=src:. <venv312>/bin/python -m pytest -q tests/unit tests/evaluation tests/contracts`.
Expected: all pass; read every output.

- [ ] **Step 5: Commit**

```bash
git add docs/deploy_staging_proposal.md prompts/correction_scope.md docs/implementation_audit.md
git commit -m "docs: staging proposal (not created), correction scope prompt, audit update"
```

---

## Self-review (completed while writing)

- **Spec coverage:** 3.1 activation records (Task 2), 3.4 ConfirmCorrectionScope + per-type validation (Task 4), 3.5 corrective-edit and scope rows (Tasks 1, 7), 3.7 correction budgets (Task 7 `CorrectionConfig`, Task 8 attempt accounting), 5 drafts/three states/partial vs full/scope selectors/affected examples/replacements/supersession/revision preview/retention/activation/conflicts-by-generation (Tasks 3, 5, 7, 8), 9 B stateful tests (Task 10), 10 staging proposal (Task 11). Definite-conflict detection between incompatible evidence (spec 5 "Conflicts") is handled as "no candidate fits" plus abstention in this plan; an explicit `ConflictDetected` event is deferred to Plan 5's inconsistent-demonstration stratum, where it is scored.
- **Interface consistency:** `EvidenceItem`, `item_fits`, `item_to_json/from_json`, `members`, `Interpretation`, `ConfirmCorrectionScope`, `behaviour_diff`, `retention_report`, `Draft`, `derive_draft`, `draft_items`, `CorrectionConfig`, `CommitCorrection`, `SkillStore`, `ActivationRejected`, `start_correction`, `CorrectionExecutor` are used with the same names and signatures across Tasks 1–10.
- **Known simplifications (named):** the correction proposer receives a compact base description, not a rendered image; generated probes are not used in correction clarification (batch/registered scenes only, as in Plan 1); the deferred Plan 1 minor #13 (settle above worst) is visible in the ledger state machine but not fixed.
