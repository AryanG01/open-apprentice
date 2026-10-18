from fractions import Fraction

import pytest

from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching import codec
from open_apprentice.teaching.events import Conflict, SessionLog


def test_codec_round_trips_fractions_canonically():
    obj = {"b": Fraction(3, 2), "a": [Fraction(4), 1]}
    assert codec.dumps(obj) == b'{"a":[4,1],"b":"3/2"}'
    assert codec.frac(codec.loads(codec.dumps(obj))["b"]) == Fraction(3, 2)
    assert codec.digest(obj) == codec.digest({"a": [4, 1], "b": "3/2"})


def test_append_and_replay_in_order(tmp_path):
    log = SessionLog(LocalStore(tmp_path), "s1")
    log.create(owner="o1")
    log.append("SceneRegistered", "system", {"scene_id": "a"})
    log.append("DemonstrationRecorded", "human", {"scene_id": "a"})
    evs = log.events()
    assert [e.type for e in evs] == ["SceneRegistered", "DemonstrationRecorded"]
    assert [e.seq for e in evs] == [1, 2] and evs[1].prev_event_id == evs[0].event_id
    m, _ = log.manifest()
    assert (
        m["intent_revision"] == 2 and m["manifest_revision"] == 2
    )  # both are intent-bearing types


def test_stale_expected_revision_conflicts(tmp_path):
    log = SessionLog(LocalStore(tmp_path), "s1")
    log.create(owner="o1")
    log.append("SceneRegistered", "system", {"scene_id": "a"})
    with pytest.raises(Conflict):
        log.append("SceneRegistered", "system", {"scene_id": "b"}, expected_revision=0)


def test_orphan_event_is_invisible_and_append_continues(tmp_path):
    store = LocalStore(tmp_path)
    log = SessionLog(store, "s1")
    log.create(owner="o1")
    log.append("SceneRegistered", "system", {"scene_id": "a"})
    # simulate a crash: an event object written but the manifest never updated
    orphan = {
        "event_id": "orphan",
        "prev_event_id": None,
        "seq": 2,
        "type": "X",
        "origin": "system",
        "payload": {},
        "caused_by": None,
    }
    store.create("sessions/s1/events/orphan.json", codec.dumps(orphan))
    assert [e.type for e in log.events()] == ["SceneRegistered"]
    log.append("DemonstrationRecorded", "human", {"scene_id": "a"})
    assert [e.type for e in log.events()] == ["SceneRegistered", "DemonstrationRecorded"]


def test_concurrent_writers_cannot_expose_conflicting_histories(tmp_path):
    store = LocalStore(tmp_path)
    SessionLog(store, "s1").create(owner="o1")
    a, b = SessionLog(store, "s1"), SessionLog(store, "s1")
    rev = a.manifest()[0]["manifest_revision"]
    a.append("SceneRegistered", "system", {"scene_id": "a"}, expected_revision=rev)
    with pytest.raises(Conflict):
        b.append("SceneRegistered", "system", {"scene_id": "b"}, expected_revision=rev)
    assert [e.payload["scene_id"] for e in a.events()] == ["a"]


def test_repeat_reads_fetch_only_new_events(tmp_path):
    store = LocalStore(tmp_path)
    log = SessionLog(store, "s1")
    log.create(owner="o1")
    for i in range(5):
        log.append("SceneRegistered", "system", {"scene_id": str(i)})
    first = log.events()
    reads = []
    real = store.get
    store.get = lambda k: (reads.append(k), real(k))[1]  # type: ignore[method-assign]
    assert log.events() == first
    assert [k for k in reads if "/events/" in k] == []
    log.append("SceneRegistered", "system", {"scene_id": "x"})
    reads.clear()
    assert [e.seq for e in log.events()] == [1, 2, 3, 4, 5, 6]
    assert len([k for k in reads if "/events/" in k]) == 1


def test_event_cache_returns_independent_lists(tmp_path):
    log = SessionLog(LocalStore(tmp_path), "s1")
    log.create(owner="o1")
    log.append("SceneRegistered", "system", {"scene_id": "a"})
    log.events().clear()
    assert len(log.events()) == 1
