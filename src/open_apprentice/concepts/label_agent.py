"""The strong same-model baseline for label placement: ONE model, the same evidence, the same language, the same teacher
and the same call/ask budget, but NO candidate set, NO solver- or batch-selected questions and NO commit gate on batch
agreement. It decides for itself when to ask which batch diagram, writes and revises its own rule, and may abstain.
It gets the same exact fit feedback on a failing commit that the main learner's filter applies. Agent-visible code.
"""

from __future__ import annotations

import json
import pathlib
from typing import Callable, Literal, Optional

from pydantic import BaseModel

from open_apprentice.budget import BudgetExhausted, Ledger
from open_apprentice.concepts.hypotheses import Constraint, fits
from open_apprentice.concepts.label_teaching import describe_compact, TeachingResult, to_state
from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.concepts.rules import RuleError, validate_rule
from open_apprentice.concepts.schemas import sha
from open_apprentice.providers.base import (
    CallContext,
    Message,
    ModelFormatError,
    Provider,
    ProviderError,
)

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "agent_labels.md"
MAX_TURNS = 8
MAX_ASKS = 3
MAX_COMMITS = 3


class AgentTurn(BaseModel):
    model_config = {"extra": "ignore"}
    action: Literal["ask", "commit", "abstain"]
    batch_index: Optional[int] = None
    rule_text: Optional[str] = None
    reason: str = ""


async def run_agent(
    provider: Provider,
    ledger: Ledger,
    demos: list[tuple[dict, dict]],
    batch: list[dict],
    teacher: Callable[[dict], dict],
    *,
    max_tokens: int = 6000,
) -> TeachingResult:
    res = TeachingResult("abstained")
    constraints = [Constraint("positive", b, to_state(a), source="demonstration") for b, a in demos]
    first = {
        "teaching_evidence": describe_compact(constraints),
        "batch": [{"index": i, "scene": s} for i, s in enumerate(batch)],
        "asks_left": MAX_ASKS,
        "commit_attempts_left": MAX_COMMITS,
    }
    msgs = [Message("system", PROMPT.read_text()), Message("user", json.dumps(first, default=str))]
    asked: set[int] = set()
    commits = 0
    failures = 0
    aliases = {o["id"]: i for i, o in enumerate(demos[0][0]["objects"])}
    for _ in range(MAX_TURNS):
        try:
            comp = await provider.complete_json(
                messages=msgs,
                output_schema=AgentTurn,
                ctx=CallContext(role="agent", category="agent"),
                ledger=ledger,
                max_tokens=max_tokens,
            )
        except BudgetExhausted:
            res.reason = "model budget exhausted"
            return res
        except ProviderError as e:
            failures += 1
            res.rounds.append({"error": f"{type(e).__name__}: {str(e)[:160]}"})
            if failures >= 3:
                res.reason = "model failed three times in a row"
                return res
            if isinstance(
                e, ModelFormatError
            ):  # same courtesy the main learner gets: tell it what was wrong
                msgs.append(
                    Message(
                        "user",
                        '{"error": "your reply was not a valid move; reply with ONE JSON object whose "action" is ask, commit or abstain"}',
                    )
                )
            continue
        failures = 0
        res.model_calls += 1 + comp.schema_corrections
        for k, v in (
            ("prompt_tokens", comp.prompt_tokens),
            ("completion_tokens", comp.completion_tokens),
        ):
            res.usage[k] = res.usage.get(k, 0) + (v or 0)
        t: AgentTurn = comp.parsed
        msgs.append(Message("assistant", comp.parsed.model_dump_json()))
        if t.action == "abstain":
            res.reason = t.reason or "agent abstained"
            return res
        if t.action == "ask":
            i = t.batch_index
            if i is None or not 0 <= i < len(batch) or i in asked or len(asked) >= MAX_ASKS:
                reply = {"error": "invalid or repeated ask", "asks_left": MAX_ASKS - len(asked)}
            else:
                asked.add(i)
                truth = teacher(batch[i])
                constraints.append(
                    Constraint("positive", batch[i], to_state(truth), source="answer")
                )
                res.questions.append({"batch_index": i})
                reply = {
                    "teacher_shows_for_batch_index": i,
                    "resulting_geometry": describe(constraints[-1:])[0]["resulting_geometry"],
                    "asks_left": MAX_ASKS - len(asked),
                }
            msgs.append(Message("user", json.dumps(reply, default=str)))
            continue
        commits += 1
        try:
            rule = parse_rule_text(t.rule_text or "", aliases)
            validate_rule(rule)
            bad = next((why for c in constraints for ok, why in [fits(rule, c)] if not ok), None)
        except RuleError as e:
            bad = f"syntax: {str(e)[:160]}"
        if bad is None:
            res.status, res.rule, res.rule_hash = "committed", rule, sha(rule)
            res.summary, res.scope = "agent rule", "agent_unverified"
            return res
        if commits >= MAX_COMMITS:
            res.reason = f"commit attempts used up; last problem: {bad[:160]}"
            return res
        msgs.append(
            Message(
                "user",
                json.dumps({"commit_rejected": bad, "commit_attempts_left": MAX_COMMITS - commits}),
            )
        )
    res.reason = "turn limit reached without a decision"
    return res
