"""Owned JSON records in the Store. A record of another owner is indistinguishable from a missing one."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Callable

from open_apprentice.storage.store import PreconditionFailed, Store


class NotFound(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


def dumps(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()


def put_new(store: Store, key: str, owner: str, body: dict) -> None:
    if not store.create(key, dumps({**body, "owner": owner})):
        raise FileExistsError(key)


def load(store: Store, key: str, owner: str) -> tuple[dict, int]:
    b = store.get(key)
    if b is None:
        raise NotFound(key)
    d = json.loads(b.data)
    if d.get("owner") != owner:
        raise NotFound(key)
    return d, b.generation


def update(store: Store, key: str, owner: str, fn: Callable[[dict], dict]) -> dict:
    for _ in range(50):
        d, gen = load(store, key, owner)
        new = {**fn(d), "owner": owner}
        try:
            store.put(key, dumps(new), if_generation=gen)
            return new
        except PreconditionFailed:
            continue
    raise RuntimeError(f"{key}: update contention")


def idempotent(
    store: Store, owner: str, key: str, request_digest: str, produce: Callable[[], dict]
) -> dict:
    """First call runs produce() and stores its result; repeats with the same request return it (waiting while the first is
    still running); a repeat with a different request is refused. A produce() that raises is not cached.
    """
    k = f"idem/{owner}/{hashlib.sha256(key.encode()).hexdigest()}.json"
    for _ in range(600):  # up to ~60 s waiting for an in-flight first request
        b = store.get(k)
        if b is None:
            if not store.create(k, dumps({"digest": request_digest, "state": "pending"})):
                continue
            gen = store.get(k).generation  # type: ignore[union-attr]
            return _produce(store, k, request_digest, gen, produce)
        d = json.loads(b.data)
        if d["digest"] != request_digest:
            raise IdempotencyConflict("this idempotency key was used with a different request")
        state = d.get("state", "done")
        if state == "done":
            return d["result"]
        if state == "failed":
            try:
                store.put(
                    k,
                    dumps({"digest": request_digest, "state": "pending"}),
                    if_generation=b.generation,
                )
            except PreconditionFailed:
                continue
            return _produce(store, k, request_digest, store.get(k).generation, produce)  # type: ignore[union-attr]
        time.sleep(0.1)  # pending: the first request is still running
    raise IdempotencyConflict(
        "a request with this idempotency key is still in progress; retry shortly"
    )


def _produce(store: Store, k: str, digest: str, gen: int, produce: Callable[[], dict]) -> dict:
    try:
        result = produce()
    except BaseException:
        store.put(k, dumps({"digest": digest, "state": "failed"}), if_generation=gen)
        raise
    store.put(k, dumps({"digest": digest, "state": "done", "result": result}), if_generation=gen)
    return result
