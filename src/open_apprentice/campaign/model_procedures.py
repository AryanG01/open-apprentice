"""Nemotron-written native procedures (plan 9E, spec 7.4). A candidate is used only if the caller's check (the independent
verifier against gold on retained and fresh banners, run on the evaluator side) passes it; otherwise the reference
procedure is used and labelled. The prompt never contains the reference program."""

from __future__ import annotations

import asyncio
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable

from open_apprentice.budget import Ledger
from open_apprentice.campaign.builtins import split_two_cards
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.layout_rule import evaluate_layout, objects_for_rule, wrap_learned
from open_apprentice.campaign.learn import learn_layout
from open_apprentice.campaign.model import call_model
from open_apprentice.campaign.plan import plan_from_layout
from open_apprentice.campaign.procedures import APPLY_PLAN, APPLY_TOOLS, plan_inputs
from open_apprentice.providers.base import Provider, StrictModel
from open_apprentice.skills.interpreter import ProgramError, validate_program

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "campaign_procedure.md"
MAX_ATTEMPTS = 3


class ProgramOut(StrictModel):
    program: list[Any]
    summary: str


class ProgramSet(StrictModel):
    candidates: list[ProgramOut]


@dataclass
class ProcedureCheck:
    passed: bool
    cases: list[dict]


@dataclass
class ProcedureOutcome:
    program: list
    origin: str  # model | reference
    attempts: list[dict] = field(default_factory=list)


def _example_inputs() -> list[dict]:
    """Two real plan inputs (one card; two cards) from public development fixtures, so the model sees the field shapes."""
    learned = asyncio.run(
        learn_layout(load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"])
    )
    out = []
    for fid, transform in (("short_a", lambda p: p), ("de_long_a", split_two_cards)):
        src = load_fixture(fid)["scene"]
        res = evaluate_layout(
            wrap_learned(learned.rule),
            objects_for_rule(src, "banner"),
            {"output_format": "9:16", "overflows": False},
        )
        out.append(plan_inputs(transform(plan_from_layout(res, src, "banner", learned.origin))))
    return out


async def propose_procedures(
    provider: Provider, ledger: Ledger, backend: str, failures: list[str] | None = None
) -> list[list]:
    examples = await asyncio.to_thread(_example_inputs)
    payload = {"backend": backend, "example_inputs": examples, "previous_failures": failures or []}
    res = await call_model(
        provider,
        ledger,
        role="campaign_procedure",
        prompt=PROMPT,
        payload=payload,
        schema=ProgramSet,
        max_tokens=6000,
    )
    if res.parsed is None:
        return []
    kept = []
    for c in res.parsed.candidates[:2]:
        try:
            validate_program(
                c.program, APPLY_TOOLS
            )  # only allowlisted tools, within the static caps
        except ProgramError:
            continue
        kept.append(c.program)
    return kept


async def write_procedure(
    provider: Provider | None,
    ledger: Ledger | None,
    backend: str,
    check: Callable[[list], ProcedureCheck],
) -> ProcedureOutcome:
    if provider is None:
        return ProcedureOutcome(APPLY_PLAN, "reference")
    attempts: list[dict] = []
    failures: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        candidates = await propose_procedures(provider, ledger, backend, failures)
        if not candidates:
            attempts.append({"passed": False, "cases": [], "note": "no usable candidate"})
            failures = [
                "your previous reply had no valid program (check the tool names and the language)"
            ]
            continue
        for program in candidates:
            result = await asyncio.to_thread(check, program)
            attempts.append({"passed": result.passed, "cases": result.cases})
            if result.passed:
                return ProcedureOutcome(program, "model", attempts)
            failures = [
                f"{c['fixture']}/{c['outcome']}: "
                + ", ".join(c.get("failed_checks") or [c.get("error", "failed")])
                for c in result.cases
                if not c["passed"]
            ]
    return ProcedureOutcome(APPLY_PLAN, "reference", attempts)
