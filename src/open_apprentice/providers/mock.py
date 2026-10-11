"""Deterministic MOCK provider (spec 14, D8). Scripted per prompt role; never invents answers.

A role with no remaining scripted reply raises MockScriptMissing instead of improvising, so an
offline test can never silently pass on made-up model behaviour. Token counts are simulated.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Optional, Sequence

from open_apprentice.providers.base import (
    CallContext,
    Message,
    Provider,
    RawCompletion,
    estimate_tokens,
)


class MockScriptMissing(Exception):
    pass


class MockProvider(Provider):
    label = "MOCK"

    def __init__(
        self,
        script: Mapping[str, Sequence[Any]],
        model: str = "mock-model",
        functions: Optional[Mapping[str, Callable[[list[Message]], Any]]] = None,
    ) -> None:
        # reply may be a str (sent verbatim) or any JSON-serialisable object. `functions[role](messages)` is called for
        # every request of that role when the role's queue is empty (still deterministic, still scripted by the test).
        self._queues = {k: list(v) for k, v in script.items()}
        self._fns = dict(functions or {})
        self.requested_model = model
        self.calls: list[tuple[str, list[Message]]] = []

    async def _call(
        self, messages: list[Message], *, max_tokens: int, ctx: CallContext
    ) -> RawCompletion:
        self.calls.append((ctx.role, list(messages)))
        q = self._queues.get(ctx.role)
        if q:
            reply = q.pop(0)
        elif ctx.role in self._fns:
            reply = self._fns[ctx.role](messages)
        else:
            raise MockScriptMissing(f"no scripted reply left for role {ctx.role!r}")
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return RawCompletion(
            text=text,
            model_id=self.requested_model,
            request_id=f"mock-{len(self.calls)}",
            finish_reason="stop",
            prompt_tokens=estimate_tokens(json.dumps([m.__dict__ for m in messages])),
            completion_tokens=estimate_tokens(text),
            latency_ms=0.0,
            usd=0.0,
        )
