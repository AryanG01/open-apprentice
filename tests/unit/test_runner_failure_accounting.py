"""A provider failure inside a run must produce rows (with the tokens already spent), never vanish."""

import asyncio
from unittest.mock import MagicMock

from open_apprentice.agent.policies import Policy
from open_apprentice.evaluation.episodes import make_manifest
from open_apprentice.evaluation.runner import run_episode
from open_apprentice.providers.base import TruncatedOutput


class Boom(Policy):
    name = "boom"

    async def learn(self, ctx, handle, demo):
        ctx.ledger.reserve("x", tokens=10)
        raise TruncatedOutput("cap")

    async def solve(self, ctx, view):
        raise TruncatedOutput("cap")


def test_provider_errors_become_failed_rows_not_lost_runs():
    ep = make_manifest("development", 0, 12).episodes[1]
    harness = MagicMock()
    rows = asyncio.run(
        run_episode(ep, Boom(), harness, MagicMock(), MagicMock(), provider=MagicMock())
    )
    assert (
        len(rows) == 9
        and rows[0].stage == "learning"
        and rows[0].failure == "provider_error:MODEL_TRUNCATED"
    )
    assert all(
        r.failure == "provider_error:MODEL_TRUNCATED" and not r.committed and r.correct is None
        for r in rows[1:]
    )
