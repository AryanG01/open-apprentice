"""Local executor: repeatedly step() the committed log and perform the returned action exactly as the spec's worker does
(Plan 4 moves this behind Cloud Tasks). Effects are claimed in the store by action id, so a restart or a duplicate run
never re-performs an action whose claim exists. Failures are recorded as events, never left to wedge a session."""

from __future__ import annotations

import uuid
from fractions import Fraction
from typing import Optional, Protocol

from open_apprentice.concepts.label_teaching import describe_compact
from open_apprentice.providers.base import ProviderTimeout, TruncatedOutput
from open_apprentice.storage.store import Store
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger, OverBudget
from open_apprentice.teaching.constraints import derive
from open_apprentice.teaching.events import Conflict, Event, SessionLog
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
    Request,
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
TRANSIENT = ("truncation", "timeout", "transport")


def failure_kind(e: BaseException) -> str:
    """Categorise a provider failure. Only truncation, timeout and transport are retried (spec 3.7)."""
    if isinstance(e, TruncatedOutput):
        return "truncation"
    if isinstance(e, (ProviderTimeout, TimeoutError)):
        return "timeout"
    if isinstance(e, ConnectionError) or "transport" in str(e).lower():
        return "transport"
    if isinstance(e, (ValueError, KeyError, TypeError)) or "format" in type(e).__name__.lower():
        return "format"
    return "other"


def well_formed(c: object) -> bool:
    return isinstance(c, dict) and isinstance(c.get("rule"), list)


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

    # ---- teacher responses
    def submit_response(self, resp: Response) -> bool:
        """Accept a teacher response only if its request is outstanding, committing against the exact log
        revision that was checked (a concurrent answer makes this re-check, not double-record). Returns False and
        records nothing otherwise."""
        for _ in range(20):
            m, _ = self.log.manifest()
            evs = self.log.events()
            if (evs[-1].event_id if evs else None) != m["head_event_id"]:
                continue  # the log moved between the two reads
            try:
                return self._submit_checked(resp, evs, m["manifest_revision"])
            except Conflict:
                continue
        return False

    def _submit_checked(self, resp: Response, evs: list[Event], revision: int) -> bool:
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
        self.log.append(
            "ResponseRecorded",
            origin,
            {"response": response_to_json(resp)},
            expected_revision=revision,
        )
        return True

    # ---- actions
    def _attempts_used(self) -> int:
        return sum(
            1
            for e in self.log.events()
            if (e.type == "ActionIssued" and e.payload.get("kind") == "RequestModelProposal")
            or (e.type == "ModelCallFailed" and not e.payload.get("terminal"))
        )

    def _fail(self, action_id: str, reason: str, terminal: bool) -> None:
        self.log.append(
            "ModelCallFailed",
            "system",
            {"action_id": action_id, "reason": reason, "terminal": terminal},
        )

    def _propose(self, action: RequestModelProposal) -> None:
        self._issue(action.action_id, "RequestModelProposal", {"round_kind": action.round_kind})
        ev = derive(self.log.events())
        evidence = {"teaching_evidence": describe_compact(ev.positives)}
        for attempt_no in range(1, MAX_TRIES + 1):
            if attempt_no > 1 and self._attempts_used() >= self.config.max_attempts:
                self._fail(action.action_id, "attempt budget", True)
                return
            attempt = uuid.uuid4().hex
            try:
                self.ledger.reserve(attempt, action.action_id, self.worst)
            except OverBudget as e:
                self._fail(action.action_id, f"budget: {e}", True)
                return
            self.ledger.dispatched(attempt)
            try:
                cands, usage, cost = self.proposer.propose(
                    evidence, action.round_kind, action.feedback
                )
            except Exception as e:  # provider failure: cost unknown, kept at worst case
                self.ledger.mark_unknown(attempt)
                kind = failure_kind(e)
                terminal = attempt_no == MAX_TRIES or kind not in TRANSIENT
                self._fail(action.action_id, kind, terminal)
                if terminal:
                    return
                continue
            self.ledger.settle(attempt, cost)
            kept = [c for c in cands if well_formed(c)]
            self.log.append(
                "ModelProposalReturned",
                "model",
                {
                    "action_id": action.action_id,
                    "candidates": kept,
                    "malformed": len(cands) - len(kept),
                    "usage": usage,
                },
            )
            return

    def _deliver(self, request: Request) -> None:
        try:
            resp = self.teacher.ask(request)
        except ProtocolError as e:
            self.log.append(
                "Errored",
                "system",
                {"action_id": f"teacher-{request.request_id}", "reason": f"protocol: {e}"},
            )
            return
        self.submit_response(resp)

    def _ask(self, action: AskTeacher | PresentPreview) -> None:
        try:
            validate_request(action.request, derive(self.log.events()).scene_hashes)
        except ProtocolError as e:
            self.log.append(
                "Errored", "system", {"action_id": action.action_id, "reason": f"protocol: {e}"}
            )
            return
        self._issue(action.action_id, type(action).__name__)
        self.log.append(
            "RequestIssued",
            "system",
            {"request": request_to_json(action.request), "action_id": action.action_id},
        )
        self._deliver(action.request)

    def _recover(self) -> None:
        """Single-process recovery after a crash: a model action with no result was interrupted (its cost stays in
        the ledger) and is recorded as a terminal failure; a teacher request with no response is asked again with the
        same request id (submit_response keeps only the first answer)."""
        evs = self.log.events()
        if any(e.type in ("VersionStored", "Abstained", "Errored") for e in evs):
            return
        resolved = {
            e.payload.get("action_id")
            for e in evs
            if e.type in ("ModelProposalReturned", "ModelCallFailed")
        }
        terminal_failed = {
            e.payload.get("action_id")
            for e in evs
            if e.type == "ModelCallFailed" and e.payload.get("terminal")
        }
        for e in evs:
            aid = e.payload.get("action_id")
            if (
                e.type == "ActionIssued"
                and e.payload.get("kind") == "RequestModelProposal"
                and (aid not in resolved)
                and aid not in terminal_failed
            ):
                self._fail(aid, "interrupted", True)
                return
        answered = {
            response_from_json(e.payload["response"]).request_id
            for e in evs
            if e.type == "ResponseRecorded"
        }
        for e in evs:
            if e.type == "RequestIssued":
                req = request_from_json(e.payload["request"])
                if req.request_id not in answered:
                    self._deliver(req)
                    return

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
        self._recover()
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
