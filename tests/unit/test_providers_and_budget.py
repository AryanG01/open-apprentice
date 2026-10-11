import json

import httpx
import pytest

from open_apprentice.budget import BudgetExhausted, Ledger, Limits
from open_apprentice.providers.base import (
    CallContext,
    Message,
    ModelFormatError,
    ProviderAuthError,
    ProviderRateLimit,
    ProviderTimeout,
    StrictModel,
    TruncatedOutput,
    WrongModelIdentity,
)
from open_apprentice.providers.mock import MockProvider, MockScriptMissing
from open_apprentice.providers.nebius import NebiusProvider

CTX = CallContext(role="t")
MSGS = [Message("user", "hi")]
MODEL = "nvidia/nemotron-3-super-120b-a12b"


class Out(StrictModel):
    answer: int


def ledger(**kw):
    return Ledger(Limits(**{"tokens": 100_000, "calls": 20, **kw}))


def reply(content, *, finish="stop", model=MODEL, usage=True, status=200):
    body = {
        "id": "req-1",
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 10, "completion_tokens": 5}
    return httpx.Response(status, json=body)


def nebius(handler, **kw):
    async def nosleep(_):
        pass

    return NebiusProvider(
        base_url="https://x/v1/",
        api_key="sk-test-9f3a",
        model=MODEL,
        transport=httpx.MockTransport(handler),
        sleep=nosleep,
        **kw,
    )


async def run(p, led=None):
    return await p.complete_json(messages=MSGS, output_schema=Out, ctx=CTX, ledger=led or ledger())


# ---------- mock ----------
async def test_mock_is_labelled_and_deterministic():
    p = MockProvider({"t": [{"answer": 1}]})
    out = await run(p)
    assert out.parsed.answer == 1 and out.provider_label == "MOCK"


async def test_mock_never_improvises():
    with pytest.raises(MockScriptMissing):
        await run(MockProvider({}))


# ---------- structured output ----------
async def test_extra_fields_forbidden_then_one_charged_correction():
    p = MockProvider({"t": [{"answer": 1, "extra": 2}, {"answer": 3}]})
    led = ledger()
    out = await run(p, led)
    assert out.parsed.answer == 3 and out.schema_corrections == 1
    assert (
        led.consumed_calls == 2 and "schema_correction" in led.by_category
    )  # correction is charged


async def test_invalid_twice_is_model_format_error_not_executed():
    p = MockProvider({"t": ["not json", "{still bad"]})
    with pytest.raises(ModelFormatError):
        await run(p)


# ---------- live adapter against a fake server ----------
async def test_nebius_happy_path_and_cost_known_with_rates():
    p = nebius(
        lambda r: reply('{"answer": 7}'), input_usd_per_million=1.0, output_usd_per_million=2.0
    )
    out = await run(p)
    assert out.parsed.answer == 7 and out.provider_label == "LIVE" and out.request_id == "req-1"
    assert out.usd == pytest.approx(10 * 1e-6 + 5 * 2e-6)


async def test_cost_unknown_not_zero_without_rates_or_usage():
    led = ledger()
    out = await run(nebius(lambda r: reply('{"answer": 1}')), led)
    assert out.usd is None and led.unknown_cost_calls == 1
    led2 = ledger()
    out2 = await run(
        nebius(
            lambda r: reply('{"answer": 1}', usage=False),
            input_usd_per_million=1,
            output_usd_per_million=1,
        ),
        led2,
    )
    assert out2.usage_estimated and out2.usd is None


async def test_429_honours_retry_after_then_succeeds_and_counts_retries():
    calls = []

    def h(req):
        calls.append(1)
        return (
            httpx.Response(429, headers={"retry-after": "1"})
            if len(calls) < 3
            else reply('{"answer": 1}')
        )

    out = await run(nebius(h))
    assert out.retries == 2 and len(calls) == 3


