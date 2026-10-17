"""SpendGuard: the shared ledger is written per call, the run cap and the shared budget stop calls BEFORE they are sent, a timeout
is charged its worst case, a truncated reply is billed, and unknown costs are charged conservatively."""

import json

import pytest

from open_apprentice.budget import BudgetExhausted
from open_apprentice.evaluation.spend import SpendGuard, spendable, spent_so_far
from open_apprentice.providers.base import (
    CallContext,
    Message,
    Provider,
    ProviderTimeout,
    RawCompletion,
)

CTX = CallContext(role="t")
MSGS = [Message("user", "x" * 300)]


class Fake(Provider):
    label = "FAKE"
    requested_model = "m"

    def __init__(self, **kw):
        self.kw, self.sent = kw, 0

    async def _call(self, messages, *, max_tokens, ctx):
        self.sent += 1
        if self.kw.get("timeout"):
            raise ProviderTimeout("t")
        return RawCompletion(
            "{}",
            "m",
            "r",
            self.kw.get("finish", "stop"),
            self.kw.get("p", 1000),
            self.kw.get("c", 1000),
            0.0,
            usd=self.kw.get("usd"),
        )


def root(tmp_path, total=50, funded=50, reserve=10):
    (tmp_path / "budget.json").write_text(
        json.dumps({"authorized_total_usd": total, "funded_usd": funded, "reserve_usd": reserve})
    )
    return tmp_path


async def test_every_call_is_logged_including_truncated_ones(tmp_path):
    g = SpendGuard(Fake(finish="length", usd=0.01), run_id="r", run_cap_usd=1, root=root(tmp_path))
    await g._call(MSGS, max_tokens=100, ctx=CTX)
    assert spent_so_far(tmp_path) == pytest.approx(0.01) and g.calls == 1
    assert [json.loads(x)["kind"] for x in (tmp_path / "spend.jsonl").read_text().splitlines()] == [
        "reserve",
        "length",
        "release",
    ]


async def test_unknown_cost_is_charged_at_the_conservative_rate(tmp_path):
    g = SpendGuard(
        Fake(usd=None, p=500_000, c=500_000), run_id="r", run_cap_usd=100, root=root(tmp_path)
    )
    await g._call(MSGS, max_tokens=100, ctx=CTX)
    assert spent_so_far(tmp_path) == pytest.approx(4.0)  # 1M tokens at $4/M, not zero


async def test_configured_rates_price_a_call_when_the_provider_gives_no_figure(tmp_path):
    g = SpendGuard(
        Fake(usd=None, p=1_000_000, c=1_000_000),
        run_id="r",
        run_cap_usd=100,
        root=root(tmp_path),
        in_per_m=1,
        out_per_m=3,
    )
    await g._call(MSGS, max_tokens=100, ctx=CTX)
    assert spent_so_far(tmp_path) == pytest.approx(4.0)


async def test_a_timeout_is_charged_its_worst_case(tmp_path):
    g = SpendGuard(Fake(timeout=True), run_id="r", run_cap_usd=5, root=root(tmp_path))
    with pytest.raises(ProviderTimeout):
        await g._call(MSGS, max_tokens=10_000, ctx=CTX)
    assert spent_so_far(tmp_path) > 0.04  # (100 + 10000 tokens) * $4/M


async def test_the_run_cap_stops_the_next_call_before_it_is_sent(tmp_path):
    inner = Fake(usd=0.02)
    g = SpendGuard(inner, run_id="r", run_cap_usd=0.05, root=root(tmp_path))
    with pytest.raises(
        BudgetExhausted
    ):  # worst case for 10k completion tokens is $0.04 + prompt: fits once at most
        for _ in range(5):
            await g._call(MSGS, max_tokens=10_000, ctx=CTX)
    assert inner.sent < 5 and g.stopped_reason == "run cap"


async def test_the_shared_budget_counts_other_runs_and_the_reserve(tmp_path):
    r = root(tmp_path, total=50, funded=12, reserve=10)  # spendable = 2
    assert spendable(json.loads((r / "budget.json").read_text())) == 2
    (r / "spend.jsonl").write_text(
        json.dumps({"usd": 1.99}) + "\n"
    )  # another run already spent most of it
    inner = Fake(usd=0.001)
    g = SpendGuard(inner, run_id="r2", run_cap_usd=100, root=r)
    with pytest.raises(BudgetExhausted):
        await g._call(MSGS, max_tokens=10_000, ctx=CTX)
    assert inner.sent == 0 and g.stopped_reason == "shared budget"


async def test_an_unfunded_account_blocks_every_live_call(tmp_path):
    g = SpendGuard(Fake(usd=0.0), run_id="r", run_cap_usd=100, root=root(tmp_path, funded=2.24))
    with pytest.raises(BudgetExhausted):
        await g._call(MSGS, max_tokens=100, ctx=CTX)


