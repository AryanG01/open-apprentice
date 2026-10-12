"""Record one real provider session to a tape and replay it later at zero cost.

A replayed call returns the recorded model text only when the request (role + messages) is byte-identical to a recorded one.
Anything else is refused with ReplayMismatch; replay never improvises and is always labelled REPLAY.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import asdict
from typing import Any

from open_apprentice.providers.base import (
    CallContext,
    Message,
    Provider,
    ProviderError,
    RawCompletion,
)

TAPE_VERSION = 1


class ReplayMismatch(ProviderError):
    code = "REPLAY_MISMATCH"


def call_key(role: str, messages: list[Message]) -> str:
    payload = json.dumps([role, [[m.role, m.content] for m in messages]], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class RecordingProvider(Provider):
    """Wraps a real provider and appends every completed raw call to `path` (rewritten after each call, so a crash keeps what was paid for)."""

    def __init__(self, inner: Provider, path: pathlib.Path, meta: dict[str, Any]) -> None:
        self._inner = inner
        self._path = pathlib.Path(path)
        self._meta = meta
        self._entries: list[dict[str, Any]] = []
        self.label = inner.label
        self.requested_model = inner.requested_model
        self.completion_floor = inner.completion_floor

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def _call(
        self, messages: list[Message], *, max_tokens: int, ctx: CallContext
    ) -> RawCompletion:
        raw = await self._inner._call(messages, max_tokens=max_tokens, ctx=ctx)
        self._entries.append(
            {"role": ctx.role, "key": call_key(ctx.role, messages), "raw": asdict(raw)}
        )
        self._path.write_text(
            json.dumps({"version": TAPE_VERSION, **self._meta, "entries": self._entries}, indent=1)
        )
        return raw


class ReplayProvider(Provider):
    label = "REPLAY"

    def __init__(self, tape: dict[str, Any]) -> None:
        if tape.get("version") != TAPE_VERSION:
            raise ValueError("unsupported tape version")
        self.requested_model = tape["model"]
        self._pending: dict[str, list[dict[str, Any]]] = {}
        for e in tape["entries"]:
            self._pending.setdefault(e["key"], []).append(e["raw"])

    async def _call(
        self, messages: list[Message], *, max_tokens: int, ctx: CallContext
    ) -> RawCompletion:
        queue = self._pending.get(call_key(ctx.role, messages))
        if not queue:
            raise ReplayMismatch(
                "this request was not part of the recorded session; replay only covers the recorded path"
            )
        return RawCompletion(**{**queue.pop(0), "latency_ms": 0.0})


def load_tape(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(pathlib.Path(path).read_text())
