import asyncio
import dataclasses
import pathlib

from open_apprentice.budget import BudgetExhausted, Ledger, Limits
from open_apprentice.campaign.model import call_model
from open_apprentice.providers.base import StrictModel
from open_apprentice.providers.mock import MockProvider

PROMPT = pathlib.Path(__file__)  # any readable file stands in for a prompt


class Out(StrictModel):
    answer: str


def _call(provider, ledger=None):
    return asyncio.run(
        call_model(
            provider,
            ledger or Ledger(Limits(tokens=100_000, calls=8)),
            role="r",
            prompt=PROMPT,
            payload={"q": 1},
            schema=Out,
            max_tokens=500,
        )
    )


def test_a_valid_reply_is_parsed():
    res = _call(MockProvider({"r": [{"answer": "yes"}]}))
    assert res.parsed.answer == "yes" and res.error is None and res.tokens > 0


class _TruncatedOnce(MockProvider):
    async def _call(self, messages, *, max_tokens, ctx):
        raw = await super()._call(messages, max_tokens=max_tokens, ctx=ctx)
        return dataclasses.replace(raw, finish_reason="length") if len(self.calls) == 1 else raw


def test_a_truncated_reply_is_retried_once():
    p = _TruncatedOnce({"r": [{"answer": "cut"}, {"answer": "whole"}]})
    res = _call(p)
    assert res.parsed.answer == "whole" and len(p.calls) == 2


class _Broke(MockProvider):
    async def _call(self, messages, *, max_tokens, ctx):
        raise BudgetExhausted("usd", "cap reached")


def test_budget_exhaustion_is_a_plain_error_not_an_exception():
    res = _call(_Broke({}))
    assert res.parsed is None and "budget" in res.error


def test_a_reply_that_does_not_match_the_schema_is_a_plain_error():
    res = _call(MockProvider({"r": [{"wrong": 1}, {"wrong": 2}]}))
    assert res.parsed is None and res.error
