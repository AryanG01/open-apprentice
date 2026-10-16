"""Runs a correction cycle: same claim/record discipline as the learning executor; a commit stores an immutable version
and activates it only by compare-and-set against the pointer generation captured when the correction started."""

from __future__ import annotations

import uuid
from fractions import Fraction
from typing import Optional, Protocol

from open_apprentice.skills.versions import ActivationRejected, SkillStore
from open_apprentice.storage.store import Store
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger, OverBudget
from open_apprentice.teaching.constraints import scene_from_payload
from open_apprentice.teaching.correction_step import (
    CommitCorrection,
    CorrectionConfig,
    Dismiss,
    RecordOverride,
    correction_step,
)
from open_apprentice.teaching.corrections import derive_draft
from open_apprentice.teaching.events import Conflict, SessionLog
from open_apprentice.teaching.executor import (
    MAX_TRIES,
    TRANSIENT,
    claim,
    failure_kind,
    submit_response,
)
from open_apprentice.teaching.step import (
    Abstain,
    AskTeacher,
    Error,
    PresentPreview,
    RequestModelProposal,
    WaitForResult,
)
from open_apprentice.teaching.teacher import (
    Output,
    ProtocolError,
    Request,
    Response,
    Teacher,
    _out_json,
    request_from_json,
    request_to_json,
    response_from_json,
    validate_request,
)


class ScopeProposer(Protocol):
    def propose_scope(
        self, evidence_json: dict, round_kind: str
    ) -> tuple[list[dict], dict, Fraction]: ...


def start_correction(
    store: Store,
    sid: str,
    skill_id: str,
    scene_id: str,
    scene: dict,
    corrected_output: Output,
    mask: list[str],
    extra_scenes: dict[str, dict],
    full_approval: bool = False,
    owner: str = "o",
) -> SessionLog:
    """Open a correction session against the ACTIVE version, capturing the pointer generation it started from."""
    skills = SkillStore(store)
    version, _, generation = skills.active(skill_id)
    if version is None:
        raise ValueError(f"{skill_id} has no active version to correct")
    base = skills.version(skill_id, version)
    log = SessionLog(store, sid)
    log.create(owner=owner)
    log.append(
        "CorrectionStarted",
        "human",
        {
            "skill_id": skill_id,
            "base_version": version,
            "base_pointer_generation": generation,
            "base_artifact": base,
            "scene_id": scene_id,
            "scene": codec.loads(codec.dumps(scene)),
            "scene_hash": codec.digest(scene_from_payload(codec.loads(codec.dumps(scene)))),
            "corrected_output": _out_json(corrected_output),
            "mask": list(mask),
            "full_approval": full_approval,
        },
    )
    scenes = {i["scene_id"]: i["scene"] for i in base["evidence"]}
    scenes.update({k: codec.loads(codec.dumps(v)) for k, v in extra_scenes.items()})
    for k in sorted(scenes):
        if k == scene_id:
            continue
        log.append(
            "SceneRegistered",
            "system",
            {
                "scene_id": k,
                "scene_hash": codec.digest(scene_from_payload(scenes[k])),
                "scene": scenes[k],
                "role": "batch",
            },
        )
    return log


