import pytest

from open_apprentice.api.v2 import identity, records
from open_apprentice.storage.store import LocalStore

SECRET = b"s" * 32


def test_cookie_round_trip_and_tamper():
    tok = identity.sign("abc", SECRET)
    assert identity.verify(tok, SECRET) == "abc"
    assert identity.verify(tok[:-1] + ("A" if tok[-1] != "A" else "B"), SECRET) is None
    assert identity.verify(tok, b"t" * 32) is None
    assert identity.verify(None, SECRET) is None and identity.verify("garbage", SECRET) is None


def test_records_hide_other_owners(tmp_path):
    s = LocalStore(tmp_path)
    records.put_new(s, "documents/d1.json", "alice", {"name": "a"})
    assert records.load(s, "documents/d1.json", "alice")[0]["name"] == "a"
    with pytest.raises(records.NotFound):
        records.load(s, "documents/d1.json", "bob")
    with pytest.raises(records.NotFound):
        records.load(s, "documents/missing.json", "alice")
    with pytest.raises(FileExistsError):
        records.put_new(s, "documents/d1.json", "alice", {})


def test_update_is_compare_and_set(tmp_path):
    s = LocalStore(tmp_path)
    records.put_new(s, "runs/r.json", "o", {"n": 0})
    out = records.update(s, "runs/r.json", "o", lambda d: {**d, "n": d["n"] + 1})
    assert out["n"] == 1 and records.load(s, "runs/r.json", "o")[0]["n"] == 1


def test_idempotency_replays_and_refuses_a_different_body(tmp_path):
    s = LocalStore(tmp_path)
    calls = []

    def produce():
        calls.append(1)
        return {"id": "x"}

    assert records.idempotent(s, "o", "k1", "d1", produce) == {"id": "x"}
    assert records.idempotent(s, "o", "k1", "d1", produce) == {"id": "x"} and len(calls) == 1
    with pytest.raises(records.IdempotencyConflict):
        records.idempotent(s, "o", "k1", "d2", produce)
    assert records.idempotent(s, "other", "k1", "d2", produce) == {"id": "x"} and len(calls) == 2
