"""Regression tests for the Plan 2 whole-branch review findings (each failed before its fix)."""

from fractions import Fraction as F

import pytest
from google.api_core.exceptions import NotFound
from google.api_core.exceptions import PreconditionFailed as GcsPrecondition

from open_apprentice.skills.versions import SkillStore
from open_apprentice.storage.gcs import GcsStore
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.correction_executor import CorrectionExecutor, start_correction
from open_apprentice.teaching.correction_step import CorrectionConfig, correction_step
from open_apprentice.teaching.executor import Executor
from open_apprentice.teaching.scope import SelectorError, parse_selector
from open_apprentice.teaching.step import StepConfig, step
from tests.unit.teaching.test_correction_executor import (
    ScriptedScope,
    corrected,
    install_base,
    teacher,
)
from tests.unit.teaching.test_correction_step import SCENE, Log, propose, started
from tests.unit.teaching.test_executor import ApprovingTeacher, CountingProposer
from tests.unit.teaching.test_executor import start as learning_start


# ---- Important 1: a correction session never wedges after a crash
def test_crash_between_version_stored_and_activation_is_recovered(tmp_path, monkeypatch):
    store = LocalStore(tmp_path)
    skills = install_base(store)
    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})
    real = SkillStore.activate
    calls = {"n": 0}

    def crashing(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("process died before the pointer moved")
        return real(self, *a, **k)

    monkeypatch.setattr(SkillStore, "activate", crashing)
    with pytest.raises(RuntimeError):
        CorrectionExecutor(store, log, ScriptedScope(), teacher(), Ledger(store, F(5))).run()
    status = CorrectionExecutor(store, log, ScriptedScope(), teacher(), Ledger(store, F(5))).run()
    assert status == "activated" and skills.active("k")[0] == 2


def test_claim_without_any_event_is_recovered_not_spun_on(tmp_path):
    store = LocalStore(tmp_path)
    install_base(store)
    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})
    a = correction_step(log.events(), CorrectionConfig())
    store.create(f"claims/{log.sid}/{a.action_id}.json", b"{}")  # crashed right after claiming
    status = CorrectionExecutor(store, log, ScriptedScope(), teacher(), Ledger(store, F(5))).run()
    assert status == "activated"


def test_learning_executor_recovers_a_claim_without_any_event(tmp_path):
    store, log = learning_start(tmp_path)
    a = step(log.events(), StepConfig())
    store.create(f"claims/{a.action_id}.json", b"{}")
    assert (
        Executor(
            store, log, CountingProposer(), ApprovingTeacher(), Ledger(store, F(5)), StepConfig()
        ).run()
        == "committed"
    )


def test_interrupted_scope_proposal_is_recorded_as_error(tmp_path):
    store = LocalStore(tmp_path)
    install_base(store)
    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})
    a = correction_step(log.events(), CorrectionConfig())
    store.create(f"claims/{log.sid}/{a.action_id}.json", b"{}")
    log.append(
        "ActionIssued",
        "system",
        {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": "scope"},
    )
    assert (
        CorrectionExecutor(store, log, ScriptedScope(), teacher(), Ledger(store, F(5))).run()
        == "error"
    )


def test_asynchronous_human_answer_can_be_submitted(tmp_path):
    store = LocalStore(tmp_path)
    install_base(store)
    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})

    class Later:
        def ask(self, req):
            return None  # handed to a person

    ex = CorrectionExecutor(store, log, ScriptedScope(), Later(), Ledger(store, F(5)))
    assert ex.run() == "waiting"
    from open_apprentice.teaching.teacher import Response, request_from_json

    req = request_from_json(
        next(e for e in log.events() if e.type == "RequestIssued").payload["request"]
    )
    revise = next(i.interp_id for i in req.interpretations if i.kind == "revise")
    assert ex.submit_response(Response(req.request_id, "select", selected=revise)) is True
    assert (
        ex.submit_response(Response(req.request_id, "select", selected=revise)) is False
    )  # duplicate


