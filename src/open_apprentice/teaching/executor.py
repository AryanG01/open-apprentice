"""Local executor: repeatedly step() the committed log and perform the returned action exactly as the spec's worker does
(Plan 4 moves this behind Cloud Tasks). Effects are claimed in the store by action id, so a restart or a duplicate run
never re-performs an action whose claim exists."""

from __future__ import annotations

import uuid
from fractions import Fraction
from typing import Optional, Protocol

from open_apprentice.concepts.label_teaching import describe_compact
from open_apprentice.storage.store import Store
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger, OverBudget
from open_apprentice.teaching.constraints import derive
from open_apprentice.teaching.events import Conflict, SessionLog
from open_apprentice.teaching.step import (
    Abstain,
    Action,
    AskTeacher,
    CommitVersion,
    Error,
    PresentPreview,
    RequestModelProposal,
    StepConfig,
    WaitForResult,
    step,
)
from open_apprentice.teaching.teacher import (
    ProtocolError,
    Response,
    Teacher,
    request_from_json,
    request_to_json,
    response_from_json,
    response_to_json,
    validate_request,
    validate_response,
)

MAX_TRIES = 2  # one retry for a transient provider failure (spec 3.7)


class Proposer(Protocol):
    def propose(
        self, evidence_json: dict, round_kind: str, feedback: tuple[str, ...]
    ) -> tuple[list[dict], dict, Fraction]: ...


class Executor:
    def __init__(
        self,
        store: Store,
        log: SessionLog,
        proposer: Proposer,
        teacher: Teacher,
        ledger: Ledger,
        config: StepConfig,
        worst_usd: Fraction = Fraction(1, 5),
    ) -> None:
        self.store, self.log, self.proposer, self.teacher = store, log, proposer, teacher
        self.ledger, self.config, self.worst = ledger, config, worst_usd

    def _claim(self, action_id: str) -> bool:
        return self.store.create(f"claims/{action_id}.json", codec.dumps({"action_id": action_id}))

    def _issue(self, action_id: str, kind: str, extra: Optional[dict] = None) -> None:
        self.log.append(
            "ActionIssued", "system", {"action_id": action_id, "kind": kind, **(extra or {})}
        )

    def submit_response(self, resp: Response) -> bool:
        """Accept a teacher response only if its request is outstanding. Returns False (and records nothing)
        otherwise."""
        evs = self.log.events()
        reqs = {
            request_from_json(e.payload["request"]).request_id: request_from_json(
                e.payload["request"]
            )
            for e in evs
            if e.type == "RequestIssued"
        }
        answered = {
            response_from_json(e.payload["response"]).request_id
            for e in evs
            if e.type == "ResponseRecorded"
        }
        req = reqs.get(resp.request_id)
        if req is None or resp.request_id in answered:
            return False
        try:
            validate_response(req, resp)
        except ProtocolError:
            return False
        origin = "simulator" if resp.source in ("simulator", "deterministic_simulator") else "human"
        self.log.append("ResponseRecorded", origin, {"response": response_to_json(resp)})
        return True

    def _propose(self, action: RequestModelProposal) -> None:
        self._issue(action.action_id, "RequestModelProposal", {"round_kind": action.round_kind})
        ev = derive(self.log.events())
        evidence = {"teaching_evidence": describe_compact(ev.positives)}
        for attempt_no in range(1, MAX_TRIES + 1):
            attempt = uuid.uuid4().hex
            try:
                self.ledger.reserve(attempt, action.action_id, self.worst)
            except OverBudget as e:
                self.log.append(
                    "ModelCallFailed",
                    "system",
                    {"action_id": action.action_id, "reason": f"budget: {e}", "terminal": True},
                )
                return
            self.ledger.dispatched(attempt)
            try:
                cands, usage, cost = self.proposer.propose(
                    evidence, action.round_kind, action.feedback
                )
            except Exception as e:  # provider failure: cost unknown, kept at worst case
                self.ledger.mark_unknown(attempt)
                terminal = attempt_no == MAX_TRIES
                self.log.append(
                    "ModelCallFailed",
                    "system",
                    {
                        "action_id": action.action_id,
                        "reason": type(e).__name__,
                        "terminal": terminal,
                    },
                )
                if terminal:
                    return
                continue
            self.ledger.settle(attempt, cost)
            self.log.append(
                "ModelProposalReturned",
                "model",
                {"action_id": action.action_id, "candidates": cands, "usage": usage},
            )
            return

    def _ask(self, action: AskTeacher | PresentPreview) -> None:
        validate_request(action.request, derive(self.log.events()).scene_hashes)
        self._issue(action.action_id, type(action).__name__)
        self.log.append(
            "RequestIssued",
            "system",
            {"request": request_to_json(action.request), "action_id": action.action_id},
        )
        self.submit_response(self.teacher.ask(action.request))

    def _perform(self, action: Action) -> None:
        if isinstance(action, WaitForResult) or not self._claim(action.action_id):
            return
        if isinstance(action, RequestModelProposal):
            self._propose(action)
        elif isinstance(action, (AskTeacher, PresentPreview)):
            self._ask(action)
        elif isinstance(action, CommitVersion):
            self._issue(action.action_id, "CommitVersion")
            record = {"rule": action.rule, "summary": action.summary, "claim": action.claim}
            self.store.create(f"programs/{action.program_hash}.json", codec.dumps(record))
            self.log.append(
                "VersionStored",
                "system",
                {"action_id": action.action_id, "program_hash": action.program_hash},
            )
        elif isinstance(action, Abstain):
            self.log.append(
                "Abstained", "system", {"action_id": action.action_id, "reason": action.reason}
            )
        elif isinstance(action, Error):
            self.log.append(
                "Errored", "system", {"action_id": action.action_id, "reason": action.reason}
            )

    def run(self, max_steps: int = 50) -> str:
        for _ in range(max_steps):
            types = {e.type for e in self.log.events()}
            if "VersionStored" in types:
                return "committed"
            if "Abstained" in types:
                return "abstained"
            if "Errored" in types:
                return "error"
            action = step(self.log.events(), self.config)
            if isinstance(action, WaitForResult):
                return "waiting"
            try:
                self._perform(action)
            except Conflict:
                continue  # someone else advanced the log: re-read and re-step
        return "waiting"
