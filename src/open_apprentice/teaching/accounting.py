"""Durable exposure ledger. exposure = settled + outstanding reservations + conservative exposure of dispatched or
uncertain attempts; every attempt is in exactly one state. Exactly-once provider execution is NOT claimed."""

from __future__ import annotations

from fractions import Fraction
from typing import Callable, Optional

from open_apprentice.storage.store import PreconditionFailed, Store
from open_apprentice.teaching import codec

KEY = "ledger/manifest.json"


class OverBudget(Exception):
    pass


class Ledger:
    def __init__(self, store: Store, cap_usd: Fraction) -> None:
        self.store, self.cap = store, Fraction(cap_usd)

    def _update(self, fn: Callable[[dict], None]) -> dict:
        for _ in range(50):
            b = self.store.get(KEY)
            doc = codec.loads(b.data) if b else {"attempts": {}}
            fn(doc)
            try:
                self.store.put(KEY, codec.dumps(doc), if_generation=b.generation if b else None)
                return doc
            except PreconditionFailed:
                continue
        raise RuntimeError("ledger contention")

    @staticmethod
    def _sum(doc: dict) -> dict[str, Fraction]:
        out = {"settled": Fraction(0), "reserved": Fraction(0), "uncertain": Fraction(0)}
        for a in doc["attempts"].values():
            st = a["state"]
            if st == "completed":
                out["settled"] += codec.frac(a["actual"])
            elif st == "reserved":
                out["reserved"] += codec.frac(a["worst"])
            elif st in ("dispatched", "outcome_unknown"):
                out["uncertain"] += codec.frac(a["worst"])
        out["total"] = out["settled"] + out["reserved"] + out["uncertain"]
        return out

    def reserve(self, attempt_id: str, action_id: str, worst_usd: Fraction) -> None:
        def fn(doc: dict) -> None:
            if attempt_id in doc["attempts"]:
                return
            if self._sum(doc)["total"] + Fraction(worst_usd) > self.cap:
                raise OverBudget(f"reserving {worst_usd} would exceed cap {self.cap}")
            doc["attempts"][attempt_id] = {
                "action_id": action_id,
                "worst": Fraction(worst_usd),
                "state": "reserved",
            }

        self._update(fn)

    def _transition(
        self, attempt_id: str, allowed: tuple[str, ...], new: str, actual: Optional[Fraction] = None
    ) -> None:
        def fn(doc: dict) -> None:
            a = doc["attempts"][attempt_id]
            if a["state"] == new:
                return
            if a["state"] not in allowed:
                raise ValueError(f"{attempt_id}: {a['state']} -> {new} not allowed")
            a["state"] = new
            if actual is not None:
                a["actual"] = Fraction(actual)

        self._update(fn)

    def record(self, attempt_id: str, action_id: str, actual_usd: Fraction) -> None:
        """Spend that already happened elsewhere (the demo lanes' own metering): counted even past the cap, never refused."""

        def fn(doc: dict) -> None:
            doc["attempts"].setdefault(
                attempt_id,
                {
                    "action_id": action_id,
                    "worst": Fraction(actual_usd),
                    "actual": Fraction(actual_usd),
                    "state": "completed",
                },
            )

        self._update(fn)

    def dispatched(self, attempt_id: str) -> None:
        self._transition(attempt_id, ("reserved",), "dispatched")

    def settle(self, attempt_id: str, actual_usd: Fraction) -> None:
        self._transition(attempt_id, ("dispatched", "outcome_unknown"), "completed", actual_usd)

    def fail_before_dispatch(self, attempt_id: str) -> None:
        self._transition(attempt_id, ("reserved",), "released")

    def mark_unknown(self, attempt_id: str) -> None:
        self._transition(attempt_id, ("dispatched",), "outcome_unknown")

    def exposure(self, action_ids: Optional[set[str]] = None) -> dict[str, Fraction]:
        """Global exposure, or only the attempts made for the given actions (one session's spend)."""
        b = self.store.get(KEY)
        doc = codec.loads(b.data) if b else {"attempts": {}}
        if action_ids is not None:
            doc = {
                "attempts": {
                    k: a for k, a in doc["attempts"].items() if a["action_id"] in action_ids
                }
            }
        return self._sum(doc)

    def state(self, attempt_id: str) -> Optional[str]:
        b = self.store.get(KEY)
        if b is None:
            return None
        return codec.loads(b.data)["attempts"].get(attempt_id, {}).get("state")
