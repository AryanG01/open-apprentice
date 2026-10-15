import pytest

from open_apprentice.skills.versions import ActivationRejected, SkillStore
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.events import SessionLog


def art(rule="r1"):
    return {
        "skill_id": "k",
        "program": {"rule": [rule]},
        "evidence": [],
        "superseded": {},
        "retention_report": {},
    }


def test_store_is_immutable_and_versions_increase(tmp_path):
    s = SkillStore(LocalStore(tmp_path))
    assert s.store_version("k", art("a")) == 1
    assert s.store_version("k", art("b")) == 2
    assert s.store_version("k", art("a")) == 1  # same content: idempotent
    assert s.version("k", 1)["program"]["rule"] == ["a"] and s.version("k", 1)["artifact_hash"]


def test_activate_and_rollback_keep_a_committed_history(tmp_path):
    s = SkillStore(LocalStore(tmp_path))
    s.store_version("k", art("a"))
    s.store_version("k", art("b"))
    s.activate("k", 1, None, "op1", "s1")
    s.activate("k", 2, s.active("k")[2], "op2", "s2")
    s.activate("k", 1, s.active("k")[2], "op3", "s3")  # rollback
    assert [(h["from_version"], h["to_version"]) for h in s.history("k")] == [
        (None, 1),
        (1, 2),
        (2, 1),
    ]
    assert s.active("k")[0] == 1


def test_activation_compares_generation_not_version(tmp_path):
    s = SkillStore(LocalStore(tmp_path))
    s.store_version("k", art("a"))
    s.store_version("k", art("b"))
    s.activate("k", 1, None, "op1", "s1")
    g_start = s.active("k")[2]  # a correction starts here, at version 1
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
    s.store_version("k", art("a"))
    s.store_version("k", art("b"))
    s.activate("k", 1, None, "op1", "s1")
    rid = s.active("k")[1]
    logs["s1"].append(
        "VersionActivated",
        "system",
        {"operation_id": "op1", "from": None, "to": 1, "record_id": rid},
    )
    s.activate("k", 2, s.active("k")[2], "op2", "s2")  # crash before logging
    s.activate("k", 1, s.active("k")[2], "op3", "s3")  # rollback, crash before logging
    pointer_before = s.active("k")
    assert s.reconcile("k", logs) == 2
    assert s.reconcile("k", logs) == 0  # idempotent
    assert s.active("k") == pointer_before
    assert [e.payload["to"] for e in logs["s2"].events() if e.type == "VersionActivated"] == [2]
    assert [e.payload["to"] for e in logs["s3"].events() if e.type == "VersionActivated"] == [1]
