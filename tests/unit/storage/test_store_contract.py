import threading

import pytest
from google.api_core.exceptions import NotFound
from google.api_core.exceptions import PreconditionFailed as GcsPrecondition

from open_apprentice.storage.gcs import GcsStore
from open_apprentice.storage.store import LocalStore, PreconditionFailed


class FakeBlob:
    """Mirrors the google-cloud-storage Blob subset GcsStore uses, enforcing generation preconditions like GCS."""

    def __init__(self, bucket, name):
        self.bucket, self.name, self.generation = bucket, name, None

    def download_as_bytes(self):
        with self.bucket.lock:
            if self.name not in self.bucket.data:
                raise NotFound(self.name)
            data, gen = self.bucket.data[self.name]
            self.generation = gen
            return data

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
