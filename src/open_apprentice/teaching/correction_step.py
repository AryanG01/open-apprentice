"""Pure correction policy (spec 5). Same discipline as step.py: deterministic, no I/O, the log is the only input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from open_apprentice.concepts.rules import RuleError, validate_rule
from open_apprentice.teaching import codec
from open_apprentice.teaching.corrections import Draft, derive_draft, draft_items
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.evidence import EvidenceItem, item_fits, item_to_json
from open_apprentice.teaching.retention import behaviour_diff, retention_report
from open_apprentice.teaching.scope import SelectorError, members, parse_selector
from open_apprentice.teaching.step import (
    Abstain,
    AskTeacher,
    Error,
    PresentPreview,
    RequestModelProposal,
    WaitForResult,
    _aid,
    _forbidden_effect,
    _groups,
    _usable,
    run_output,
)
from open_apprentice.teaching.teacher import (
    ChooseOutput,
    ConfirmCorrectionScope,
    ConfirmPreview,
    Interpretation,
)

TERMINAL = (
    "VersionStored",
    "OverrideRecorded",
    "CorrectionDismissed",
    "Abstained",
    "Errored",
    "ActivationRejected",
)


@dataclass(frozen=True)
class CorrectionConfig:
    max_clarifications: int = 2
    max_attempts: int = 4
    max_affected: int = 6
    max_revision_preview: int = 3


@dataclass(frozen=True)
class CommitCorrection:
    action_id: str
    rule: list
    summary: str
    selector: str
    artifact: dict


@dataclass(frozen=True)
class RecordOverride:
    action_id: str


@dataclass(frozen=True)
class Dismiss:
    action_id: str


CorrectionAction = Union[
    WaitForResult,
    RequestModelProposal,
    AskTeacher,
    PresentPreview,
    CommitCorrection,
    RecordOverride,
    Dismiss,
    Abstain,
    Error,
]


def _candidates(events: list[Event]) -> list[dict]:
    seen: dict[str, dict] = {}
    for e in events:
        if e.type == "ModelProposalReturned":
            for c in e.payload["candidates"]:
                key = codec.digest([c.get("rule"), c.get("selector")])
                seen.setdefault(key, {"key": key, **c})
    return list(seen.values())


def _exceptions(c: dict, items: list[EvidenceItem]) -> frozenset[tuple[str, str]]:
    """Per-label exceptions a conflict set would need: only the labels whose approved output the candidate changes."""
    out = set()
    for i in items:
        new = run_output(c["rule"], i.scene) or {}
        out |= {(i.scene_id, k) for k, v in (i.output or {}).items() if new.get(k) != v}
    return frozenset(out)


def _admissible(c: dict, d: Draft) -> Optional[dict]:
    """The candidate with its conflict set, or None when it must never be shown to the user."""
    try:
        validate_rule(c["rule"])
        parse_selector(c["selector"])
        if any(_forbidden_effect(c["rule"], sc) for sc in d.scenes.values()):
            return None
        if not item_fits(c["rule"], d.corrective)[0]:
            return None
        conflicts = [i.id for i in d.base_items if not item_fits(c["rule"], i)[0]]
        exceptions = _exceptions(c, [i for i in d.base_items if i.id in conflicts])
        diff = behaviour_diff(
            d.base["program"]["rule"], c["rule"], d.scenes, c["selector"], exceptions
        )
    except (RuleError, SelectorError, KeyError, TypeError):
        return None
    if diff["unexplained"]:
        return None
    return {**c, "conflicts": conflicts, "diff": diff}


def _size_key(c: dict) -> tuple[int, str]:
    return (len(codec.dumps(c["rule"])), c["key"])


def correction_step(events: list[Event], config: CorrectionConfig) -> CorrectionAction:
    if any(e.type in TERMINAL for e in events):
        return WaitForResult("terminal")
    for e in events:
        if e.type == "ModelCallFailed" and e.payload.get("terminal"):
            return Error(_aid(events, "Error"), f"provider: {e.payload['reason']}")
    if any(e.type == "CorrectionAbandoned" for e in events):
        return Abstain(
            _aid(events, "Abstain"), "correction abandoned; the active version is unchanged"
        )
    issued = [e.payload["action_id"] for e in events if e.type == "ActionIssued"]
    done = {
        e.payload.get("action_id")
        for e in events
        if e.type in ("ModelProposalReturned", "ModelCallFailed")
    }
    req_actions = {e.payload["action_id"] for e in events if e.type == "RequestIssued"}
    answered = {e.payload["response"]["request_id"] for e in events if e.type == "ResponseRecorded"}
    open_requests = [
        e
        for e in events
        if e.type == "RequestIssued" and e.payload["request"]["request_id"] not in answered
    ]
    outstanding = [a for a in issued if a not in done and a not in req_actions]
    if outstanding or open_requests:
        return WaitForResult(
            outstanding[0] if outstanding else open_requests[0].payload["action_id"]
        )

    d = derive_draft(events)
    if d.override:
        return RecordOverride(_aid(events, "RecordOverride"))
    if d.dismissed:
        return Dismiss(_aid(events, "Dismiss"))
    if d.cancelled:
        return Abstain(
            _aid(events, "Abstain"), "correction cancelled; the active version is unchanged"
        )
    if not d.rounds:
        return RequestModelProposal(_aid(events, "RequestModelProposal"), "scope")

    cands = [a for c in _candidates(events) if (a := _admissible(c, d)) is not None]
    can_revise = "revision" not in d.rounds and d.attempts < config.max_attempts
    if d.authorized is None:
        if (not cands or d.none_answered) and can_revise:
            return RequestModelProposal(_aid(events, "RequestModelProposal"), "revision")
        if d.none_answered:
            return Abstain(
                _aid(events, "Abstain"),
                "no acceptable interpretation; the active version is unchanged",
            )
        if d.clarifications >= config.max_clarifications:
            return Abstain(_aid(events, "Abstain"), "clarification budget exhausted")
        return _ask_scope(events, d, cands)

    selector = d.authorized["selector"]
    inside = [
        c
        for c in cands
        if all(members(c["selector"], sc) == members(selector, sc) for sc in d.scenes.values())
        and all(item_fits(c["rule"], i)[0] for i in d.chosen_outputs + d.rejected_items)
    ]
    if not inside:
        return Abstain(_aid(events, "Abstain"), "no program fits the authorized scope")
    for sid in sorted(d.scenes):
        groups = _groups(inside, d.scenes[sid])
        if len(groups) >= 2:
            if _usable(groups) and d.clarifications < config.max_clarifications:
                alts = tuple((chr(65 + k), out) for k, (out, _) in enumerate(groups))
                aid = _aid(events, "AskTeacher")
                return AskTeacher(aid, ChooseOutput(f"q-{aid}", sid, d.scene_hashes[sid], alts))
            return Abstain(
                _aid(events, "Abstain"), "unresolved disagreement inside the authorized scope"
            )
    sel = min(inside, key=_size_key)

    pending = [i for i in d.base_items if i.id in sel["conflicts"] and i.id not in d.superseded]
    if pending and not d.affected_used:
        if len(pending) > config.max_affected:
            return Abstain(_aid(events, "Abstain"), "too many affected examples to review")
        aid = _aid(events, "PresentPreview")
        items = tuple(
            (
                i.id,
                i.scene_id,
                d.scene_hashes.get(i.scene_id, codec.digest(i.scene)),
                run_output(sel["rule"], i.scene) or {},
            )
            for i in pending
        )
        return PresentPreview(
            aid, ConfirmPreview(f"p-{aid}", "affected_examples", items), sel["key"]
        )
    if pending:
        return Abstain(
            _aid(events, "Abstain"),
            "an affected example was not approved; the active version is unchanged",
        )

    if not d.revision_preview_used:
        base_rule = d.base["program"]["rule"]
        others = [s for s in sorted(d.scenes) if s != d.corrective.scene_id]
        changed = [
            s
            for s in others
            if run_output(base_rule, d.scenes[s]) != run_output(sel["rule"], d.scenes[s])
        ]
        same = [s for s in others if s not in changed]
        chosen = (changed[:1] + same[:1] + changed[1:] + same[1:])[: config.max_revision_preview]
        if not chosen:
            return Abstain(
                _aid(events, "Abstain"), "no document available for the revision preview"
            )
        aid = _aid(events, "PresentPreview")
        items = tuple(
            (f"r{k}", s, d.scene_hashes[s], run_output(sel["rule"], d.scenes[s]) or {})
            for k, s in enumerate(chosen)
        )
        return PresentPreview(
            aid, ConfirmPreview(f"p-{aid}", "revision_preview", items), sel["key"]
        )

    items_all = draft_items(d)
    misses = [i.id for i in items_all if not item_fits(sel["rule"], i)[0]]
    active_after = [i for i in d.base_items if i.id not in d.superseded]
    approved = frozenset(
        (v["scene_id"], lid) for v in d.superseded.values() for lid in v["changed_labels"]
    )
    diff = behaviour_diff(
        d.base["program"]["rule"], sel["rule"], d.scenes, sel["selector"], approved
    )
    report = retention_report(
        sel["rule"], active_after, d.superseded, d.replacements, diff, len(d.scenes)
    )
    if not d.preview_items:
        return Abstain(
            _aid(events, "Abstain"),
            "revision preview not approved; the active version is unchanged",
        )
    if misses or report["scope_violations"] or report["unexplained_regressions"]:
        return Abstain(
            _aid(events, "Abstain"),
            f"checks failed ({misses[:3]}); the active version is unchanged",
        )
    base = d.base
    artifact = {
        "skill_id": base["skill_id"],
        "parent_version": base["version"],
        "program": {
            "rule": sel["rule"],
            "summary": sel.get("summary", ""),
            "selector": sel["selector"],
        },
        "evidence": [item_to_json(i) for i in items_all],
        "superseded": d.superseded,
        "retention_report": report,
    }
    return CommitCorrection(
        _aid(events, "CommitCorrection"),
        sel["rule"],
        sel.get("summary", ""),
        sel["selector"],
        artifact,
    )


def _ask_scope(events: list[Event], d: Draft, cands: list[dict]) -> AskTeacher:
    revise: list[dict] = []
    for c in sorted(cands, key=_size_key):
        sig = tuple(
            sorted((sid, tuple(sorted(members(c["selector"], sc)))) for sid, sc in d.scenes.items())
        )
        if all(sig != r["sig"] for r in revise):
            revise.append({**c, "sig": sig})
        if len(revise) == 2:
            break
    cid = d.corrective.scene_id
    extra = None
    if len(revise) == 2:
        extra = next(
            (
                s
                for s in sorted(d.scenes)
                if s != cid
                and run_output(revise[0]["rule"], d.scenes[s])
                != run_output(revise[1]["rule"], d.scenes[s])
            ),
            None,
        )
    interps = []
    for k, c in enumerate(revise):
        shown = [cid] + ([extra] if extra else [])
        cons = tuple(
            (s, d.scene_hashes[s], run_output(c["rule"], d.scenes[s]) or {}) for s in shown
        )
        interps.append(Interpretation(f"r{k}", "revise", c["selector"], c.get("summary", ""), cons))
    interps.append(
        Interpretation("ov", "override", None, "Keep this edit on this document only", ())
    )
    interps.append(Interpretation("ac", "accidental", None, "That edit was a mistake", ()))
    aid = _aid(events, "AskTeacher")
    return AskTeacher(aid, ConfirmCorrectionScope(f"c-{aid}", tuple(interps)))
