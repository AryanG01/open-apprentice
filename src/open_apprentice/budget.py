"""Shared budget ledger (spec 19, 14.7).

Every activity (inference, retries, schema corrections, probes, solver, replay, discarded branches)
reserves here first, then reconciles. Costs are never silently zero: an unknown cost is its own
state. A timed-out external call stays reserved until reconciled (spec 14.6).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional


class BudgetExhausted(Exception):
    """Raised before work starts when a ceiling would be crossed. Distinct from infra failure."""

    def __init__(self, dimension: str, detail: str = "") -> None:
        self.dimension = dimension
        super().__init__(f"BUDGET_EXHAUSTED[{dimension}] {detail}".strip())


@dataclass(frozen=True)
class Limits:
    tokens: Optional[int] = None
    calls: Optional[int] = None
    actions: Optional[int] = None
    usd: Optional[float] = None


@dataclass
class Reservation:
    id: str
    category: str
    tokens: int
    calls: int
    usd: Optional[float]
    state: str = "open"  # open | reconciled | released | unresolved


@dataclass
class Ledger:
    limits: Limits
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _res: dict[str, Reservation] = field(default_factory=dict, repr=False)
    consumed_tokens: int = 0
    consumed_calls: int = 0
    consumed_actions: int = 0
    consumed_usd: float = 0.0
    unknown_cost_calls: int = 0
    by_category: dict[str, dict[str, float]] = field(default_factory=dict)

    def _held(self) -> tuple[int, int, float]:
        open_ = [r for r in self._res.values() if r.state in ("open", "unresolved")]
        return (
            sum(r.tokens for r in open_),
            sum(r.calls for r in open_),
            sum(r.usd or 0.0 for r in open_),
        )

    def reserve(
        self, category: str, *, tokens: int = 0, calls: int = 1, usd: Optional[float] = None
    ) -> Reservation:
        """Hold capacity before an expensive call. Raises BudgetExhausted rather than overshoot."""
        with self._lock:
            ht, hc, hu = self._held()
            lim = self.limits
            if lim.tokens is not None and self.consumed_tokens + ht + tokens > lim.tokens:
                raise BudgetExhausted(
                    "tokens", f"{self.consumed_tokens}+{ht}+{tokens}>{lim.tokens}"
                )
            if lim.calls is not None and self.consumed_calls + hc + calls > lim.calls:
                raise BudgetExhausted("calls", f"limit {lim.calls}")
            if lim.usd is not None:
                if usd is None:
                    raise BudgetExhausted(
                        "usd", "a dollar ceiling is set but this call has no cost estimate"
                    )
                if self.consumed_usd + hu + usd > lim.usd:
                    raise BudgetExhausted("usd", f"limit {lim.usd}")
            r = Reservation(uuid.uuid4().hex, category, tokens, calls, usd)
            self._res[r.id] = r
            return r

    def reconcile(self, r: Reservation, *, tokens: int, usd: Optional[float]) -> None:
        """Replace the reservation with actual usage. usd=None records an unknown cost, not zero."""
        with self._lock:
            if r.state not in ("open", "unresolved"):
                raise ValueError(f"reservation already {r.state}")
            r.state = "reconciled"
            self.consumed_tokens += tokens
            self.consumed_calls += r.calls
            c = self.by_category.setdefault(
                r.category, {"tokens": 0, "calls": 0, "usd": 0.0, "unknown_cost_calls": 0}
            )
            c["tokens"] += tokens
            c["calls"] += r.calls
            if usd is None:
                self.unknown_cost_calls += r.calls
                c["unknown_cost_calls"] += r.calls
            else:
                self.consumed_usd += usd
                c["usd"] += usd

    def release(self, r: Reservation) -> None:
        """Give back an unused reservation (call never sent)."""
        with self._lock:
            if r.state == "open":
                r.state = "released"

    def mark_unresolved(self, r: Reservation) -> None:
        """Timed-out request may still have been processed: stays held until reconciled."""
        with self._lock:
            if r.state == "open":
                r.state = "unresolved"

    def charge_actions(self, category: str, n: int = 1) -> None:
        with self._lock:
            if self.limits.actions is not None and self.consumed_actions + n > self.limits.actions:
                raise BudgetExhausted("actions", f"limit {self.limits.actions}")
            self.consumed_actions += n
            c = self.by_category.setdefault(
                category, {"tokens": 0, "calls": 0, "usd": 0.0, "unknown_cost_calls": 0}
            )
            c["actions"] = c.get("actions", 0) + n

    def snapshot(self) -> dict:
        with self._lock:
            ht, hc, hu = self._held()
            return {
                "consumed": {
                    "tokens": self.consumed_tokens,
                    "calls": self.consumed_calls,
                    "actions": self.consumed_actions,
                    "usd": self.consumed_usd,
                },
                "held": {"tokens": ht, "calls": hc, "usd": hu},
                "unknown_cost_calls": self.unknown_cost_calls,
                "unresolved_reservations": sum(
                    1 for r in self._res.values() if r.state == "unresolved"
                ),
                "by_category": {k: dict(v) for k, v in self.by_category.items()},
            }