async def test_429_exhausts_to_rate_limit_error():
    with pytest.raises(ProviderRateLimit):
        await run(
            nebius(
                lambda r: httpx.Response(429),
            ),
            ledger(),
        )


async def test_auth_failure_not_retried():
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(401, text="secret-config-echo")

    with pytest.raises(ProviderAuthError) as e:
        await run(nebius(h))
    assert len(calls) == 1 and "secret-config-echo" not in str(e.value)


async def test_read_timeout_leaves_reservation_unresolved_and_is_not_retried():
    calls = []

    def h(req):
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    led = ledger()
    with pytest.raises(ProviderTimeout):
        await run(nebius(h), led)
    assert len(calls) == 1 and led.snapshot()["unresolved_reservations"] == 1


async def test_truncation_is_distinct_and_partial_json_not_used():
    with pytest.raises(TruncatedOutput):
        await run(nebius(lambda r: reply('{"answer": 1', finish="length")))


async def test_wrong_model_identity_stops_instead_of_switching():
    with pytest.raises(WrongModelIdentity):
        await run(nebius(lambda r: reply('{"answer": 1}', model="some/other-model")))


async def test_request_body_carries_no_secret_and_uses_json_mode():
    seen = {}

    def h(req):
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers["authorization"]
        return reply('{"answer": 1}')

    await run(nebius(h))
    assert (
        seen["body"]["response_format"] == {"type": "json_object"}
        and seen["body"]["model"] == MODEL
    )
    assert "sk-test-9f3a" not in json.dumps(seen["body"]) and "sk-test-9f3a" in seen["auth"]


# ---------- budget ----------
async def test_budget_refuses_before_calling():
    p = MockProvider({"t": [{"answer": 1}]})
    with pytest.raises(BudgetExhausted):
        await run(p, Ledger(Limits(tokens=10, calls=5)))
    assert p.calls == []


def test_usd_ceiling_requires_a_cost_estimate():
    led = Ledger(Limits(usd=1.0))
    with pytest.raises(BudgetExhausted, match="no cost estimate"):
        led.reserve("x", tokens=1)


def test_reservation_lifecycle_and_release():
    led = Ledger(Limits(tokens=100, calls=2))
    r = led.reserve("x", tokens=60)
    with pytest.raises(BudgetExhausted):
        led.reserve("x", tokens=60)  # held capacity counts
    led.release(r)
    led.reserve("x", tokens=60)  # freed
    r2 = led.reserve("y", tokens=10)
    led.reconcile(r2, tokens=5, usd=None)
    with pytest.raises(ValueError):
        led.reconcile(r2, tokens=5, usd=None)


async def test_reasoning_effort_is_sent_only_when_configured():
    seen = []

    def h(req):
        seen.append(json.loads(req.content))
        return reply('{"answer": 1}')

    await run(nebius(h))
    assert "reasoning_effort" not in seen[0]
    p = NebiusProvider(
        base_url="https://x/v1/",
        api_key="k",
        model=MODEL,
        reasoning_effort="low",
        transport=httpx.MockTransport(h),
    )
    await run(p)
    assert seen[1]["reasoning_effort"] == "low"


async def test_completion_floor_raises_small_caps_and_never_lowers_large_ones():
    seen = []

    def h(req):
        seen.append(json.loads(req.content)["max_tokens"])
        return reply('{"answer": 1}')

    p = NebiusProvider(
        base_url="https://x/v1/",
        api_key="k",
        model=MODEL,
        completion_floor=32000,
        transport=httpx.MockTransport(h),
    )
    await p.complete_json(
        messages=MSGS, output_schema=Out, ctx=CTX, ledger=ledger(tokens=500_000), max_tokens=3000
    )
    await p.complete_json(
        messages=MSGS, output_schema=Out, ctx=CTX, ledger=ledger(tokens=500_000), max_tokens=50000
    )
    assert seen == [32000, 50000]
