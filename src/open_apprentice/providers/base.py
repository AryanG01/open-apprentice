"""Provider interface (spec 14.4-14.6). Application code depends on this, never on raw HTTP dicts.

complete_json: reserve budget -> call -> reconcile -> strict-validate (extra fields forbidden).
At most ONE charged schema-correction call; anything still invalid is a model-format failure.
Truncation, refusal, wrong model identity, auth, rate-limit and timeout are distinct outcomes.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from open_apprentice.budget import BudgetExhausted, Ledger


class ProviderError(Exception):
    code = "PROVIDER_ERROR"
    retryable = False


class ProviderAuthError(ProviderError):
    code = "PROVIDER_AUTH_ERROR"


class ProviderRateLimit(ProviderError):
    code = "PROVIDER_RATE_LIMIT"
    retryable = True


class ProviderTimeout(ProviderError):
    code = "INFRA_TIMEOUT"
    retryable = True


class ModelFormatError(ProviderError):
    code = "MODEL_FORMAT_ERROR"


class TruncatedOutput(ProviderError):
    code = "MODEL_TRUNCATED"


class ProviderRefusal(ProviderError):
    code = "MODEL_REFUSAL"


class WrongModelIdentity(ProviderError):
    code = "WRONG_MODEL_IDENTITY"


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class CallContext:
    role: str  # prompt role, e.g. "hypotheses", "binding", "repair"
    category: str = "inference"  # budget category (teaching, repair, ...)
    run_id: Optional[str] = None


@dataclass
class RawCompletion:
    text: str
    model_id: str
    request_id: Optional[str]
    finish_reason: str  # "stop" | "length" | "content_filter" | ...
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    latency_ms: float
    retries: int = 0
    usd: Optional[float] = None  # None => unknown, never silently zero


@dataclass
class ValidatedCompletion:
    parsed: Any
    provider_label: str  # MOCK | REPLAY | LIVE -- shown in UI/CLI
    model_id: str
    request_id: Optional[str]
    finish_reason: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    usage_estimated: bool
    usd: Optional[float]
    latency_ms: float
    retries: int
    schema_corrections: int
    raw_hash: str


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 3)  # deliberately conservative; used only for reservations


class Provider(ABC):
    label: str = "UNSET"
    requested_model: str = ""
    completion_floor: int = (
        0  # reasoning models spend hidden tokens: every call gets AT LEAST this many completion tokens
    )

    async def aclose(self) -> None:
        """Release network resources. Providers with none (the mock) inherit this no-op."""
        return None

    @abstractmethod
    async def _call(
        self, messages: list[Message], *, max_tokens: int, ctx: CallContext
    ) -> RawCompletion: ...

    async def complete_json(
        self,
        *,
        messages: list[Message],
        output_schema: type[BaseModel],
        ctx: CallContext,
        ledger: Ledger,
        max_tokens: int = 2048,
        usd_per_call_estimate: Optional[float] = None,
    ) -> ValidatedCompletion:
        max_tokens = max(max_tokens, self.completion_floor)
        msgs = list(messages)
        corrections = 0
        while True:
            prompt_est = estimate_tokens(json.dumps([m.__dict__ for m in msgs]))
            res = ledger.reserve(
                ctx.category if corrections == 0 else "schema_correction",
                tokens=prompt_est + max_tokens,
                calls=1,
                usd=usd_per_call_estimate,
            )
            try:
                raw = await self._call(msgs, max_tokens=max_tokens, ctx=ctx)
            except ProviderTimeout:
                ledger.mark_unresolved(res)  # may still have been processed
                raise
            except BaseException:
                ledger.release(res)  # request never produced a billable response we know of
                raise
            estimated = raw.prompt_tokens is None or raw.completion_tokens is None
            used = res.tokens if estimated else raw.prompt_tokens + raw.completion_tokens
            ledger.reconcile(res, tokens=used, usd=raw.usd)

            if self.requested_model and raw.model_id != self.requested_model:
                raise WrongModelIdentity(
                    f"requested {self.requested_model!r}, got {raw.model_id!r}"
                )
            if raw.finish_reason == "length":
                raise TruncatedOutput(
                    "output hit the completion limit; not executing partial output"
                )
            if raw.finish_reason == "content_filter":
                raise ProviderRefusal("provider refused or filtered the response")

            try:
                parsed = output_schema.model_validate_json(raw.text, strict=False)
            except (ValidationError, ValueError) as e:
                if corrections >= 1:
                    raise ModelFormatError(f"invalid after one correction: {str(e)[:300]}") from e
                corrections += 1
                msgs = msgs + [
                    Message("assistant", raw.text[:4000]),
                    Message(
                        "user",
                        "Your reply was not valid JSON for the required schema. "
                        f"Error: {str(e)[:300]}. Reply with ONLY the corrected JSON object.",
                    ),
                ]
                continue
            return ValidatedCompletion(
                parsed=parsed,
                provider_label=self.label,
                model_id=raw.model_id,
                request_id=raw.request_id,
                finish_reason=raw.finish_reason,
                prompt_tokens=raw.prompt_tokens,
                completion_tokens=raw.completion_tokens,
                usage_estimated=estimated,
                usd=raw.usd,
                latency_ms=raw.latency_ms,
                retries=raw.retries,
                schema_corrections=corrections,
                raw_hash=hashlib.sha256(raw.text.encode()).hexdigest(),
            )


class StrictModel(BaseModel):
    """Base for every model-output schema: unknown fields are errors (spec 14.5)."""

    model_config = {"extra": "forbid"}


__all__ = [
    "BudgetExhausted",
    "CallContext",
    "Message",
    "ModelFormatError",
    "Provider",
    "ProviderAuthError",
    "ProviderError",
    "ProviderRateLimit",
    "ProviderRefusal",
    "ProviderTimeout",
    "RawCompletion",
    "StrictModel",
    "TruncatedOutput",
    "ValidatedCompletion",
    "WrongModelIdentity",
    "estimate_tokens",
]
