"""Append-only session event log. An event is an immutable object written first; it becomes part of history only when
the session manifest's head pointer is moved to it by compare-and-set. Replay walks head -> prev, never lists objects."""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Optional

from open_apprentice.storage.store import PreconditionFailed, Store
from open_apprentice.teaching import codec

INTENT_TYPES = frozenset(
    {
        "SceneRegistered",
        "MappingRecorded",
        "DemonstrationRecorded",
        "ResponseRecorded",
        "ScopeAuthorized",
        "VersionActivated",
    }
)


class Conflict(Exception):
    """The manifest moved since the caller read it; re-read events, re-step, retry."""


@dataclass(frozen=True)
class Event:
    event_id: str
    prev_event_id: Optional[str]
    seq: int
    type: str
    origin: str
    payload: dict
    caused_by: Optional[str] = None


_CHAINS: OrderedDict[str, list[Event]] = OrderedDict()  # head event id (a uuid) -> its whole chain
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 256


class SessionLog:
    def __init__(self, store: Store, sid: str) -> None:
        self.store, self.sid = store, sid
        self._mkey = f"sessions/{sid}/manifest.json"

    def create(self, owner: str) -> dict:
        m = {
            "sid": self.sid,
            "owner": owner,
            "manifest_revision": 0,
            "intent_revision": 0,
            "head_event_id": None,
            "head_seq": 0,
            "status": "open",
        }
        self.store.put(self._mkey, codec.dumps(m), if_generation=None)
        return m

    def manifest(self) -> tuple[dict, int]:
        b = self.store.get(self._mkey)
        if b is None:
            raise KeyError(f"no session {self.sid}")
        return codec.loads(b.data), b.generation

    def append(
        self,
        type: str,
        origin: str,
        payload: dict,
        caused_by: Optional[str] = None,
        expected_revision: Optional[int] = None,
    ) -> Event:
        for _ in range(20):
            try:
                return self._append_once(type, origin, payload, caused_by, expected_revision)
            except Conflict:
                if expected_revision is not None:
                    raise
        raise Conflict("too many concurrent writers")

    def _append_once(
        self,
        type: str,
        origin: str,
        payload: dict,
        caused_by: Optional[str],
        expected_revision: Optional[int],
    ) -> Event:
        b = self.store.get(self._mkey)
        if b is None:
            raise KeyError(f"no session {self.sid}")
        m = codec.loads(b.data)
        if expected_revision is not None and m["manifest_revision"] != expected_revision:
            raise Conflict(
                f"manifest at {m['manifest_revision']}, caller expected {expected_revision}"
            )
        ev = Event(
            uuid.uuid4().hex,
            m["head_event_id"],
            m["head_seq"] + 1,
            type,
            origin,
            payload,
            caused_by,
        )
        if not self.store.create(
            f"sessions/{self.sid}/events/{ev.event_id}.json", codec.dumps(asdict(ev))
        ):
            raise RuntimeError("event id collision")
        m2 = dict(
            m,
            head_event_id=ev.event_id,
            head_seq=ev.seq,
            manifest_revision=m["manifest_revision"] + 1,
            intent_revision=m["intent_revision"] + (1 if type in INTENT_TYPES else 0),
        )
        try:
            self.store.put(self._mkey, codec.dumps(m2), if_generation=b.generation)
        except PreconditionFailed as e:
            raise Conflict(str(e)) from e  # the written event stays unreachable
        return ev

    def events(self) -> list[Event]:
        """Events are create-only and the head only moves forward, so a chain read once never changes: walk back from the
        head only until a head already seen, and reuse the rest."""
        m, _ = self.manifest()
        out: list[Event] = []
        eid = m["head_event_id"]
        base: list[Event] = []
        while eid is not None:
            with _CACHE_LOCK:
                hit = _CHAINS.get(eid)
                if hit is not None:
                    _CHAINS.move_to_end(eid)
            if hit is not None:
                base = hit
                break
            b = self.store.get(f"sessions/{self.sid}/events/{eid}.json")
            if b is None:
                raise RuntimeError(f"committed event {eid} missing")
            d = codec.loads(b.data)
            out.append(Event(**d))
            eid = d["prev_event_id"]
        chain = base + list(reversed(out))
        if m["head_event_id"] is not None:
            with _CACHE_LOCK:
                _CHAINS[m["head_event_id"]] = chain
                while len(_CHAINS) > _CACHE_MAX:
                    _CHAINS.popitem(last=False)
        return list(chain)
