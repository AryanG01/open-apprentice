"""Nebius Token Factory adapter (OpenAI-compatible chat completions), spec 14.

STATUS: written from the spec's documented facts; NOT verified against the live endpoint (no
credential yet). Anything marked `probe` below is an assumption that `oa provider probe --live`
must confirm and record in docs/capabilities.json before it is relied on.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Awaitable, Callable, Optional

import httpx

from open_apprentice.providers.base import (
    CallContext,
    Message,
    Provider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimit,
    ProviderTimeout,
    RawCompletion,
)


class NebiusProvider(Provider):
    label = "LIVE"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        input_usd_per_million: Optional[float] = None,
        output_usd_per_million: Optional[float] = None,
        json_mode: bool = True,  # probe: json_object support is unconfirmed
        limit_field: str = "max_tokens",  # probe: may be max_completion_tokens
        reasoning_effort: Optional[
            str
        ] = None,  # documented request field; None => provider default
        completion_floor: int = 0,
        connect_timeout: float = 10.0,
        read_timeout: float = 300.0,
        max_retries: int = 3,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not api_key:
            raise ProviderAuthError("NEBIUS_API_KEY is not set")
        self.requested_model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._rates = (input_usd_per_million, output_usd_per_million)
        self._json_mode = json_mode
        self._limit_field = limit_field
        self._effort = reasoning_effort
        self.completion_floor = completion_floor
        self._max_retries = max_retries
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(read_timeout, connect=connect_timeout), transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _cost(self, p: Optional[int], c: Optional[int]) -> Optional[float]:
        i, o = self._rates
        if None in (i, o, p, c):
            return None  # unknown, never zero (spec 14.7)
        return p * i / 1e6 + c * o / 1e6

    async def _call(
        self, messages: list[Message], *, max_tokens: int, ctx: CallContext
    ) -> RawCompletion:
        body: dict = {
            "model": self.requested_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            self._limit_field: max_tokens,
            "temperature": 0,
        }
        if self._json_mode:
            body["response_format"] = {"type": "json_object"}
        if self._effort:
            body["reasoning_effort"] = self._effort
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

        retries = 0
        start = time.perf_counter()
        while True:
            try:
                r = await self._client.post(self._url, json=body, headers=headers)
            except httpx.ReadTimeout as e:
                # Possibly processed server-side: do NOT auto-retry (could double-charge).
                raise ProviderTimeout("read timeout; cost unknown until reconciled") from e
            except httpx.TransportError as e:
                if retries >= self._max_retries:
                    raise ProviderError(f"transport failure: {type(e).__name__}") from e
                await self._backoff(retries, None)
                retries += 1
                continue

            if r.status_code in (401, 403):
                raise ProviderAuthError(f"HTTP {r.status_code}")  # never retried
            if r.status_code == 429 or r.status_code >= 500:
                if retries >= self._max_retries:
                    if r.status_code == 429:
                        raise ProviderRateLimit("rate limited after retries")
                    raise ProviderError(f"HTTP {r.status_code} after retries")
                await self._backoff(retries, r.headers.get("retry-after"))
                retries += 1
                continue
            if r.status_code >= 400:
                # Redact provider body: it may echo configuration (spec 16.4).
                raise ProviderError(f"HTTP {r.status_code} (body redacted)")
            break

        data = r.json()
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
            finish = choice.get("finish_reason") or "unknown"
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise ProviderError("unexpected response shape") from e
        usage = data.get("usage") or {}
        p, c = usage.get("prompt_tokens"), usage.get("completion_tokens")
        return RawCompletion(
            text=text,
            model_id=data.get("model", ""),
            request_id=data.get("id") or r.headers.get("x-request-id"),
            finish_reason=finish,
            prompt_tokens=p,
            completion_tokens=c,
            latency_ms=(time.perf_counter() - start) * 1000,
            retries=retries,
            usd=self._cost(p, c),
        )

    async def _backoff(self, attempt: int, retry_after: Optional[str]) -> None:
        if retry_after:
            try:
                await self._sleep(min(float(retry_after), 60.0))
                return
            except ValueError:
                pass
        await self._sleep(min(0.5 * 2**attempt, 30.0) * (0.5 + random.random() / 2))
