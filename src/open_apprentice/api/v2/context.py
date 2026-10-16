"""Everything /api/v2 needs, in one object: the Store, the renderer, the proposers, the durable ledger and the dispatcher.
Unit tests build it with a fake renderer; the app builds it from the environment with make_v2()."""

from __future__ import annotations

import logging
import os
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Optional, Protocol

from open_apprentice.drawio.parse import Page
from open_apprentice.drawio.render import Rendered, render_page
from open_apprentice.storage.factory import store_from_env
from open_apprentice.storage.store import Store
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.correction_executor import ScopeProposer
from open_apprentice.teaching.executor import Proposer

log = logging.getLogger(__name__)


class Dispatcher(Protocol):
    def submit(self, key: str, fn: Callable[[], None]) -> None: ...


@dataclass
class V2:
    store: Store
    render: Callable[[Page], Rendered]
    proposer: Proposer
    scope_proposer: ScopeProposer
    model: str  # provenance: "Fixture" | "Live" | "Recorded"
    live_available: Callable[[], bool]
    ledger: Ledger
    worst_usd: Fraction  # reserved per model attempt; 0 for the offline enumerator
    dispatcher: Dispatcher
    secret: bytes


class LocalDispatcher:
    """At most one job per key runs at a time. A submit while that key is running asks for exactly one more run afterwards
    (submits coalesce), so session progress never runs two executors on one log at once."""

    def __init__(self, workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="oa-v2")
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._running: set[str] = set()
        self._again: dict[str, Callable[[], None]] = {}
        self.errors: dict[str, str] = {}

    def submit(self, key: str, fn: Callable[[], None]) -> None:
        with self._lock:
            if key in self._running:
                self._again[key] = fn
                return
            self._running.add(key)
        self._pool.submit(self._run, key, fn)

    def _run(self, key: str, fn: Callable[[], None]) -> None:
        while True:
            try:
                fn()
            except (
                Exception
            ) as e:  # recorded, never lost silently; the job itself records user-facing failures
                log.exception("v2 job %s failed", key)
                self.errors[key] = f"{type(e).__name__}: {e}"
            with self._lock:
                nxt = self._again.pop(key, None)
                if nxt is None:
                    self._running.discard(key)
                    self._idle.notify_all()
                    return
            fn = nxt

    def drain(self, timeout: float = 30.0) -> None:
        with self._lock:
            if not self._idle.wait_for(lambda: not self._running, timeout=timeout):
                raise TimeoutError(f"dispatcher still busy: {sorted(self._running)}")

    def close(self) -> None:
        self._pool.shutdown(wait=True)


def _secret() -> bytes:
    s = os.environ.get("SESSION_SECRET")
    if s:
        return s.encode()
    log.warning(
        "SESSION_SECRET is not set: owner cookies are signed with a per-process key and reset on restart"
    )
    return secrets.token_bytes(32)


def make_v2(engine_url: Optional[str]) -> V2:
    """Offline (enumerator, provenance Fixture) unless DEMO_MODEL_ENABLED=1 and a provider is configured. Clients cannot
    switch this; the live global cap is the durable ledger (DEMO_MODEL_MAX_USD, default 1.5)."""
    from open_apprentice.concepts.label_enumerative import LabelEnumerator

    store = store_from_env()

    def render(page: Page) -> Rendered:
        if engine_url is None:
            from open_apprentice.drawio.parse import DrawioRefused

            raise DrawioRefused("the renderer is not running on this server")
        return render_page(page, engine_url)

    offline = LabelEnumerator()
    proposer: Proposer = offline
    scope: ScopeProposer = offline
    model, worst, cap = "Fixture", Fraction(0), Fraction(0)
    if os.environ.get("DEMO_MODEL_ENABLED") == "1":
        try:
            from open_apprentice.config import load_settings
            from open_apprentice.providers.factory import make_provider
            from open_apprentice.providers.teaching_adapter import (
                ProviderProposer,
                ProviderScopeProposer,
            )

            provider = make_provider(load_settings())
            proposer, scope = ProviderProposer(provider), ProviderScopeProposer(provider)
            model, worst = "Live", Fraction(1, 5)
            cap = Fraction(os.environ.get("DEMO_MODEL_MAX_USD", "1.5"))
        except Exception as e:  # misconfigured live mode stays offline, visibly
            log.warning("live mode unavailable, staying offline: %s", e)
    ledger = Ledger(store, cap)
    return V2(
        store=store,
        render=render,
        proposer=proposer,
        scope_proposer=scope,
        model=model,
        live_available=lambda: model == "Live" and ledger.exposure()["total"] + worst <= cap,
        ledger=ledger,
        worst_usd=worst,
        dispatcher=LocalDispatcher(),
        secret=_secret(),
    )
