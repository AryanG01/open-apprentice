from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.events import SessionLog
from open_apprentice.teaching.executor import Executor
from open_apprentice.teaching.step import StepConfig, run_output
from open_apprentice.teaching.teacher import ConfirmPreview, Response

RIGHT = rule_for_spec(Spec("right", None, "all", F(12)))
SCENE = {
    "objects": [
        {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
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


class CountingProposer:
    def __init__(self):
        self.calls = 0

    def propose(self, evidence_json, round_kind, feedback):
        self.calls += 1
        cands = [{"rule": RIGHT, "summary": "right", "text": ""}] if round_kind == "initial" else []
        return cands, {}, F(1, 100)


class ApprovingTeacher:
    def __init__(self):
        self.asked = 0

    def ask(self, req):
        self.asked += 1
        assert isinstance(req, ConfirmPreview)
        verdicts = tuple((i[0], "approve") for i in req.items)
        return Response(req.request_id, "items", per_item=verdicts, source="simulator")


def start(tmp_path):
    store = LocalStore(tmp_path)
    log = SessionLog(store, "s1")
    log.create(owner="o")
    for sid, role in (("d", "demo"), ("b1", "batch")):
        log.append(
            "SceneRegistered",
            "system",
            {
                "scene_id": sid,
                "scene_hash": codec.digest(SCENE),
                "scene": codec.loads(codec.dumps(SCENE)),
                "role": role,
            },
        )
    out = codec.loads(codec.dumps(run_output(RIGHT, SCENE)))
    log.append("DemonstrationRecorded", "human", {"scene_id": "d", "output": out})
    return store, log


def test_full_episode_commits_with_scripted_proposer_and_teacher(tmp_path):
    store, log = start(tmp_path)
    p, t = CountingProposer(), ApprovingTeacher()
    status = Executor(store, log, p, t, Ledger(store, F(5)), StepConfig()).run()
    assert status == "committed" and t.asked == 1
    assert [e.type for e in log.events()].count("VersionStored") == 1


def test_replay_is_effect_free(tmp_path):
    store, log = start(tmp_path)
    p, t = CountingProposer(), ApprovingTeacher()
    ledger = Ledger(store, F(5))
    Executor(store, log, p, t, ledger, StepConfig()).run()
    before = (p.calls, t.asked, len(log.events()), ledger.exposure()["total"])
    # a second executor over the same committed log (restart, duplicate delivery) must do nothing
    Executor(store, SessionLog(store, "s1"), p, t, ledger, StepConfig()).run()
    assert (p.calls, t.asked, len(log.events()), ledger.exposure()["total"]) == before


def test_response_to_answered_request_is_rejected(tmp_path):
    store, log = start(tmp_path)
    ex = Executor(
        store, log, CountingProposer(), ApprovingTeacher(), Ledger(store, F(5)), StepConfig()
    )
    ex.run()
    rid = next(
        e.payload["request"]["request_id"] for e in log.events() if e.type == "RequestIssued"
    )
    n = len(log.events())
    assert ex.submit_response(Response(rid, "items", per_item=(("i0", "reject"),))) is False
    assert len(log.events()) == n


class FlakyProposer(CountingProposer):
    def propose(self, evidence_json, round_kind, feedback):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("transport")
        return super().propose(evidence_json, round_kind, feedback)


def test_one_transient_failure_is_retried_and_stays_in_the_accounting(tmp_path):
    store, log = start(tmp_path)
    p, t = FlakyProposer(), ApprovingTeacher()
    ledger = Ledger(store, F(5))
    status = Executor(store, log, p, t, ledger, StepConfig(), worst_usd=F(1, 5)).run()
    assert status == "committed"
    fails = [e for e in log.events() if e.type == "ModelCallFailed"]
    assert len(fails) == 1 and fails[0].payload["terminal"] is False
    assert ledger.exposure()["uncertain"] == F(1, 5)  # the failed attempt stays at worst case
