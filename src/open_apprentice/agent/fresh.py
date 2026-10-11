"""Fresh agent (spec 9.1): propose a typed program, execute it, read public feedback, correct.

Competent baseline by design: it observes the scene, may check its work with observe_geometry, and
gets up to `max_cycles` propose/execute rounds with coarse operational feedback. It never sees the
evaluator, native state, drift config, or final scores (import-linter + engine route separation).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

from open_apprentice.budget import BudgetExhausted, Ledger
from open_apprentice.environments.client import EngineSession, EngineToolError
from open_apprentice.environments.operational import check_gap_row_public
from open_apprentice.environments.tasks import PUBLIC_TOOLS
from open_apprentice.providers.base import (
    CallContext,
    Message,
    Provider,
    ProviderError,
    StrictModel,
)
from open_apprentice.skills.interpreter import ProgramError, run_program

PROMPT_PATH = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "fresh_gap_row.md"


class Proposal(StrictModel):
    diagnosis: str = ""
    program: list[dict[str, Any]]


@dataclass
class AgentResult:
    status: str  # operational_pass | operational_fail | budget_exhausted | provider_error
    cycles: int
    trace: list[dict] = field(default_factory=list)
    prompt_hash: str = ""
    final_program: list[dict] | None = None


def prompt_text() -> tuple[str, str]:
    t = PROMPT_PATH.read_text()
    return t, hashlib.sha256(t.encode()).hexdigest()


async def run_fresh(
    task_view: dict,
    session: EngineSession,
    provider: Provider,
    ledger: Ledger,
    *,
    max_cycles: int = 3,
    max_tokens: int = 2048,
) -> AgentResult:
    system, phash = prompt_text()
    res = AgentResult("operational_fail", 0, prompt_hash=phash)
    scene = session.call("inspect_scene")
    messages = [
        Message("system", system),
        Message("user", json.dumps({"task": task_view, "scene": scene})),
    ]
    tools = session.tools(PUBLIC_TOOLS)

    for cycle in range(1, max_cycles + 1):
        res.cycles = cycle
        try:
            comp = await provider.complete_json(
                messages=messages,
                output_schema=Proposal,
                ctx=CallContext(role="fresh", category="execution"),
                ledger=ledger,
                max_tokens=max_tokens,
            )
        except BudgetExhausted as e:
            res.status = "budget_exhausted"
            res.trace.append({"cycle": cycle, "event": "budget", "detail": str(e)})
            return res
        except ProviderError as e:
            res.status = "provider_error"
            res.trace.append({"cycle": cycle, "event": e.code})
            return res

        prog = comp.parsed.program
        before = session.actions_used
        feedback: dict[str, Any]
        try:
            run_program(prog, {}, tools)
            bounds = session.call("observe_geometry", node_ids=task_view["selected_ids"])["bounds"]
            chk = check_gap_row_public(bounds, task_view)
            feedback = {"executed": True, **chk, "observed": bounds}
        except (ProgramError, EngineToolError) as e:
            feedback = {"executed": False, "passed": False, "error": str(e)[:300]}
        try:
            ledger.charge_actions("execution", session.actions_used - before)
        except BudgetExhausted as e:
            res.status = "budget_exhausted"
            res.trace.append({"cycle": cycle, "event": "budget", "detail": str(e)})
            return res
        res.final_program = prog
        res.trace.append(
            {
                "cycle": cycle,
                "provider": comp.provider_label,
                "model": comp.model_id,
                "diagnosis": comp.parsed.diagnosis,
                "feedback": {k: v for k, v in feedback.items() if k != "observed"},
            }
        )
        if feedback["passed"]:
            res.status = "operational_pass"
            return res
        messages = messages + [
            Message("assistant", comp.parsed.model_dump_json()),
            Message(
                "user",
                json.dumps(
                    {
                        "operational_feedback": feedback,
                        "note": "The scene now reflects your previous attempt. Correct it.",
                    }
                ),
            ),
        ]
    return res
