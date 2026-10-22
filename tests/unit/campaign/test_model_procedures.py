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
    got = asyncio.run(propose_procedures(provider, _ledger(), "fabric"))
    assert got == [APPLY_PLAN]


def test_failures_are_fed_back_and_the_first_passing_program_is_accepted():
    provider = MockProvider(
        {"campaign_procedure": [_reply([{"op": "return", "value": 1}]), _reply(APPLY_PLAN)]}
    )
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
