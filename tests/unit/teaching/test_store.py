import threading

import pytest

from open_apprentice.storage.store import LocalStore, PreconditionFailed


def test_create_is_atomic_and_never_overwrites(tmp_path):
    s = LocalStore(tmp_path)
    assert s.create("a/b.json", b"1") is True
    assert s.create("a/b.json", b"2") is False
    assert s.get("a/b.json").data == b"1"


def test_put_requires_matching_generation(tmp_path):
    s = LocalStore(tmp_path)
    g1 = s.put("m.json", b"v1", if_generation=None)
    with pytest.raises(PreconditionFailed):
        s.put("m.json", b"x", if_generation=None)
    g2 = s.put("m.json", b"v2", if_generation=g1)
    assert g2 > g1 and s.get("m.json").data == b"v2"
    with pytest.raises(PreconditionFailed):
        s.put("m.json", b"stale", if_generation=g1)


def test_concurrent_cas_exactly_one_winner(tmp_path):
    s = LocalStore(tmp_path)
    g = s.put("m.json", b"0", if_generation=None)
    wins: list[int] = []

    def worker(i: int) -> None:
        try:
            s.put("m.json", str(i).encode(), if_generation=g)
            wins.append(i)
        except PreconditionFailed:
            pass

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(wins) == 1


def test_missing_key_is_none(tmp_path):
    assert LocalStore(tmp_path).get("nope") is None
