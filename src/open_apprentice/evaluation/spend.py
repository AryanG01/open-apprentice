"""Spend control for paid experiment runs: one shared ledger file, written before the next call can start.

Rules (owner authorisation in results/redesign/budget.json):
  * spendable = min(authorized_total, funded) - reserve, across every run ever logged in spend.jsonl
  * before each call the worst case (prompt estimate + max completion tokens at the conservative $4/M) must fit
  * a call's cost is the provider's figure if present, else tokens at the CONFIGURED rates, else $4/M; a timed-out call is
    charged its worst case because the provider may have processed it
  * truncated or otherwise failed replies are billable and are recorded like any other
The guard raises BudgetExhausted rather than overshoot; callers record that as a stopped run, not a success.
"""

from __future__ import annotations

import json
import pathlib
import threading
import time
from typing import Optional

from open_apprentice.budget import BudgetExhausted
from open_apprentice.providers.base import (
    CallContext,
    Message,
    Provider,
    ProviderTimeout,
    RawCompletion,
    estimate_tokens,
)

ROOT = pathlib.Path("results/redesign")
CONSERVATIVE_USD_PER_MILLION = 4.0


def load_budget(root: pathlib.Path = ROOT) -> dict:
    return json.loads((root / "budget.json").read_text())


def spendable(budget: dict) -> float:
    return min(budget["authorized_total_usd"], budget["funded_usd"]) - budget["reserve_usd"]


def spent_so_far(root: pathlib.Path = ROOT) -> float:
    f = root / "spend.jsonl"
    if not f.exists():
        return 0.0
    return sum(json.loads(line)["usd"] for line in f.read_text().splitlines() if line.strip())


class SpendGuard(Provider):
    """Wraps a provider; every call is checked against the shared ledger first and logged right after."""

    def __init__(
        self,
        inner: Provider,
        *,
        run_id: str,
        run_cap_usd: float,
        root: pathlib.Path = ROOT,
        in_per_m: Optional[float] = None,
        out_per_m: Optional[float] = None,
    ) -> None:
        self._inner = inner
        self.label = inner.label
        self.requested_model = inner.requested_model
        self.completion_floor = inner.completion_floor
        self._run_id, self._cap, self._root = run_id, run_cap_usd, root
        self._rates = (in_per_m, out_per_m)
        self._lock = threading.Lock()
        self.run_usd = 0.0
        self.calls = 0
        self.stopped_reason = ""

    async def aclose(self) -> None:
        await self._inner.aclose()

    def _price(self, raw: RawCompletion) -> float:
        if raw.usd is not None:
            return raw.usd
        i, o = self._rates
        if None not in (i, o, raw.prompt_tokens, raw.completion_tokens):
            return raw.prompt_tokens * i / 1e6 + raw.completion_tokens * o / 1e6
        total = (raw.prompt_tokens or 0) + (raw.completion_tokens or 0)
        return total * CONSERVATIVE_USD_PER_MILLION / 1e6

    def _log(self, usd: float, kind: str, ctx: CallContext, tokens: int) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        row = {
            "t": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "run": self._run_id,
            "usd": round(usd, 6),
            "kind": kind,
            "role": ctx.role,
            "tokens": tokens,
        }
        with open(self._root / "spend.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
        self.run_usd += usd
        self.calls += 1

    async def _call(
        self, messages: list[Message], *, max_tokens: int, ctx: CallContext
    ) -> RawCompletion:
        worst_tokens = estimate_tokens(json.dumps([m.__dict__ for m in messages])) + max_tokens
        worst = worst_tokens * CONSERVATIVE_USD_PER_MILLION / 1e6
        with self._lock:
            budget = load_budget(self._root)
            total_after = spent_so_far(self._root) + worst
            if total_after > spendable(budget):
                self.stopped_reason = "shared budget"
                raise BudgetExhausted(
                    "usd", f"shared budget: worst case would reach ${total_after:.2f}"
                )
            if self.run_usd + worst > self._cap:
                self.stopped_reason = "run cap"
                raise BudgetExhausted("usd", f"run cap ${self._cap:.2f}")
        try:
            raw = await self._inner._call(messages, max_tokens=max_tokens, ctx=ctx)
        except ProviderTimeout:
            with self._lock:
                self._log(worst, "timeout_worst_case", ctx, worst_tokens)
            raise
        with self._lock:
            self._log(
                self._price(raw),
                raw.finish_reason,
                ctx,
                (raw.prompt_tokens or 0) + (raw.completion_tokens or 0),
            )
        return raw
