"""Synchronous teaching adapters over the async provider API, for the event-sourced executors (which run in worker threads,
never on the event loop). The durable teaching ledger has already reserved the worst case before a call; a call whose cost the
provider does not report raises, so the executor keeps that attempt at worst case (never a silent zero)."""

from __future__ import annotations

import asyncio
import json
import pathlib
from fractions import Fraction
from typing import Optional

from pydantic import BaseModel

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.hypotheses import HypothesisSet
from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.concepts.rules import RuleError, validate_rule
from open_apprentice.providers.base import CallContext, Message, Provider, ValidatedCompletion

PROMPTS = pathlib.Path(__file__).resolve().parents[3] / "prompts"


class ScopeOut(BaseModel):
    model_config = {"extra": "ignore"}
    summary: str = ""
    rule_text: str = ""
    selector: str = ""


class ScopeSet(BaseModel):
    model_config = {"extra": "ignore"}
    candidates: list[ScopeOut]


def _usd(completion: ValidatedCompletion) -> Optional[float]:
    return completion.usd


def _rule(text: str) -> Optional[list]:
    try:
        rule = parse_rule_text(text)
        validate_rule(rule)
    except RuleError:
        return None
    return rule


def _call(
    provider: Provider,
    prompt: pathlib.Path,
    role: str,
    user: dict,
    schema: type[BaseModel],
    max_tokens: int,
) -> tuple[ValidatedCompletion, dict, Fraction]:
    msgs = [Message("system", prompt.read_text()), Message("user", json.dumps(user))]
    done = asyncio.run(
        provider.complete_json(
            messages=msgs,
            output_schema=schema,
            ctx=CallContext(role, "teaching"),
            ledger=Ledger(Limits()),
            max_tokens=max_tokens,
        )
    )
    usd = _usd(done)
    if usd is None:
        raise ValueError("cost unknown: the provider did not report usage")
    usage = {
        "prompt_tokens": done.prompt_tokens,
        "completion_tokens": done.completion_tokens,
        "usage_estimated": done.usage_estimated,
        "provider_label": done.provider_label,
        "model_id": done.model_id,
    }
    return done, usage, Fraction(str(usd))


def _user(evidence_json: dict, round_kind: str, feedback: tuple[str, ...]) -> dict:
    if round_kind == "initial":
        return evidence_json
    return {**evidence_json, "round": round_kind, "feedback": list(feedback)[-8:]}


class ProviderProposer:
    def __init__(
        self,
        provider: Provider,
        prompt_path: pathlib.Path = PROMPTS / "hypotheses_labels.md",
        max_tokens: int = 6000,
    ) -> None:
        self.provider, self.prompt, self.max_tokens = provider, prompt_path, max_tokens

    def propose(
        self, evidence_json: dict, round_kind: str, feedback: tuple[str, ...]
    ) -> tuple[list[dict], dict, Fraction]:
        done, usage, cost = _call(
            self.provider,
            self.prompt,
            "hypotheses",
            _user(evidence_json, round_kind, feedback),
            HypothesisSet,
            self.max_tokens,
        )
        cands, malformed = [], 0
        for c in done.parsed.candidates:
            ast, text = c.source()
            rule = ast if ast is not None else (_rule(text) if text else None)
            if rule is None:
                malformed += 1
                continue
            cands.append({"rule": rule, "summary": c.summary, "text": text or ""})
        return cands, {**usage, "malformed": malformed}, cost


class ProviderScopeProposer:
    def __init__(
        self,
        provider: Provider,
        prompt_path: pathlib.Path = PROMPTS / "correction_scope.md",
        max_tokens: int = 6000,
    ) -> None:
        self.provider, self.prompt, self.max_tokens = provider, prompt_path, max_tokens

    def propose_scope(
        self, evidence_json: dict, round_kind: str
    ) -> tuple[list[dict], dict, Fraction]:
        done, usage, cost = _call(
            self.provider,
            self.prompt,
            "correction_scope",
            _user(evidence_json, round_kind, ()),
            ScopeSet,
            self.max_tokens,
        )
        cands, malformed = [], 0
        for c in done.parsed.candidates:
            rule = _rule(c.rule_text) if c.rule_text.strip() else None
            if rule is None or not c.selector.strip():
                malformed += 1
                continue
            cands.append({"rule": rule, "selector": c.selector, "summary": c.summary})
        return cands, {**usage, "malformed": malformed}, cost
