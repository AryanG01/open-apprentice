"""One counted retry when a binding call is truncated (reasoning runaway); a second truncation is reported, not hidden."""

import asyncio

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.transfer import _propose
from open_apprentice.providers.base import TruncatedOutput


class _Prov:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    async def complete_json(self, **kw):
        self.calls += 1
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


class _Done:
    class parsed:
        candidates = []

        @staticmethod
        def model_dump_json():
            return "{}"


def test_one_truncation_is_retried_two_are_raised():
    p = _Prov([TruncatedOutput("x"), _Done])
    asyncio.run(_propose(p, Ledger(Limits(tokens=10**6, calls=10)), "binding", {}))
    assert p.calls == 2
    p = _Prov([TruncatedOutput("x"), TruncatedOutput("y")])
    with pytest.raises(TruncatedOutput):
        asyncio.run(_propose(p, Ledger(Limits(tokens=10**6, calls=10)), "binding", {}))
    assert p.calls == 2
