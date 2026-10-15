"""Immutable skill versions and their activation history. A version object is written once; the active pointer moves only
by compare-and-set and always references an immutable activation record (operation, originating session, from/to,
predecessor), so history can be rebuilt from the pointer even if a session crashed before logging. Spec 3.1."""

from __future__ import annotations

import uuid
from typing import Optional

from open_apprentice.storage.store import PreconditionFailed, Store
from open_apprentice.teaching import codec
from open_apprentice.teaching.events import SessionLog


class ActivationRejected(Exception):
    """The active pointer is not at the generation the caller started from."""


class SkillStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    def _latest(self, skill_id: str) -> int:
        n = 0
        while self.store.get(f"skills/{skill_id}/v{n + 1}.json") is not None:
            n += 1
        return n

    def store_version(self, skill_id: str, artifact: dict) -> int:
        body = {k: v for k, v in artifact.items() if k not in ("version", "artifact_hash")}
        body["skill_id"] = skill_id
        h = codec.digest(body)
        for n in range(1, self._latest(skill_id) + 1):
            if self.version(skill_id, n)["artifact_hash"] == h:
                return n  # same content already stored: idempotent
        while True:
            n = self._latest(skill_id) + 1
            doc = dict(body, version=n, artifact_hash=h)
            if self.store.create(f"skills/{skill_id}/v{n}.json", codec.dumps(doc)):
                return n

    def version(self, skill_id: str, n: int) -> dict:
        b = self.store.get(f"skills/{skill_id}/v{n}.json")
        if b is None:
            raise KeyError(f"{skill_id} v{n} not stored")
        return codec.loads(b.data)

    def active(self, skill_id: str) -> tuple[Optional[int], Optional[str], Optional[int]]:
        b = self.store.get(f"skills/{skill_id}/active.json")
        if b is None:
            return None, None, None
        d = codec.loads(b.data)
        return d["version"], d["record_id"], b.generation

    def activate(
        self,
        skill_id: str,
        version: int,
        expected_generation: Optional[int],
        operation_id: str,
        session_id: str,
    ) -> str:
        self.version(skill_id, version)  # must exist
        b = self.store.get(f"skills/{skill_id}/active.json")
        cur = codec.loads(b.data) if b else None
        if (b.generation if b else None) != expected_generation:
            raise ActivationRejected(
                f"pointer at generation {b.generation if b else None}, expected {expected_generation}"
            )
        record_id = uuid.uuid4().hex
        record = {
            "record_id": record_id,
            "operation_id": operation_id,
            "session_id": session_id,
            "from_version": cur["version"] if cur else None,
            "to_version": version,
            "prev_record_id": cur["record_id"] if cur else None,
        }
        self.store.create(f"skills/{skill_id}/activations/{record_id}.json", codec.dumps(record))
        try:
            self.store.put(
                f"skills/{skill_id}/active.json",
                codec.dumps({"version": version, "record_id": record_id}),
                if_generation=expected_generation,
            )
        except PreconditionFailed as e:
            raise ActivationRejected(str(e)) from e  # the record stays unreachable
        return record_id

    def history(self, skill_id: str) -> list[dict]:
        _, rid, _ = self.active(skill_id)
        out = []
        while rid is not None:
            b = self.store.get(f"skills/{skill_id}/activations/{rid}.json")
            if b is None:
                raise RuntimeError(f"committed activation record {rid} missing")
            r = codec.loads(b.data)
            out.append(r)
            rid = r["prev_record_id"]
        return list(reversed(out))

    def reconcile(self, skill_id: str, logs: dict[str, SessionLog]) -> int:
        """Append any committed activation missing from its originating session's log. Never moves the pointer."""
        added = 0
        for r in self.history(skill_id):
            log = logs.get(r["session_id"])
            if log is None:
                continue
            seen = {
                e.payload.get("operation_id") for e in log.events() if e.type == "VersionActivated"
            }
            if r["operation_id"] in seen:
                continue
            log.append(
                "VersionActivated",
                "system",
                {
                    "operation_id": r["operation_id"],
                    "from": r["from_version"],
                    "to": r["to_version"],
                    "record_id": r["record_id"],
                    "reconciled": True,
                },
            )
            added += 1
        return added