# ---- Important 2: an approved base item does not whitelist unrelated labels on its scene
def test_supersession_records_the_changed_labels():
    from open_apprentice.teaching.corrections import derive_draft
    from tests.unit.teaching.test_correction_step import WARN, answer, base_items, select_revise
    from open_apprentice.teaching.teacher import Response

    log = Log()
    started(log, base_items())
    propose(log, [WARN])
    select_revise(log)
    b = correction_step(log.evs, CorrectionConfig())
    answer(
        log,
        b,
        Response(
            b.request.request_id,
            "items",
            per_item=tuple((i[0], "approve") for i in b.request.items),
        ),
    )
    assert derive_draft(log.evs).superseded["b1"]["changed_labels"] == ["l1"]


# ---- Important 3: a GCS conditional write whose response was lost is not misreported
class LossyBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name, self.generation = bucket, name, None

    def download_as_bytes(self):
        if self.name not in self.bucket.data:
            raise NotFound(self.name)
        data, self.generation = self.bucket.data[self.name]
        return data

    def upload_from_string(self, data, if_generation_match=None):
        cur = self.bucket.data.get(self.name)
        if if_generation_match is not None and if_generation_match != (cur[1] if cur else 0):
            raise GcsPrecondition(self.name)
        self.bucket.counter += 1
        self.bucket.data[self.name] = (bytes(data), self.bucket.counter)
        self.generation = self.bucket.counter
        if self.bucket.lose_next:
            self.bucket.lose_next = False
            raise GcsPrecondition("retry of a write that already landed")


class LossyBucket:
    def __init__(self):
        self.data, self.counter, self.lose_next = {}, 100, False

    def blob(self, name):
        return LossyBlob(self, name)


def test_lost_response_put_is_recognised_as_our_write():
    b = LossyBucket()
    s = GcsStore(b)
    g = s.put("m", b"1", if_generation=None)
    b.lose_next = True
    g2 = s.put("m", b"2", if_generation=g)
    assert s.get("m").data == b"2" and s.get("m").generation == g2


def test_lost_response_create_is_recognised_as_our_write():
    b = LossyBucket()
    b.lose_next = True
    assert GcsStore(b).create("a", b"x") is True


# ---- Minor 1: an escaped newline is refused too
def test_escaped_newline_selector_is_refused():
    with pytest.raises(SelectorError):
        parse_selector("(o.x >\\n 0)")


# ---- Minor 2: correction retries respect the attempt budget
def test_correction_retry_respects_the_attempt_budget(tmp_path):
    store = LocalStore(tmp_path)
    install_base(store)
    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})

    class Timeouts(ScriptedScope):
        def propose_scope(self, evidence_json, round_kind):
            self.calls += 1
            raise TimeoutError("read timeout")

    p = Timeouts()
    CorrectionExecutor(
        store, log, p, teacher(), Ledger(store, F(5)), CorrectionConfig(max_attempts=1)
    ).run()
    assert p.calls == 1


# ---- Minor 4: the user can abandon a correction after approving affected examples; nothing stored changes
def test_abandon_after_affected_approval_leaves_stored_version_and_pointer(tmp_path):
    store = LocalStore(tmp_path)
    skills = install_base(store)
    v1 = skills.version("k", 1)
    pointer = skills.active("k")
    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})

    class StopAfterAffected:
        def __init__(self):
            self.t = teacher()

        def ask(self, req):
            if getattr(req, "purpose", "") == "revision_preview":
                return None  # the person has not answered
            return self.t.ask(req)

    ex = CorrectionExecutor(store, log, ScriptedScope(), StopAfterAffected(), Ledger(store, F(5)))
    assert ex.run() == "waiting"
    assert any(
        e.type == "RequestIssued" and e.payload["request"]["type"] == "ConfirmPreview"
        for e in log.events()
    )
    ex.abandon()
    assert ex.run() == "abstained"
    assert skills.version("k", 1) == v1 and skills.active("k") == pointer
    with pytest.raises(KeyError):
        skills.version("k", 2)