class CorrectionExecutor:
    def __init__(
        self,
        store: Store,
        log: SessionLog,
        proposer: ScopeProposer,
        teacher: Teacher,
        ledger: Ledger,
        config: CorrectionConfig = CorrectionConfig(),
        worst_usd: Fraction = Fraction(1, 5),
    ) -> None:
        self.store, self.log, self.proposer, self.teacher = store, log, proposer, teacher
        self.ledger, self.config, self.worst = ledger, config, worst_usd

    def _claim(self, action_id: str) -> bool:
        return claim(self.store, f"claims/{self.log.sid}/{action_id}.json")

    def _status(self) -> Optional[str]:
        types = {e.type for e in self.log.events()}
        for t, s in (
            ("VersionActivated", "activated"),
            ("ActivationRejected", "activation_rejected"),
            ("OverrideRecorded", "override"),
            ("CorrectionDismissed", "dismissed"),
            ("Abstained", "abstained"),
            ("Errored", "error"),
        ):
            if t in types:
                return s
        return None

    def submit_response(self, resp: Response) -> bool:
        return submit_response(self.log, resp)

    def abandon(self) -> None:
        """The person abandons the correction: nothing stored changes (spec 5). No effect once it has ended."""
        if self._status() is None and not any(e.type == "VersionStored" for e in self.log.events()):
            self.log.append("CorrectionAbandoned", "human", {})

    def _deliver(self, request: Request, action_id: str) -> None:
        try:
            resp = self.teacher.ask(request)
        except ProtocolError as e:
            self.log.append(
                "Errored", "system", {"action_id": action_id, "reason": f"protocol: {e}"}
            )
            return
        if resp is not None:  # None: delivered to a person, who answers later via submit_response
            self.submit_response(resp)

    def _recover(self) -> None:
        """Single-process recovery after a crash, mirroring the learning executor: a stored version whose activation
        was never recorded is activated (or reconciled) against the starting generation; a model call with no result
        was interrupted and is a terminal failure; an unanswered request is asked again with the same request id.
        """
        evs = self.log.events()
        if self._status() is not None:
            return
        stored = next((e for e in evs if e.type == "VersionStored"), None)
        if stored is not None:
            self._activate(stored.payload["action_id"], stored.payload["version"])
            return
        resolved = {
            e.payload.get("action_id")
            for e in evs
            if e.type in ("ModelProposalReturned", "ModelCallFailed")
        }
        for e in evs:
            if (
                e.type == "ActionIssued"
                and e.payload.get("kind") == "RequestModelProposal"
                and e.payload["action_id"] not in resolved
            ):
                self.log.append(
                    "ModelCallFailed",
                    "system",
                    {
                        "action_id": e.payload["action_id"],
                        "reason": "interrupted",
                        "terminal": True,
                    },
                )
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
                    self._deliver(req, e.payload["action_id"])
                    return

    def _propose(self, action: RequestModelProposal) -> None:
        self.log.append(
            "ActionIssued",
            "system",
            {
                "action_id": action.action_id,
                "kind": "RequestModelProposal",
                "round_kind": action.round_kind,
            },
        )
        d = derive_draft(self.log.events())
        evidence = {
            "base_program": d.base["program"],
            "corrected_scene": d.corrective.scene_id,
            "corrected_labels": list(d.corrective.mask),
            # what was corrected and where to: without these no proposer can explain the edit
            "corrected_scene_objects": codec.loads(codec.dumps(d.corrective.scene["objects"])),
            "canvas": codec.loads(codec.dumps(d.corrective.scene["canvas"])),
            "corrected_output": {
                k: codec.loads(codec.dumps(list(v))) for k, v in (d.corrective.output or {}).items()
            },
        }
        for attempt_no in range(1, MAX_TRIES + 1):
            if (
                attempt_no > 1
                and derive_draft(self.log.events()).attempts >= self.config.max_attempts
            ):
                self.log.append(
                    "ModelCallFailed",
                    "system",
                    {"action_id": action.action_id, "reason": "attempt budget", "terminal": True},
                )
                return
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
                cands, usage, cost = self.proposer.propose_scope(evidence, action.round_kind)
            except Exception as e:  # provider failure: cost unknown, kept at worst case
                self.ledger.mark_unknown(attempt)
                kind = failure_kind(e)
                terminal = attempt_no == MAX_TRIES or kind not in TRANSIENT
                self.log.append(
                    "ModelCallFailed",
                    "system",
                    {"action_id": action.action_id, "reason": kind, "terminal": terminal},
                )
                if terminal:
                    return
                continue
            self.ledger.settle(attempt, cost)
            kept = [
                c
                for c in cands
                if isinstance(c, dict)
                and isinstance(c.get("rule"), list)
                and isinstance(c.get("selector"), str)
            ]
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

    def _ask(self, action: AskTeacher | PresentPreview) -> None:
        d = derive_draft(self.log.events())
        try:
            validate_request(action.request, d.scene_hashes)
        except ProtocolError as e:
            self.log.append(
                "Errored", "system", {"action_id": action.action_id, "reason": f"protocol: {e}"}
            )
            return
        self.log.append(
            "ActionIssued", "system", {"action_id": action.action_id, "kind": type(action).__name__}
        )
        self.log.append(
            "RequestIssued",
            "system",
            {"request": request_to_json(action.request), "action_id": action.action_id},
        )
        self._deliver(action.request, action.action_id)

    def _commit(self, action: CommitCorrection) -> None:
        skill_id = self.log.events()[0].payload["skill_id"]
        version = SkillStore(self.store).store_version(skill_id, action.artifact)
        self.log.append(
            "VersionStored",
            "system",
            {"action_id": action.action_id, "skill_id": skill_id, "version": version},
        )
        self._activate(action.action_id, version)

    def _activate(self, action_id: str, version: int) -> None:
        """Move the pointer from the generation captured at the start, once. If the pointer already carries this
        operation (a crash after the move, before logging), record that instead of retrying."""
        start = self.log.events()[0].payload
        skills, skill_id = SkillStore(self.store), start["skill_id"]
        current, rid, _ = skills.active(skill_id)
        if rid is not None:
            rec = codec.loads(self.store.get(f"skills/{skill_id}/activations/{rid}.json").data)
            if rec["operation_id"] == action_id:
                self._activated(action_id, start["base_version"], current, rid)
                return
        try:
            rid = skills.activate(
                skill_id, version, start["base_pointer_generation"], action_id, self.log.sid
            )
        except ActivationRejected as e:
            self.log.append(
                "ActivationRejected",
                "system",
                {"action_id": action_id, "reason": str(e), "stored_version": version},
            )
            return
        self._activated(action_id, start["base_version"], version, rid)

    def _activated(self, action_id: str, frm: int, to: int, rid: str) -> None:
        self.log.append(
            "VersionActivated",
            "system",
            {"operation_id": action_id, "from": frm, "to": to, "record_id": rid},
        )

    def run(self, max_steps: int = 50) -> str:
        self._recover()
        for _ in range(max_steps):
            status = self._status()
            if status:
                return status
            action = correction_step(self.log.events(), self.config)
            if isinstance(action, WaitForResult):
                return self._status() or "waiting"
            if not self._claim(action.action_id):
                continue
            try:
                if isinstance(action, RequestModelProposal):
                    self._propose(action)
                elif isinstance(action, (AskTeacher, PresentPreview)):
                    self._ask(action)
                elif isinstance(action, CommitCorrection):
                    self._commit(action)
                elif isinstance(action, RecordOverride):
                    start = self.log.events()[0].payload
                    self.log.append(
                        "OverrideRecorded",
                        "system",
                        {
                            "action_id": action.action_id,
                            "scene_id": start["scene_id"],
                            "output": start["corrected_output"],
                        },
                    )
                elif isinstance(action, Dismiss):
                    self.log.append(
                        "CorrectionDismissed", "system", {"action_id": action.action_id}
                    )
                elif isinstance(action, Abstain):
                    self.log.append(
                        "Abstained",
                        "system",
                        {"action_id": action.action_id, "reason": action.reason},
                    )
                elif isinstance(action, Error):
                    self.log.append(
                        "Errored",
                        "system",
                        {"action_id": action.action_id, "reason": action.reason},
                    )
            except Conflict:
                continue
        return "waiting"
