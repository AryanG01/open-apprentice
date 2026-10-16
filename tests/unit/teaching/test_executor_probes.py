from fractions import Fraction as F

from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.events import SessionLog
from open_apprentice.teaching.executor import Executor
from open_apprentice.teaching.probes import ProbeResult
from open_apprentice.teaching.step import StepConfig, run_output
from tests.unit.teaching.test_step_probes import BATCH, DEMO, FIXED, RIGHT

ON = StepConfig(probes=True)


class TwoRules:
    def propose(self, evidence_json, round_kind, feedback):
        if round_kind != "initial":
            return [], {}, F(0)
        return (
            [
                {"rule": RIGHT, "summary": "right", "text": ""},
                {"rule": FIXED, "summary": "fixed", "text": ""},
            ],
            {},
            F(0),
        )


class Later:
    def ask(self, req):
        return None


def session(tmp_path):
    store = LocalStore(tmp_path)
    log = SessionLog(store, "s1")
    log.create(owner="o")
    for sid, sc, role in (("d", DEMO, "demo"), ("b", BATCH, "batch")):
        log.append(
            "SceneRegistered",
            "system",
            {
                "scene_id": sid,
                "scene_hash": codec.digest(sc),
                "scene": codec.loads(codec.dumps(sc)),
                "role": role,
            },
        )
    log.append(
        "DemonstrationRecorded",
        "human",
        {"scene_id": "d", "output": codec.loads(codec.dumps(run_output(RIGHT, DEMO)))},
    )
    return store, log


def run(store, log, renderer):
    return Executor(
        store,
        log,
        TwoRules(),
        Later(),
        Ledger(store, F(0)),
        ON,
        worst_usd=F(0),
        probe_renderer=renderer,
    ).run()


def accept(probe):
    return ProbeResult(True, f"probe:{probe.probe_id}", probe.scene)


def types(log):
    return [e.type for e in log.events()]


def test_accepted_probe_becomes_a_question(tmp_path):
    store, log = session(tmp_path)
    assert run(store, log, accept) == "waiting"
    evs = log.events()
    probe_scene = next(
        e for e in evs if e.type == "SceneRegistered" and e.payload["role"] == "probe"
    )
    q = next(e for e in evs if e.type == "RequestIssued")
    assert (
        q.payload["request"]["type"] == "ChooseOutput"
        and q.payload["request"]["scene_id"] == probe_scene.payload["scene_id"]
    )


def test_mismatched_probe_is_recorded_and_never_asked_about(tmp_path):
    store, log = session(tmp_path)
    seen = []

    def mismatch(probe):
        seen.append(probe.probe_id)
        return ProbeResult(False, reason="measured geometry differs by 3.0")

    run(store, log, mismatch)
    evs = log.events()
    failed = [e.payload for e in evs if e.type == "ProbeRendered"]
    assert failed and all(not f["ok"] for f in failed) and "differs" in failed[0]["reason"]
    assert not any(e.type == "SceneRegistered" and e.payload["role"] == "probe" for e in evs)
    assert len(set(seen)) == len(seen)  # each probe tried once


def test_a_raising_renderer_is_recorded_not_crashed_on(tmp_path):
    store, log = session(tmp_path)

    def boom(probe):
        raise RuntimeError("engine down")

    run(store, log, boom)
    assert any(
        e.type == "ProbeRendered" and "engine down" in e.payload["reason"] for e in log.events()
    )


def test_crash_after_issuing_a_probe_is_recovered(tmp_path):
    store, log = session(tmp_path)
    calls = {"n": 0}

    def crash_once(probe):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SystemExit("process died mid-render")
        return accept(probe)

    try:
        run(store, log, crash_once)
    except SystemExit:
        pass
    assert run(store, log, crash_once) == "waiting"
    assert any(e.type == "ProbeRendered" and e.payload["ok"] for e in log.events())
