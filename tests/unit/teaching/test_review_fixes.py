"""Regression tests for the Plan 1 whole-branch review findings (each failed before its fix)."""

import subprocess
import sys
import os
import threading
from fractions import Fraction as F


from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.constraints import derive
from open_apprentice.teaching.events import Event, SessionLog
from open_apprentice.teaching.executor import Executor
from open_apprentice.teaching.step import (
    AskTeacher,
    CommitVersion,
    PresentPreview,
    RequestModelProposal,
    StepConfig,
    WaitForResult,
    run_output,
    step,
)
from open_apprentice.teaching.teacher import (
    ChooseOutput,
    ConfirmPreview,
    ProtocolError,
    Response,
    request_to_json,
    response_to_json,
)

BLOCKED = {
    "objects": [
        {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
        {
            "id": "n1",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": 120,
            "y": 0,
            "w": 60,
            "h": 50,
        },
        {
            "id": "l0",
            "kind": "label",
            "role": "note",
            "attached": "n0",
            "x": 0,
            "y": 60,
            "w": 40,
            "h": 20,
        },
    ],
    "canvas": {"w": 600, "h": 400},
}
CLEAR = {"objects": [o for o in BLOCKED["objects"] if o["id"] != "n1"], "canvas": BLOCKED["canvas"]}
RIGHT = rule_for_spec(Spec("right", None, "all", F(12)))
FALLBACK = rule_for_spec(Spec("right", "below", "all", F(12)))
CFG = StepConfig()


class Log:
    def __init__(self):
        self.evs: list[Event] = []

    def add(self, t, payload, origin="system"):
        n = len(self.evs) + 1
        self.evs.append(Event(f"e{n}", f"e{n-1}" if n > 1 else None, n, t, origin, payload))


def reg(log, sid, scene, role):
    log.add(
        "SceneRegistered",
        {
            "scene_id": sid,
            "scene_hash": codec.digest(scene),
            "scene": codec.loads(codec.dumps(scene)),
            "role": role,
        },
    )


def demo(log):
    reg(log, "d", CLEAR, "demo")
    log.add(
        "DemonstrationRecorded",
        {"scene_id": "d", "output": codec.loads(codec.dumps(run_output(RIGHT, CLEAR)))},
        "human",
    )


def proposals(log, rules):
    a = step(log.evs, CFG)
    assert isinstance(a, RequestModelProposal)
    log.add(
        "ActionIssued",
        {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": a.round_kind},
    )
    log.add(
        "ModelProposalReturned",
        {
            "action_id": a.action_id,
            "usage": {},
            "candidates": [{"rule": r, "summary": s, "text": ""} for r, s in rules],
        },
        "model",
    )


# 1 (Critical): an answered question is not an approved preview
def test_question_answer_alone_never_commits():
    log = Log()
    demo(log)
    reg(log, "b1", BLOCKED, "batch")
    reg(log, "b2", CLEAR, "batch")
    proposals(log, [(RIGHT, "right"), (FALLBACK, "fallback")])
    a = step(log.evs, CFG)
    assert isinstance(a, AskTeacher)
    log.add("ActionIssued", {"action_id": a.action_id, "kind": "AskTeacher"})
    log.add("RequestIssued", {"request": request_to_json(a.request), "action_id": a.action_id})
    pick = next(k for k, o in a.request.alternatives if o == run_output(FALLBACK, BLOCKED))
    log.add(
        "ResponseRecorded",
        {"response": response_to_json(Response(a.request.request_id, "choose", selected=pick))},
        "simulator",
    )
    nxt = step(log.evs, CFG)
    if isinstance(nxt, RequestModelProposal):
        log.add(
            "ActionIssued",
            {
                "action_id": nxt.action_id,
                "kind": "RequestModelProposal",
                "round_kind": nxt.round_kind,
            },
        )
        log.add(
            "ModelProposalReturned",
            {"action_id": nxt.action_id, "usage": {}, "candidates": []},
            "model",
        )
        nxt = step(log.evs, CFG)
    assert not isinstance(nxt, CommitVersion)
    assert isinstance(nxt, PresentPreview)


# 2 (Important): one request, one response
def test_derive_counts_only_the_first_response_per_request():
    log = Log()
    reg(log, "b", CLEAR, "batch")
    h = codec.digest(CLEAR)
    q = ChooseOutput("q1", "b", h, (("A", {"l0": (F(112), F(15))}), ("B", {"l0": (F(30), F(62))})))
    log.add("RequestIssued", {"request": request_to_json(q), "action_id": "a"})
    log.add(
        "ResponseRecorded",
        {"response": response_to_json(Response("q1", "choose", selected="A"))},
        "human",
    )
    log.add("ResponseRecorded", {"response": response_to_json(Response("q1", "none"))}, "human")
    e = derive(log.evs)
    assert len(e.positives) == 1 and not e.negatives


def test_submit_response_commits_against_the_revision_it_checked(tmp_path, monkeypatch):
    store, log = _session(tmp_path)
    ex = Executor(store, log, _Proposer(), _Teacher(), Ledger(store, F(5)), CFG)
    seen = {}
    real = log.append

    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)

    rid = "p-x"
    log.append(
        "RequestIssued",
        "system",
        {
            "request": request_to_json(
                ConfirmPreview(
                    rid,
                    "learning_preview",
                    (("i0", "b1", codec.digest(CLEAR), run_output(RIGHT, CLEAR)),),
                )
            ),
            "action_id": "x",
        },
    )
    monkeypatch.setattr(log, "append", spy)
    assert ex.submit_response(Response(rid, "items", per_item=(("i0", "approve"),)))
    assert seen.get("expected_revision") is not None


# 3 (Important): failures never wedge a session
def test_teacher_protocol_error_is_recorded_not_raised(tmp_path):
    store, log = _session(tmp_path)

    class Bad(_Teacher):
        def ask(self, req):
            raise ProtocolError("two alternatives match")

    status = Executor(store, log, _Proposer(), Bad(), Ledger(store, F(5)), CFG).run()
    assert status == "error"
    assert any(e.type == "Errored" and "protocol" in e.payload["reason"] for e in log.events())


def test_interrupted_model_action_is_recovered_as_error(tmp_path):
    store, log = _session(tmp_path)
    a = step(log.events(), CFG)
    store.create(f"claims/{a.action_id}.json", b"{}")
    log.append(
        "ActionIssued",
        "system",
        {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": "initial"},
    )
    status = Executor(store, log, _Proposer(), _Teacher(), Ledger(store, F(5)), CFG).run()
    assert status == "error"


def test_append_without_expected_revision_retries_on_a_lost_race(tmp_path):
    store = LocalStore(tmp_path)
    log = SessionLog(store, "s")
    log.create(owner="o")
    real_put = store.put
    calls = {"n": 0}

    def racing_put(key, data, if_generation):
        calls["n"] += 1
        if calls["n"] == 1 and key.endswith("manifest.json"):
            other = SessionLog(LocalStore(tmp_path), "s")
            store.put = real_put
            other.append("SceneRegistered", "system", {"scene_id": "x"})
            store.put = racing_put
        return real_put(key, data, if_generation)

    store.put = racing_put
    log.append("SceneRegistered", "system", {"scene_id": "y"})
    assert [e.payload["scene_id"] for e in log.events()] == ["x", "y"]


# 4 (Important): no second terminal result
def test_step_waits_after_errored_is_recorded():
    log = Log()
    demo(log)
    a = step(log.evs, CFG)
    log.add(
        "ActionIssued",
        {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": "initial"},
    )
    log.add("ModelCallFailed", {"action_id": a.action_id, "reason": "truncation", "terminal": True})
    log.add("Errored", {"action_id": "err", "reason": "provider"})
    assert isinstance(step(log.evs, CFG), WaitForResult)


# 5 (Important): only transient failures retry; attempts never exceed the budget
def test_format_error_is_not_retried(tmp_path):
    store, log = _session(tmp_path)

    class FormatBad(_Proposer):
        def propose(self, ev, kind, fb):
            self.calls += 1
            raise ValueError("model reply was not valid JSON")

    p = FormatBad()
    status = Executor(store, log, p, _Teacher(), Ledger(store, F(5)), CFG).run()
    assert status == "error" and p.calls == 1
    fail = next(e for e in log.events() if e.type == "ModelCallFailed")
    assert fail.payload["reason"] == "format"


def test_attempts_never_exceed_the_budget(tmp_path):
    store, log = _session(tmp_path)

    class AlwaysTimeout(_Proposer):
        def propose(self, ev, kind, fb):
            self.calls += 1
            raise TimeoutError("read timeout")

    p = AlwaysTimeout()
    Executor(store, log, p, _Teacher(), Ledger(store, F(5)), StepConfig(max_attempts=1)).run()
    assert p.calls == 1


# 6 (Important): the guard refuses to start in a process that already loaded the evaluator
def test_guard_refuses_when_evaluator_already_loaded():
    env = {**os.environ, "PYTHONPATH": "src"}
    code = (
        "import open_apprentice.evaluation.labels\n"
        "from open_apprentice.teaching.isolation import install_learner_guard\n"
        "install_learner_guard()\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert r.returncode != 0 and "already loaded" in r.stderr


# 7: an unaskable disagreement uses the contrastive round before abstaining
def test_unaskable_disagreement_tries_contrastive_first():
    warn_only = {
        "objects": [CLEAR["objects"][0], dict(CLEAR["objects"][1], role="warning")],
        "canvas": CLEAR["canvas"],
    }
    g12 = rule_for_spec(Spec("right", None, "notes", F(12)))
    g125 = rule_for_spec(
        Spec("right", None, "notes", F(25, 2))
    )  # 0.5 apart on notes: cannot be asked
    log = Log()
    reg(log, "d", warn_only, "demo")  # nothing moves in the demo, so both fit
    log.add(
        "DemonstrationRecorded",
        {"scene_id": "d", "output": codec.loads(codec.dumps(run_output(g12, warn_only)))},
        "human",
    )
    reg(log, "b1", CLEAR, "batch")
    proposals(log, [(g12, "gap 12"), (g125, "gap 12.5")])
    a = step(log.evs, CFG)
    assert isinstance(a, RequestModelProposal) and a.round_kind == "contrastive"


# 10: only teacher-origin events create intent
def test_non_teacher_origin_creates_no_intent():
    log = Log()
    reg(log, "d", CLEAR, "demo")
    log.add("DemonstrationRecorded", {"scene_id": "d", "output": {"l0": [112, 15]}}, "model")
    assert not derive(log.evs).positives


# 11: malformed model candidates never crash step
def test_malformed_candidates_are_dropped_at_the_boundary(tmp_path):
    store, log = _session(tmp_path)

    class Junk(_Proposer):
        def propose(self, ev, kind, fb):
            self.calls += 1
            return (
                ([{"summary": "no rule"}, {"rule": "not a list"}] if kind == "initial" else []),
                {},
                F(0),
            )

    status = Executor(store, log, Junk(), _Teacher(), Ledger(store, F(5)), CFG).run()
    assert status in ("abstained", "error")


# 12: concurrent readers never see a half-written generation
def test_concurrent_get_never_raises(tmp_path):
    s = LocalStore(tmp_path)
    s.put("m", b"0", if_generation=None)
    errors: list[Exception] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                s.get("m")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

    t = threading.Thread(target=reader)
    t.start()
    for _ in range(300):
        b = s.get("m")
        try:
            s.put("m", b"x", if_generation=b.generation)
        except Exception:  # noqa: BLE001
            pass
    stop.set()
    t.join()
    assert not errors


class _Proposer:
    def __init__(self):
        self.calls = 0

    def propose(self, ev, kind, fb):
        self.calls += 1
        return (
            ([{"rule": RIGHT, "summary": "right", "text": ""}] if kind == "initial" else []),
            {},
            F(1, 100),
        )


class _Teacher:
    def ask(self, req):
        return Response(
            req.request_id,
            "items",
            per_item=tuple((i[0], "approve") for i in req.items),
            source="simulator",
        )


def _session(tmp_path):
    store = LocalStore(tmp_path)
    log = SessionLog(store, "s1")
    log.create(owner="o")
    for sid, role in (("d", "demo"), ("b1", "batch")):
        log.append(
            "SceneRegistered",
            "system",
            {
                "scene_id": sid,
                "scene_hash": codec.digest(CLEAR),
                "scene": codec.loads(codec.dumps(CLEAR)),
                "role": role,
            },
        )
    log.append(
        "DemonstrationRecorded",
        "human",
        {"scene_id": "d", "output": codec.loads(codec.dumps(run_output(RIGHT, CLEAR)))},
    )
    return store, log
