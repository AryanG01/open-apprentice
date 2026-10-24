"""Vision calls: a message may carry content parts, and a base64 image never inflates the token reservation."""

import asyncio
import base64

from pydantic import BaseModel

from open_apprentice.budget import Ledger, Limits
from open_apprentice.providers.base import (
    CallContext,
    IMAGE_TOKENS_EST,
    Message,
    prompt_estimate,
)
from open_apprentice.providers.mock import MockProvider

BIG = "data:image/png;base64," + base64.b64encode(bytes(300_000)).decode()


class Out(BaseModel):
    ok: bool


def _vision_messages():
    return [
        Message("system", "read the banner"),
        Message(
            "user",
            [
                {"type": "text", "text": '{"hint": "x"}'},
                {"type": "image_url", "image_url": {"url": BIG}},
            ],
        ),
    ]


def test_an_image_part_costs_a_fixed_estimate_not_its_base64_length():
    est = prompt_estimate(_vision_messages())
    assert IMAGE_TOKENS_EST <= est < IMAGE_TOKENS_EST + 200
    assert est < len(BIG) // 3 // 10  # the old json.dumps estimate would have been ~130k


def test_plain_text_messages_are_estimated_as_before():
    assert prompt_estimate([Message("user", "x" * 300)]) >= 100


def test_a_vision_call_fits_a_small_budget_and_the_mock_sees_the_image_part():
    provider = MockProvider({"v": [{"ok": True}]})
    ledger = Ledger(Limits(tokens=40_000, calls=2))
    out = asyncio.run(
        provider.complete_json(
            messages=_vision_messages(),
            output_schema=Out,
            ctx=CallContext(role="v", category="inference"),
            ledger=ledger,
            max_tokens=1500,
        )
    )
    assert out.parsed.ok
    parts = provider.calls[0][1][-1].content
    assert isinstance(parts, list) and parts[1]["type"] == "image_url"


def test_the_vision_provider_is_a_separate_instance_with_its_own_model_and_rates():
    from open_apprentice.config import load_settings
    from open_apprentice.providers.factory import make_vision_provider

    base = {
        "PROVIDER_MODE": "nebius",
        "NEBIUS_API_KEY": "k",
        "LIVE_RUN_MAX_USD": "5",
        "NEBIUS_MODEL": "m-text",
    }
    assert (
        make_vision_provider(load_settings(env=base)) is None
    )  # no vision model configured: manual path only
    env = base | {
        "NEBIUS_VISION_MODEL": "nvidia/Nemotron-3.5-Super-VL",
        "VISION_INPUT_USD_PER_MILLION": "0.3",
        "VISION_OUTPUT_USD_PER_MILLION": "0.9",
    }
    p = make_vision_provider(load_settings(env=env))
    assert p.requested_model == "nvidia/Nemotron-3.5-Super-VL"
    assert p._rates == (0.3, 0.9) and p.completion_floor == 0
    assert (
        make_vision_provider(
            load_settings(env={"PROVIDER_MODE": "mock", "NEBIUS_VISION_MODEL": "x"})
        )
        is None
    )


def test_call_model_sends_the_image_as_a_content_part_after_the_json_text():
    import pathlib

    from open_apprentice.campaign.model import call_model
    from open_apprentice.providers.base import StrictModel

    class Reply(StrictModel):
        ok: bool

    provider = MockProvider({"v": [{"ok": True}]})
    prompt = pathlib.Path(__file__)  # any readable file: only its text is sent as the system turn
    res = asyncio.run(
        call_model(
            provider,
            Ledger(Limits(tokens=40_000, calls=2)),
            role="v",
            prompt=prompt,
            payload={"k": 1},
            schema=Reply,
            max_tokens=1500,
            image=BIG,
        )
    )
    assert res.parsed.ok
    user = provider.calls[0][1][-1].content
    assert user[0] == {"type": "text", "text": '{"k": 1}'}
    assert user[1] == {"type": "image_url", "image_url": {"url": BIG}}
    plain = MockProvider({"v": [{"ok": True}]})
    asyncio.run(
        call_model(
            plain,
            Ledger(Limits(tokens=40_000, calls=2)),
            role="v",
            prompt=prompt,
            payload={"k": 1},
            schema=Reply,
            max_tokens=1500,
        )
    )
    assert plain.calls[0][1][-1].content == '{"k": 1}'  # text-only callers are unchanged
