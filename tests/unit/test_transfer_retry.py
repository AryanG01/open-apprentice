"""A reasoning model that runs out of tokens thinking gets ONE retry, and the retry must differ from the first request:
at temperature 0 an identical request would most likely truncate again and be billed twice."""

import json

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.transfer import _propose
from open_apprentice.providers.base import CallContext, Message, RawCompletion
from open_apprentice.providers.mock import MockProvider

ONE_CANDIDATE = {"candidates": [{"diagnosis": "d", "program": [{"op": "return", "value": 0}]}]}


class TruncatesFirst(MockProvider):
    def __init__(self, reply):
        super().__init__({"binding": [reply, reply]})
        self.requests: list[list[Message]] = []

    async def _call(self, messages, *, max_tokens, ctx: CallContext) -> RawCompletion:
        self.requests.append(list(messages))
        raw = await super()._call(messages, max_tokens=max_tokens, ctx=ctx)
        if len(self.requests) == 1:
            raw.finish_reason = "length"  # cut off mid-thought
        return raw


async def test_the_retry_after_truncation_is_a_different_request():
    provider = TruncatesFirst(ONE_CANDIDATE)
    cands, _ = await _propose(provider, Ledger(Limits(tokens=10**6, calls=10)), "binding", {"x": 1})
    assert len(provider.requests) == 2 and len(cands) == 1
    first, second = provider.requests
    assert json.dumps([m.__dict__ for m in first]) != json.dumps([m.__dict__ for m in second])
    assert "brief" in second[-1].content.lower()  # it asks the model to cut its reasoning short