async def test_merge_system_moves_instructions_into_the_user_turn(tmp_path):
    from open_apprentice.evaluation.spend import SpendGuard
    from open_apprentice.providers.base import Message, RawCompletion
    from open_apprentice.providers.mock import MockProvider

    seen = []

    class Spy(MockProvider):
        async def _call(self, messages, *, max_tokens, ctx):
            seen.append(messages)
            return RawCompletion(
                text="{}",
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                usd=0.0,
                model_id="m",
                request_id="r",
                latency_ms=1,
            )

    (tmp_path / "budget.json").write_text(
        '{"authorized_total_usd": 50, "reserve_usd": 10, "funded_usd": 50}'
    )
    g = SpendGuard(Spy({}), run_id="t", run_cap_usd=1, root=tmp_path, merge_system=True)
    await g._call(
        [Message("system", "RULES"), Message("user", "DATA")],
        max_tokens=10,
        ctx=CTX,
    )
    assert (
        [m.role for m in seen[0]] == ["user"]
        and "RULES" in seen[0][0].content
        and "DATA" in seen[0][0].content
    )


async def test_a_stalled_call_hits_the_wall_clock_deadline_and_is_charged_worst_case(
    tmp_path, monkeypatch
):
    import asyncio

    import pytest

    from open_apprentice.evaluation import spend
    from open_apprentice.providers.base import Message, ProviderTimeout
    from open_apprentice.providers.mock import MockProvider

    class Stalled(MockProvider):
        async def _call(self, messages, *, max_tokens, ctx):
            await asyncio.sleep(30)

    (tmp_path / "budget.json").write_text(
        '{"authorized_total_usd": 50, "reserve_usd": 10, "funded_usd": 50}'
    )
    monkeypatch.setattr(spend, "CALL_DEADLINE_S", 0.05)
    g = spend.SpendGuard(Stalled({}), run_id="t", run_cap_usd=1, root=tmp_path)
    with pytest.raises(ProviderTimeout):
        await g._call([Message("user", "x")], max_tokens=10, ctx=CTX)
    assert "timeout_worst_case" in (tmp_path / "spend.jsonl").read_text()


async def test_a_run_cap_holds_across_fresh_guards_and_processes(tmp_path):
    from open_apprentice.providers.spend import guarded_factory, spent_for_run

    r = root(tmp_path)
    (r / "spend.jsonl").write_text(json.dumps({"run": "other", "usd": 5.0}) + "\n")
    factory = guarded_factory(lambda: Fake(usd=0.3), run_id="cal", cap_usd=0.5, root=r)
    await factory()._call(MSGS, max_tokens=10, ctx=CTX)  # 0.3 of the 0.5 spent
    assert spent_for_run("cal", r) == pytest.approx(0.3)
    with pytest.raises(BudgetExhausted):  # a new guard (another call or process) sees only 0.2 left
        await factory()._call(MSGS, max_tokens=100_000, ctx=CTX)


async def test_concurrent_guards_cannot_both_start_a_call_that_only_one_budget_fits(tmp_path):
    """Several learner processes near the cap: each guard must see the others' outstanding reservations."""
    import asyncio

    started = asyncio.Event()

    class Slow(Fake):
        async def _call(self, messages, *, max_tokens, ctx):
            started.set()
            await asyncio.sleep(0.3)  # still in flight while the other guard checks
            return await super()._call(messages, max_tokens=max_tokens, ctx=ctx)

    r = root(tmp_path, total=50, funded=50, reserve=10)
    (r / "budget.json").write_text(
        json.dumps({"authorized_total_usd": 50, "funded_usd": 50, "reserve_usd": 10})
    )
    (r / "spend.jsonl").write_text(json.dumps({"run": "o", "usd": 39.92}) + "\n")  # 0.08 spendable
    # one worst case: (300/3 + 10000) tokens at $4/M = $0.0404; two do not fit in $0.08
    guards = [SpendGuard(Slow(usd=0.001), run_id="r", run_cap_usd=1, root=r) for _ in range(2)]
    results = await asyncio.gather(
        *(g._call(MSGS, max_tokens=10_000, ctx=CTX) for g in guards), return_exceptions=True
    )
    ok = [x for x in results if not isinstance(x, BaseException)]
    refused = [x for x in results if isinstance(x, BudgetExhausted)]
    assert len(ok) == 1 and len(refused) == 1


async def test_a_settled_call_leaves_only_its_actual_cost_in_the_ledger(tmp_path):
    r = root(tmp_path)
    g = SpendGuard(Fake(usd=0.02), run_id="r", run_cap_usd=1, root=r)
    await g._call(MSGS, max_tokens=100, ctx=CTX)
    assert spent_so_far(r) == pytest.approx(0.02)  # the reservation and its release net to zero
    kinds = [json.loads(x)["kind"] for x in (r / "spend.jsonl").read_text().splitlines()]
    assert kinds == ["reserve", "stop", "release"]
