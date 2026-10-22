import asyncio
import json

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.model_procedures import (
    ProcedureCheck,
    propose_procedures,
    write_procedure,
)
from open_apprentice.campaign.procedures import APPLY_PLAN
from open_apprentice.providers.mock import MockProvider

BAD_TOOL = [{"op": "call", "tool": "export_scene", "args": {"format": "png"}}]


def _ledger():
    return Ledger(Limits(tokens=200_000, calls=8))


def _reply(*programs):
    return {"candidates": [{"program": p, "summary": "s"} for p in programs]}


def test_a_program_calling_a_tool_outside_the_allowlist_is_dropped_before_any_engine_use():
    provider = MockProvider({"campaign_procedure": [_reply(BAD_TOOL, APPLY_PLAN)]})
    got, error = asyncio.run(propose_procedures(provider, _ledger(), "fabric"))
    assert got == [APPLY_PLAN] and error is None


def test_failures_are_fed_back_and_the_first_passing_program_is_accepted():
    wrong = [{"op": "call", "tool": "move_node", "args": {"node_id": "x", "x": 0, "y": 0}}]
    provider = MockProvider({"campaign_procedure": [_reply(wrong), _reply(APPLY_PLAN)]})
    seen = []

    def check(program):
        seen.append(program)
        ok = program == APPLY_PLAN
        return ProcedureCheck(
            ok,
            [
                {
                    "fixture": "short_b",
                    "outcome": "layout",
                    "passed": ok,
                    "failed_checks": [] if ok else ["matches_gold"],
                }
            ],
        )

    out = asyncio.run(write_procedure(provider, _ledger(), "konva", check))
    assert out.origin == "model" and out.program == APPLY_PLAN and len(out.attempts) == 2
    second_prompt = provider.calls[1][1][-1].content
    assert "matches_gold" in second_prompt


def test_no_passing_program_means_the_reference_procedure():
    provider = MockProvider({"campaign_procedure": [_reply([{"op": "return", "value": 1}])] * 3})
    out = asyncio.run(
        write_procedure(provider, _ledger(), "konva", lambda p: ProcedureCheck(False, []))
    )
    assert out.origin == "reference" and out.program == APPLY_PLAN and len(out.attempts) == 3


def test_without_a_provider_the_reference_is_used_and_nothing_is_checked():
    out = asyncio.run(
        write_procedure(
            None, None, "konva", lambda p: (_ for _ in ()).throw(AssertionError("no check"))
        )
    )
    assert out.origin == "reference" and out.attempts == []


def test_the_prompt_does_not_contain_the_reference_program():
    from open_apprentice.campaign.model_procedures import PROMPT

    assert json.dumps(APPLY_PLAN[0]) not in PROMPT.read_text()
    assert "create_artboard" in PROMPT.read_text()


# Final review fixes (plan 9E).
def test_an_empty_or_call_free_program_is_never_a_candidate():
    provider = MockProvider(
        {"campaign_procedure": [_reply([], [{"op": "let", "name": "a", "value": 1}])]}
    )
    progs, error = asyncio.run(propose_procedures(provider, _ledger(), "konva"))
    assert progs == [] and error is None


def test_an_empty_program_never_falls_through_to_the_reference():
    from open_apprentice.campaign.procedures import apply_plan

    class S:
        def tools(self, names):
            return {n: (lambda **k: {}) for n in names}

    from open_apprentice.campaign.plan import LayoutPlan

    out = apply_plan(S(), LayoutPlan("banner", [], [], {}), [], "model")
    assert out["actions"] == 0  # the empty program ran, not APPLY_PLAN


def test_the_examples_shown_to_the_model_are_not_acceptance_banners():
    from open_apprentice.campaign.model_procedures import EXAMPLE_BANNERS

    assert "de_long_a" not in EXAMPLE_BANNERS and "short_b" not in EXAMPLE_BANNERS


def test_a_budget_error_stops_the_attempts_and_is_reported():
    from open_apprentice.budget import BudgetExhausted

    class Broke(MockProvider):
        async def _call(self, messages, *, max_tokens, ctx):
            raise BudgetExhausted("usd", "cap")

    out = asyncio.run(
        write_procedure(Broke({}), _ledger(), "konva", lambda p: ProcedureCheck(False, []))
    )
    assert (
        out.origin == "reference" and len(out.attempts) == 1 and "budget" in out.attempts[0]["note"]
    )
