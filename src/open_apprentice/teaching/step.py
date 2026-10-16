"""Pure learning policy: step(events, config) -> Action. Deterministic; never calls the model, the browser, storage or
the teacher. Spec section 4. Plan 1 searches batch documents only; generated probes arrive in Plan 4."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional, Union

from open_apprentice.concepts.hypotheses import fits
from open_apprentice.concepts.label_teaching import magic_condition
from open_apprentice.concepts.rules import (
    RuleError,
    evaluate_rule,
    evaluate_rule_counted,
    validate_rule,
)
from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import Evidence, derive
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.teacher import (
    SEPARATION,
    ChooseOutput,
    ConfirmPreview,
    Output,
    Request,
    max_error,
    request_from_json,
    response_from_json,
)


@dataclass(frozen=True)
class StepConfig:
    max_choose: int = 3
    max_previews: int = 1
    max_preview_items: int = 3
    max_attempts: int = 8
    max_evaluations: int = 5_000_000


@dataclass(frozen=True)
class WaitForResult:
    action_id: str


@dataclass(frozen=True)
class RequestModelProposal:
    action_id: str
    round_kind: str
    feedback: tuple[str, ...] = ()


@dataclass(frozen=True)
class AskTeacher:
    action_id: str
    request: Request


@dataclass(frozen=True)
class PresentPreview:
    action_id: str
    request: ConfirmPreview
    program_hash: str


@dataclass(frozen=True)
class CommitVersion:
    action_id: str
    program_hash: str
    rule: list
    summary: str
    claim: str


@dataclass(frozen=True)
class Abstain:
    action_id: str
    reason: str


@dataclass(frozen=True)
class Error:
    action_id: str
    reason: str


Action = Union[
    WaitForResult, RequestModelProposal, AskTeacher, PresentPreview, CommitVersion, Abstain, Error
]
RESULT_TYPES = {"ModelProposalReturned", "ModelCallFailed", "VersionStored", "Abstained", "Errored"}


def _aid(events: list[Event], kind: str) -> str:
    """Stable action id: the action kind plus the committed history it was decided on."""
    head = events[-1].event_id if events else "root"
    return codec.digest({"kind": kind, "head": head, "n": len(events)})[:24]


def run_output_counted(rule: list, scene: dict) -> tuple[Optional[Output], int]:
    """The label output and the statements it cost (statements run before a failure still count)."""
    try:
        st, steps = evaluate_rule_counted(rule, scene["objects"], scene["canvas"])
    except RuleError as e:
        return None, int(getattr(e, "steps", 0))
    out = {
        o["id"]: (st[o["id"]]["x"], st[o["id"]]["y"])
        for o in scene["objects"]
        if o["kind"] == "label"
    }
    return out, steps


def run_output(rule: list, scene: dict) -> Optional[Output]:
    return run_output_counted(rule, scene)[0]


def _forbidden_effect(rule: list, scene: dict) -> bool:
    """Only label x/y may change: no resize, no node move, no created objects."""
    try:
        st = evaluate_rule(rule, scene["objects"], scene["canvas"])
    except RuleError:
        return False
    if set(st) - {o["id"] for o in scene["objects"]}:
        return True
    for o in scene["objects"]:
        s = st[o["id"]]
        if (s["w"], s["h"]) != (o["w"], o["h"]):
            return True
        if o["kind"] != "label" and (s["x"], s["y"]) != (o["x"], o["y"]):
            return True
    return False


def candidate_pool(events: list[Event]) -> list[dict]:
    seen: dict[str, dict] = {}
    for ev in events:
        if ev.type == "ModelProposalReturned":
            for c in ev.payload["candidates"]:
                h = codec.digest(c["rule"])
                seen.setdefault(
                    h,
                    {
                        "hash": h,
                        "rule": c["rule"],
                        "summary": c.get("summary", ""),
                        "text": c.get("text", ""),
                    },
                )
    return list(seen.values())


def _filter(pool: list[dict], ev: Evidence) -> tuple[list[dict], list[str]]:
    keep, feedback = [], []
    constraints = ev.positives + ev.negatives
    for c in pool:
        label = c["summary"][:60]
        try:
            validate_rule(c["rule"])
        except RuleError as e:
            feedback.append(f"{label} -- syntax/validation: {str(e)[:160]}")
            continue
        if magic_condition(c["rule"]):
            feedback.append(
                f"{label} -- inadmissible: compares a position, size or id with a constant"
            )
            continue
        bad = next((why for k in constraints for ok, why in [fits(c["rule"], k)] if not ok), None)
        if bad is not None:
            feedback.append(f"{label} -- evidence mismatch: {bad[:200]}")
            continue
        if any(run_output(c["rule"], sc) is None for sc in ev.scenes.values()):
            feedback.append(f"{label} -- runtime: fails on a registered document")
            continue
        if any(_forbidden_effect(c["rule"], sc) for sc in ev.scenes.values()):
            feedback.append(
                f"{label} -- forbidden effect: changes something other than label positions"
            )
            continue
        keep.append(c)
    return keep, feedback


def _groups(cands: list[dict], scene: dict) -> list[tuple[Output, list[dict]]]:
    groups: list[tuple[Output, list[dict]]] = []
    for c in cands:
        out = run_output(c["rule"], scene)
        for g in groups:
            if g[0] == out:
                g[1].append(c)
                break
        else:
            groups.append((out, [c]))
    return groups


def _usable(groups: list[tuple[Output, list[dict]]]) -> bool:
    if not 2 <= len(groups) <= 4:
        return False
    for (a, _), (b, _) in combinations(groups, 2):
        e = max_error(a, b)
        if e is None or e <= SEPARATION:
            return False
    return True


def _separated_pairs(groups: list[tuple[Output, list[dict]]], n: int) -> int:
    return n * (n - 1) // 2 - sum(len(g) * (len(g) - 1) // 2 for _, g in groups)


def _selected(cands: list[dict]) -> dict:
    return min(cands, key=lambda c: (len(codec.dumps(c["rule"])), c["hash"]))


def step(events: list[Event], config: StepConfig) -> Action:
    issued: dict[str, dict] = {}
    resolved: set[str] = set()
    rounds: list[str] = []
    attempts = 0
    stored = False
    if any(e.type in ("Abstained", "Errored") for e in events):
        return WaitForResult("terminal")
    for e in events:
        if e.type == "ActionIssued":
            issued[e.payload["action_id"]] = e.payload
            if e.payload["kind"] == "RequestModelProposal":
                rounds.append(e.payload.get("round_kind", "initial"))
                attempts += 1
        elif e.type in RESULT_TYPES and e.payload.get("action_id"):
            if e.type == "ModelCallFailed" and not e.payload.get("terminal"):
                attempts += (
                    1  # a retried attempt counts against the budget; the action is still open
                )
            else:
                resolved.add(e.payload["action_id"])
        if e.type == "ModelCallFailed" and e.payload.get("terminal"):
            return Error(_aid(events, "Error"), f"provider: {e.payload['reason']}")
        if e.type == "VersionStored":
            stored = True

    requests = {
        request_from_json(e.payload["request"]).request_id: e.payload["action_id"]
        for e in events
        if e.type == "RequestIssued"
    }
    answered = {
        response_from_json(e.payload["response"]).request_id
        for e in events
        if e.type == "ResponseRecorded"
    }
    pending_requests = [rid for rid in requests if rid not in answered]
    outstanding = [a for a in issued if a not in resolved and a not in requests.values()]
    if pending_requests or outstanding:
        return WaitForResult(outstanding[0] if outstanding else requests[pending_requests[0]])
    if stored:
        return WaitForResult("done")

    ev = derive(events)

    # rule 1: no proposals yet
    if not rounds:
        return RequestModelProposal(_aid(events, "RequestModelProposal"), "initial")

    pool = candidate_pool(events)
    cands, feedback = _filter(pool, ev)

    # rule 2: empty pool -> one contradiction revision per cycle, then abstain
    if not cands:
        if "revision" not in rounds and attempts < config.max_attempts:
            return RequestModelProposal(
                _aid(events, "RequestModelProposal"), "revision", tuple(feedback[-8:])
            )
        return Abstain(
            _aid(events, "Abstain"), "no acceptable program found within the search limits"
        )

    # rule 3: disagreement search over batch documents (generated probes: Plan 4)
    chooses = [
        request_from_json(e.payload["request"])
        for e in events
        if e.type == "RequestIssued" and e.payload["request"]["type"] == "ChooseOutput"
    ]
    asked_scenes = {q.scene_id for q in chooses if isinstance(q, ChooseOutput)}
    best: Optional[tuple[tuple[int, int], str, list[tuple[Output, list[dict]]]]] = None
    disagreement_found = False
    if len(cands) >= 2:
        for i, sid in enumerate(sorted(ev.batch)):
            if sid in ev.approved:
                continue
            groups = _groups(cands, ev.scenes[sid])
            if len(groups) >= 2:
                disagreement_found = True
            if not _usable(groups) or sid in asked_scenes:
                continue
            score = (-_separated_pairs(groups, len(cands)), i)
            if best is None or score < best[0]:
                best = (score, sid, groups)
    if best is not None:
        if len(chooses) >= config.max_choose:
            return Abstain(_aid(events, "Abstain"), "unresolved disagreement")
        _, sid, groups = best
        alts = tuple((chr(65 + k), out) for k, (out, _) in enumerate(groups))
        aid = _aid(events, "AskTeacher")
        return AskTeacher(aid, ChooseOutput(f"q-{aid}", sid, ev.scene_hashes[sid], alts))
    if disagreement_found:
        if "contrastive" not in rounds and attempts < config.max_attempts:
            return RequestModelProposal(_aid(events, "RequestModelProposal"), "contrastive")
        return Abstain(_aid(events, "Abstain"), "unresolved disagreement")

    # rule 4: one program, or no disagreement found: one contrastive round per cycle
    if "contrastive" not in rounds and attempts < config.max_attempts:
        return RequestModelProposal(_aid(events, "RequestModelProposal"), "contrastive")

    # rule 6: commit, preview, or abstain
    sel = _selected(cands)
    approvals = [
        sid
        for sid in ev.batch
        if sid in ev.preview_approved
        and run_output(sel["rule"], ev.scenes[sid]) == ev.preview_approved[sid]
    ]
    unresolved_reject = any(
        run_output(sel["rule"], ev.scenes[s]) in outs for s, outs in ev.rejected.items()
    )
    previews_used = sum(
        1
        for e in events
        if e.type == "RequestIssued" and e.payload["request"]["type"] == "ConfirmPreview"
    )
    if approvals and not unresolved_reject:
        claim = (
            f"consistent with all evidence; approved on {len(approvals)} previewed document(s); "
            f"no distinguishing alternative found over {len(ev.batch)} searched document(s)"
        )
        return CommitVersion(
            _aid(events, "CommitVersion"), sel["hash"], sel["rule"], sel["summary"], claim
        )
    unlabelled = [s for s in sorted(ev.batch) if s not in ev.approved and s not in ev.rejected]
    if previews_used < config.max_previews and unlabelled:

        def moves(sid: str) -> int:
            out = run_output(sel["rule"], ev.scenes[sid]) or {}
            return sum(
                1
                for o in ev.scenes[sid]["objects"]
                if o["id"] in out and out[o["id"]] != (o["x"], o["y"])
            )

        chosen = sorted(unlabelled, key=lambda s: (-moves(s), s))[: config.max_preview_items]
        aid = _aid(events, "PresentPreview")
        items = tuple(
            (f"i{k}", s, ev.scene_hashes[s], run_output(sel["rule"], ev.scenes[s]) or {})
            for k, s in enumerate(chosen)
        )
        return PresentPreview(
            aid, ConfirmPreview(f"p-{aid}", "learning_preview", items), sel["hash"]
        )
    return Abstain(
        _aid(events, "Abstain"), "preview rejected" if unresolved_reject else "no approved preview"
    )
