"""Teaching session state machine (spec 8.6, 8.9, 9.8).

  HYPOTHESES_READY -> AWAITING_USER (question or correction request) | INTENT_READY | UNRESOLVED

Hard limits per concept: <= 2 user queries, <= 2 candidate-generation rounds. 'Neither' never forces a
pick: it either triggers a counted corrected example + a second generation round, or ends honestly as
UNRESOLVED. Every candidate must satisfy the ENTIRE ledger. The session stores no private rule; the
teacher is an external object that only sees the public query view.
"""

from __future__ import annotations

import asyncio

import enum
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from open_apprentice.budget import Ledger
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.hypotheses import (
    Candidate,
    Constraint,
    GenerationReport,
    generate_candidates,
    neutral,
)
from open_apprentice.concepts.query_selection import (
    Query,
    apply_answer,
    build_query,
    public_view,
    select_query,
)
from open_apprentice.concepts.schemas import Concept, IntentState, TeachingLedger
from open_apprentice.concepts.witness import SolverBudget, SolverPool, find_disagreement
from open_apprentice.providers.base import Provider

MAX_QUERIES = 2
MAX_ROUNDS = 2


class State(str, enum.Enum):
    TEACHING = "TEACHING"
    HYPOTHESES_READY = "HYPOTHESES_READY"
    AWAITING_USER = "AWAITING_USER"
    INTENT_READY = "INTENT_READY"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class TeachingSession:
    provider: Optional[Provider]
    budget: Ledger
    dom: DomainManifest
    object_counts: list[int]
    pool: Optional[SolverPool] = None
    seed: int = 0
    teacher_source: str = "user"
    state: State = State.TEACHING
    ledger: TeachingLedger = field(default_factory=TeachingLedger)
    constraints: list[Constraint] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    rejected_summaries: list[str] = field(default_factory=list)
    reports: list[GenerationReport] = field(default_factory=list)
    queries_asked: int = 0
    rounds: int = 0
    pending: Optional[Query] = None
    pending_kind: str = ""  # "question" | "correction"
    pending_scene: Optional[dict] = None
    intent_state: IntentState = IntentState.UNRESOLVED
    unresolved_reason: str = ""
    user_corrected: bool = False
    solver_budget: SolverBudget = field(default_factory=SolverBudget)
    # Alternative candidate source (e.g. the non-LLM enumerative reference). Same constraints, same questions.
    completion_cap: int = (
        6000  # per model call; reasoning tokens share it (raise with reasoning_effort)
    )
    prefer_readable_queries: bool = (
        False  # human-facing sessions: break ties toward readable sampled scenes (never changes scores)
    )
    audit: bool = (
        False  # one EXTRA generation round that looks for other rules fitting ALL evidence (incl. answers) after a settle
    )
    seek_disagreement: bool = (
        True  # exactly one fit and no question yet: spend the 2nd round asking for different rules that also fit
    )
    _alt_done: bool = False
    correction_turn: bool = (
        True  # one counted numeric-feedback turn when no candidate fits (shared by all model-based methods)
    )
    candidate_source: Optional[
        Callable[[list[Constraint], int, list[str]], Awaitable[GenerationReport]]
    ] = None

    # ------------------------------------------------------------------ generation
    async def _generate(self, alternatives: bool = False) -> None:
        self.rounds += 1
        if self.candidate_source is not None:
            rep = await self.candidate_source(
                self.constraints, self.rounds, self.rejected_summaries
            )
        else:
            rep = await generate_candidates(
                self.provider,
                self.budget,
                self.constraints,
                rnd=self.rounds,
                rejected_summaries=self.rejected_summaries,
                object_counts=self.object_counts,
                correction_turn=self.correction_turn,
                max_tokens=self.completion_cap,
                alternatives_to=self.candidates if alternatives else None,
            )
            if alternatives:  # keep the rule that already fit; add the new distinct fits
                have = {c.hash for c in self.candidates}
                rep.accepted = (self.candidates + [c for c in rep.accepted if c.hash not in have])[
                    :4
                ]
        self.reports.append(rep)
        self.rejected_summaries += [
            f'{r["summary"][:80]} -- REJECTED: {r["reason"][:200]}' for r in rep.rejected
        ]
        self.candidates = rep.accepted

    async def start(self, demonstration: dict) -> None:
        """demonstration = {"scene": {objects, canvas}, "after": {key: {x,y,w,h}}} (public geometry only)."""
        self.ledger.append("demonstration", neutral(demonstration), self.teacher_source)
        self.constraints.append(
            Constraint(
                "positive", demonstration["scene"], demonstration["after"], source="demonstration"
            )
        )
        await self._generate()
        await self._advance()

    # ------------------------------------------------------------------ progression
    async def _advance(self) -> None:
        if not self.candidates:
            if self.rounds < MAX_ROUNDS:
                await self._generate()
                if self.candidates:
                    await self._advance()
                    return
            self._end_unresolved(
                "candidate_generation_failure: no proposed rule fits all teaching evidence"
            )
            return
        if (
            self.audit
            and len(self.candidates) == 1
            and not self._alt_done
            and self.rounds < MAX_ROUNDS + 1
            and self.candidate_source is None
        ):
            self._alt_done = (
                True  # the audit may use a third round even when the questions are used up
            )
            await self._generate(alternatives=True)
            await self._advance()
            return
        if (
            len(self.candidates) == 1
            and self.seek_disagreement
            and not self._alt_done
            and self.queries_asked == 0
            and not self.user_corrected
            and self.rounds < MAX_ROUNDS
            and self.candidate_source is None
        ):
            self._alt_done = True
            await self._generate(alternatives=True)
            await self._advance()
            return
        if len(self.candidates) == 1:
            self._ready(
                IntentState.USER_CORRECTED
                if self.user_corrected
                else (
                    IntentState.RESOLVED_WITHIN_CANDIDATE_SET
                    if self.queries_asked
                    else IntentState.CONSISTENT_WITH_EXAMPLES
                )
            )
            return
        rules = [c.rule for c in self.candidates]
        if self.queries_asked >= MAX_QUERIES:
            await self._settle_without_more_questions(rules)
            return
        # Solver work runs in a worker thread so one visitor's search never stalls the server for everyone else.
        sc = await asyncio.to_thread(
            select_query,
            rules,
            self.dom,
            self.object_counts,
            self.solver_budget,
            self.pool,
            self.seed + self.queries_asked,
            prefer_readable=self.prefer_readable_queries,
        )
        if sc is None:
            await self._settle_without_more_questions(rules)
            return
        self.pending = build_query(rules, sc)
        self.pending_kind = "question"
        self.ledger.append(
            "query",
            {
                "query_id": self.pending.query_id,
                "source": self.pending.source,
                "scene": neutral(self.pending.input_scene),
                "options": neutral(self.pending.options),
            },
            "system",
        )
        self.state = State.AWAITING_USER

    async def _settle_without_more_questions(self, rules: list[list]) -> None:
        """No (more) askable question. Decide honestly whether the survivors are equivalent in the model."""
        res = await asyncio.to_thread(
            find_disagreement,
            rules,
            self.object_counts,
            self.dom,
            budget=self.solver_budget,
            pool=self.pool,
        )
        if res.status == "no_witness_in_model":
            self._ready(
                (
                    IntentState.USER_CORRECTED
                    if self.user_corrected
                    else IntentState.RESOLVED_WITHIN_CANDIDATE_SET
                ),
                note="remaining candidates agree everywhere in the encoded domain (not a proof of intent)",
            )
        else:
            self._end_unresolved(
                f"ambiguity_remains: candidates still disagree or could not be checked "
                f"(solver status={res.status}; query budget {self.queries_asked}/{MAX_QUERIES})",
                IntentState.CONSISTENT_WITH_EXAMPLES,
            )

    def _ready(self, st: IntentState, note: str = "") -> None:
        self.intent_state, self.state, self.unresolved_reason = st, State.INTENT_READY, note

    def _end_unresolved(self, reason: str, st: IntentState = IntentState.UNRESOLVED) -> None:
        self.state, self.intent_state, self.unresolved_reason = State.UNRESOLVED, st, reason

    # ------------------------------------------------------------------ user interaction
    def public_question(self) -> dict:
        assert (
            self.state == State.AWAITING_USER
            and self.pending is not None
            and self.pending_kind == "question"
        )
        return public_view(self.pending)

    async def answer(self, query_id: str, answer: str, candidate_set: str) -> None:
        if (
            self.state != State.AWAITING_USER
            or self.pending is None
            or self.pending_kind != "question"
        ):
            raise ValueError("no question is awaiting an answer")
        if query_id != self.pending.query_id:
            raise ValueError("stale answer: a different question is pending")
        rules = [c.rule for c in self.candidates]
        kept = apply_answer(
            rules, self.pending, answer, candidate_set
        )  # raises on stale candidate set
        q, self.pending = self.pending, None
        self.queries_asked += 1
        self.ledger.append(
            "answer",
            {"query_id": q.query_id, "answer": answer, "candidate_set_hash": q.candidate_set_hash},
            self.teacher_source,
        )
        if answer == "neither":
            self.constraints.append(
                Constraint(
                    "excludes", q.input_scene, excluded=tuple(q.options.values()), source="neither"
                )
            )
            if self.rounds >= MAX_ROUNDS:
                self._end_unresolved("neither_with_no_generation_rounds_left")
                return
            self.pending_kind, self.pending_scene, self.state = (
                "correction",
                q.input_scene,
                State.AWAITING_USER,
            )
            return
        self.constraints.append(
            Constraint("positive", q.input_scene, q.options[answer], source="answer")
        )
        self.candidates = [self.candidates[i] for i in kept]
        await self._advance()

    def correction_request(self) -> dict:
        assert self.state == State.AWAITING_USER and self.pending_kind == "correction"
        return {
            "input_scene": neutral(self.pending_scene),
            "ask": "provide the correct resulting geometry for this scene",
        }

    async def submit_correction(self, corrected_after: dict) -> None:
        """A corrected output is an additional COUNTED teacher interaction (it does not reveal the formula)."""
        if self.state != State.AWAITING_USER or self.pending_kind != "correction":
            raise ValueError("no correction requested")
        scene, self.pending_scene, self.pending_kind = self.pending_scene, None, ""
        self.ledger.append(
            "corrected_example",
            {"scene": neutral(scene), "after": neutral(corrected_after)},
            self.teacher_source,
        )
        self.constraints.append(
            Constraint("positive", scene, corrected_after, source="corrected_example")
        )
        self.user_corrected = True
        self.state = State.HYPOTHESES_READY
        await self._generate()
        await self._advance()

    # ------------------------------------------------------------------ output
    def finalize(self, concept_id: str = "concept-1") -> Concept:
        if self.state != State.INTENT_READY or not self.candidates:
            raise ValueError(
                f"cannot finalize in state {self.state.value}: {self.unresolved_reason}"
            )
        c = self.candidates[0]
        return Concept.create(
            concept_id, 1, c.summary, c.rule, self.dom.hash, self.ledger, self.intent_state
        )
