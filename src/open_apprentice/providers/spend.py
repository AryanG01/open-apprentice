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

import asyncio
import contextlib
import fcntl
import json
import pathlib
import time
from typing import Callable, Iterator, Optional

from open_apprentice.budget import BudgetExhausted
from open_apprentice.providers.base import (
    CallContext,
    Message,
    Provider,
    ProviderTimeout,
    RawCompletion,
    prompt_estimate,
)

ROOT = pathlib.Path("results/redesign")
CONSERVATIVE_USD_PER_MILLION = 4.0
CALL_DEADLINE_S = 420.0  # wall-clock ceiling per model call


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
        merge_system: bool = False,
        run_total_cap_usd: Optional[float] = None,
    ) -> None:
        self._merge_system = merge_system
        self._run_total_cap = run_total_cap_usd  # the run id's cap across every guard and process
        self._inner = inner
        self.label = inner.label
        self.requested_model = inner.requested_model
        self.completion_floor = inner.completion_floor
        self._run_id, self._cap, self._root = run_id, run_cap_usd, root
        self._rates = (in_per_m, out_per_m)
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

    @contextlib.contextmanager
    def _ledger(self) -> Iterator[None]:
        """Cross-process exclusion for check-and-reserve, so parallel learner processes see each other's outstanding
        reservations (spec 3.7: exposure = settled + outstanding reservations)."""
        self._root.mkdir(parents=True, exist_ok=True)
        with open(self._root / "spend.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _append(self, usd: float, kind: str, role: str, tokens: int) -> None:
        row = {
            "t": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "run": self._run_id,
            "usd": round(usd, 6),
            "kind": kind,
            "role": role,
            "tokens": tokens,
        }
        with open(self._root / "spend.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()

    def _release(self, worst: float) -> None:
        with self._ledger():
            self._append(-worst, "release", "_", 0)

    def _log(self, usd: float, kind: str, ctx: CallContext, tokens: int) -> None:
        with self._ledger():
            self._append(usd, kind, ctx.role, tokens)
        self.run_usd += usd
        self.calls += 1

    async def _call(
        self, messages: list[Message], *, max_tokens: int, ctx: CallContext
    ) -> RawCompletion:
        worst_tokens = prompt_estimate(messages) + max_tokens
        worst = worst_tokens * CONSERVATIVE_USD_PER_MILLION / 1e6
        with self._ledger():
            budget = load_budget(self._root)
            total_after = spent_so_far(self._root) + worst
            if total_after > spendable(budget):
                self.stopped_reason = "shared budget"
                raise BudgetExhausted(
                    "usd", f"shared budget: worst case would reach ${total_after:.2f}"
                )
            if self._run_total_cap is not None:
                run_after = spent_for_run(self._run_id, self._root) + worst
                if run_after > self._run_total_cap:
                    self.stopped_reason = "run cap"
                    raise BudgetExhausted("usd", f"run cap ${self._run_total_cap:.2f}")
            elif self.run_usd + worst > self._cap:
                self.stopped_reason = "run cap"
                raise BudgetExhausted("usd", f"run cap ${self._cap:.2f}")
            self._append(worst, "reserve", "_", 0)
        if self._merge_system and messages and messages[0].role == "system":
            # observed 2026-10-14: the endpoint sometimes ignores the system turn and answers the evidence JSON as if it
            # were the task. Instructions travel in the user turn instead.
            body = messages[1].content
            if isinstance(
                body, list
            ):  # vision: the instructions become the first text part, the image stays a part
                first = Message(
                    "user",
                    [{"type": "text", "text": f"{messages[0].content}\n\n=== INPUT ==="}, *body],
                )
            else:
                first = Message("user", f"{messages[0].content}\n\n=== INPUT ===\n{body}")
            messages = [first, *messages[2:]]
        try:
            # httpx's read timeout is per read, not per call: a trickling or stalled connection can wait far longer
            raw = await asyncio.wait_for(
                self._inner._call(messages, max_tokens=max_tokens, ctx=ctx), CALL_DEADLINE_S
            )
        except (ProviderTimeout, asyncio.TimeoutError) as e:
            if isinstance(e, asyncio.TimeoutError):
                e = ProviderTimeout(
                    f"no reply within {CALL_DEADLINE_S:.0f}s; cost unknown until reconciled"
                )
            self._log(worst, "timeout_worst_case", ctx, worst_tokens)
            self._release(worst)  # the worst-case charge replaces the reservation
            raise e
        except BaseException:
            self._release(worst)  # no billable reply we know of
            raise
        self._log(
            self._price(raw),
            raw.finish_reason,
            ctx,
            (raw.prompt_tokens or 0) + (raw.completion_tokens or 0),
        )
        self._release(worst)
        return raw


def spent_for_run(run_id: str, root: pathlib.Path = ROOT) -> float:
    f = root / "spend.jsonl"
    if not f.exists():
        return 0.0
    rows = (json.loads(x) for x in f.read_text().splitlines() if x.strip())
    return sum(r["usd"] for r in rows if r.get("run") == run_id)


def guarded_factory(
    make_inner: Callable[[], Provider],
    *,
    run_id: str,
    cap_usd: float,
    root: pathlib.Path = ROOT,
    in_per_m: Optional[float] = None,
    out_per_m: Optional[float] = None,
) -> Callable[[], Provider]:
    """A provider factory for callers that build a fresh provider per call (the teaching adapters) or run in several
    processes: each guard's run cap is what this run id has not yet spent in the shared ledger."""

    def factory() -> Provider:
        left = cap_usd - spent_for_run(run_id, root)
        return SpendGuard(
            make_inner(),
            run_id=run_id,
            run_cap_usd=left,
            run_total_cap_usd=cap_usd,
            root=root,
            in_per_m=in_per_m,
            out_per_m=out_per_m,
            merge_system=True,  # observed 2026-10-14: the endpoint sometimes ignores the system turn
        )

    return factory
