"""Correction drafts. Everything a correction does lives in its own session log; the base version is embedded in the
CorrectionStarted event and never modified. The draft constraint set is the base evidence minus approved supersessions,
plus replacements, the corrective edit and preview verdicts. Spec 5."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from open_apprentice.teaching.constraints import TEACHER_ORIGINS, scene_from_payload
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.evidence import EvidenceItem, item_from_json
from open_apprentice.teaching.teacher import (
    ChooseOutput,
    ConfirmCorrectionScope,
    ConfirmPreview,
    Output,
    Request,
    Response,
    _out_parse,
    request_from_json,
    response_from_json,
)


@dataclass
class Draft:
    base: dict
    base_items: list[EvidenceItem]
    corrective: EvidenceItem
    scenes: dict[str, dict] = field(default_factory=dict)
    scene_hashes: dict[str, str] = field(default_factory=dict)
    authorized: Optional[dict] = None
    override: bool = False
    dismissed: bool = False
    cancelled: bool = False
    none_answered: int = 0
    superseded: dict[str, dict] = field(default_factory=dict)
    replacements: list[EvidenceItem] = field(default_factory=list)
    kept_against_supersession: set[str] = field(default_factory=set)
    preview_items: list[EvidenceItem] = field(default_factory=list)
    preview_unsure: int = 0
    rejected_items: list[EvidenceItem] = field(default_factory=list)
    chosen_outputs: list[EvidenceItem] = field(default_factory=list)
    clarifications: int = 0
    affected_used: bool = False
    revision_preview_used: bool = False
    rounds: list[str] = field(default_factory=list)
    attempts: int = 0


def derive_draft(events: list[Event]) -> Draft:
    first = events[0]
    if first.type != "CorrectionStarted":
        raise ValueError("a correction log starts with CorrectionStarted")
    p = first.payload
    base = p["base_artifact"]
    scene = scene_from_payload(p["scene"])
    corrected: Output = _out_parse(p["corrected_output"])
    cid = f"{first.event_id}:0"
    if p.get("full_approval"):
        corrective = EvidenceItem(
            cid, "full", p["scene_id"], scene, output=corrected, source="correction"
        )
    else:
        mask = tuple(p["mask"])
        corrective = EvidenceItem(
            cid,
            "masked",
            p["scene_id"],
            scene,
            output={k: corrected[k] for k in mask},
            mask=mask,
            source="correction",
        )
    d = Draft(base, [item_from_json(e) for e in base["evidence"]], corrective)
    d.scenes[p["scene_id"]] = scene
    d.scene_hashes[p["scene_id"]] = p["scene_hash"]
    requests: dict[str, Request] = {}
    responded: set[str] = set()
    for ev in events[1:]:
        q = ev.payload
        if ev.type == "SceneRegistered":
            d.scenes[q["scene_id"]] = scene_from_payload(q["scene"])
            d.scene_hashes[q["scene_id"]] = q["scene_hash"]
        elif ev.type == "ActionIssued" and q.get("kind") == "RequestModelProposal":
            d.rounds.append(q.get("round_kind", "scope"))
            d.attempts += 1
        elif ev.type == "ModelCallFailed" and not q.get("terminal"):
            d.attempts += 1
        elif ev.type == "RequestIssued":
            req = request_from_json(q["request"])
            requests[req.request_id] = req
            if isinstance(req, (ConfirmCorrectionScope, ChooseOutput)):
                d.clarifications += 1
            elif isinstance(req, ConfirmPreview) and req.purpose == "affected_examples":
                d.affected_used = True
            elif isinstance(req, ConfirmPreview) and req.purpose == "revision_preview":
                d.revision_preview_used = True
        elif ev.type == "ResponseRecorded" and ev.origin in TEACHER_ORIGINS:
            r = response_from_json(q["response"])
            if r.request_id in responded or r.request_id not in requests:
                continue
            responded.add(r.request_id)
            _apply_response(d, requests[r.request_id], r, ev.event_id)
    return d


def _apply_response(d: Draft, req: Request, r: Response, event_id: str) -> None:
    if isinstance(req, ConfirmCorrectionScope):
        if r.kind == "select":
            it = next(i for i in req.interpretations if i.interp_id == r.selected)
            if it.kind == "revise":
                d.authorized = {"selector": it.selector, "interp_id": it.interp_id}
            elif it.kind == "override":
                d.override = True
            else:
                d.dismissed = True
        elif r.kind == "none":
            d.none_answered += 1
        else:
            d.cancelled = True
    elif isinstance(req, ChooseOutput):
        if r.kind == "choose" and r.selected is not None:
            out = dict(req.alternatives)[r.selected]
            sc = d.scenes[req.scene_id]
            d.chosen_outputs.append(
                EvidenceItem(f"{event_id}:0", "full", req.scene_id, sc, output=out, source="answer")
            )
    elif isinstance(req, ConfirmPreview):
        verdicts = dict(r.per_item)
        for k, (item_id, sid, _, out) in enumerate(req.items):
            v = verdicts.get(item_id)
            sc = d.scenes[sid]
            new = EvidenceItem(f"{event_id}:{k}", "full", sid, sc, output=out, source=req.purpose)
            if req.purpose == "affected_examples":
                # affected-example items are named after the base item they would replace
                if v == "approve":
                    d.replacements.append(new)
                    d.superseded[item_id] = {"by": new.id, "approved_by": event_id}
                else:
                    d.kept_against_supersession.add(item_id)
            elif v == "approve":
                d.preview_items.append(new)
            elif v == "reject":
                d.rejected_items.append(
                    EvidenceItem(
                        new.id, "excludes", sid, sc, excluded=(out,), source="revision_reject"
                    )
                )
            else:
                d.preview_unsure += 1


def draft_items(d: Draft) -> list[EvidenceItem]:
    base = [i for i in d.base_items if i.id not in d.superseded]
    return (
        base
        + d.replacements
        + [d.corrective]
        + d.chosen_outputs
        + d.preview_items
        + d.rejected_items
    )
