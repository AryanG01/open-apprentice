"""Owned JSON records in the Store. A record of another owner is indistinguishable from a missing one."""

from __future__ import annotations

import hashlib
import json
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
    """First call stores and returns produce()'s result; a repeat with the same request returns it again; a repeat with a
    different request is refused."""
    k = f"idem/{owner}/{hashlib.sha256(key.encode()).hexdigest()}.json"
    b = store.get(k)
    if b is not None:
        d = json.loads(b.data)
        if d["digest"] != request_digest:
            raise IdempotencyConflict("this idempotency key was used with a different request")
        return d["result"]
    result = produce()
    if not store.create(k, dumps({"digest": request_digest, "result": result})):
        return idempotent(
            store, owner, key, request_digest, produce
        )  # lost a race: the stored one wins
    return result
