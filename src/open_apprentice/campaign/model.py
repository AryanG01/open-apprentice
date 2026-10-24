"""One Nemotron call for the campaign lane (plan 9E). Every caller has a deterministic baseline, so this never raises:
a failure comes back as a plain reason the UI can show next to the fallback it used."""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from open_apprentice.budget import BudgetExhausted, Ledger
from open_apprentice.providers.base import (
    CallContext,
    Message,
    Provider,
    ProviderError,
    StrictModel,
    TruncatedOutput,
)

# same wording as the badge lane's binding calls (concepts/transfer.py): a retry must differ from the cut-off request
RETRY_NUDGE = "Your previous answer was cut off before it finished. Keep your reasoning brief this time and reply with ONLY the JSON object."


@dataclass
class ModelResult:
    parsed: Any | None
    error: str | None
    tokens: int


async def call_model(
    provider: Provider,
    ledger: Ledger,
    *,
    role: str,
    prompt: pathlib.Path,
    payload: dict,
    schema: type[StrictModel],
    max_tokens: int,
    image: (
        str | None
    ) = None,  # a data URL: the user turn becomes [json text, image] content parts (vision models)
) -> ModelResult:
    text = json.dumps(payload)
    user = (
        text
        if image is None
        else [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": image}}]
    )
    msgs = [Message("system", prompt.read_text()), Message("user", user)]
    tokens = 0
    for attempt in (0, 1):
        try:
            comp = await provider.complete_json(
                messages=msgs,
                output_schema=schema,
                ctx=CallContext(role=role, category="inference"),
                ledger=ledger,
                max_tokens=max_tokens,
            )
            tokens += comp.prompt_tokens + comp.completion_tokens
            return ModelResult(comp.parsed, None, tokens)
        except TruncatedOutput:
            if attempt:
                return ModelResult(None, "Nemotron's reply was cut off twice", tokens)
            msgs = msgs + [Message("user", RETRY_NUDGE)]
        except BudgetExhausted:
            return ModelResult(None, "the model budget for this session is used up", tokens)
        except (ProviderError, ValidationError, ValueError) as e:
            return ModelResult(
                None, f"Nemotron's reply could not be used ({type(e).__name__})", tokens
            )
    return ModelResult(None, "no reply", tokens)
