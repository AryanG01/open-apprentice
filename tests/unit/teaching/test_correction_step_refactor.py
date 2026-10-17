"""Plan 6 Task 5 safety net: the correction policy's action sequences on scripted scenarios, recorded from the code
before its request builders and commit predicate were factored out (OA_RECORD_TRACES=1 rewrites the fixture)."""

import json
import os
from pathlib import Path

import pytest

from open_apprentice.teaching.correction_step import correction_step
from open_apprentice.teaching.teacher import Response
from tests.unit.teaching.test_correction_step import (
    CFG,
    NOTES,
    WARN,
    Log,
    answer,
    base_items,
    started,
)

FIXTURE = Path(__file__).parent / "correction_traces.json"
WIDE = {"rule": NOTES, "selector": 'o.kind == "label"', "summary": "every label"}
SCENARIOS = {
    "revise_all_approved": ([[WARN]], "revise", "approve"),
    "revise_preview_unsure": ([[WARN]], "revise", "unsure"),
    "none_then_revision": ([[WARN], [WARN]], "none", "approve"),
    "override": ([[]], "override", "approve"),
    "accidental": ([[]], "accidental", "approve"),
    "two_candidates": ([[WARN, WIDE]], "revise", "approve"),
}


def _trace(rounds, scope_answer, preview_answer):
    log = Log()
    started(log, base_items())
    out, rounds = [], list(rounds)
    for _ in range(20):
        a = correction_step(log.evs, CFG)
        name = type(a).__name__
        req = getattr(a, "request", None)
        out.append([name, getattr(a, "round_kind", None), type(req).__name__ if req else None,
                    getattr(req, "purpose", None), getattr(a, "reason", None)])  # fmt: skip
        if name == "RequestModelProposal":
            cands = rounds.pop(0) if rounds else []
            log.add(
                "ActionIssued", {"action_id": a.action_id, "kind": name, "round_kind": a.round_kind}
            )
            log.add(
                "ModelProposalReturned",
                {"action_id": a.action_id, "usage": {}, "candidates": cands},
                "model",
            )
        elif name in ("AskTeacher", "PresentPreview"):
            t = type(req).__name__
            if t == "ConfirmCorrectionScope":
                pick = next(
                    (i.interp_id for i in req.interpretations if i.kind == scope_answer), None
                )
                resp = (
                    Response(req.request_id, "select", selected=pick)
                    if pick
                    else Response(req.request_id, "none")
                )
            elif t == "ChooseOutput":
                resp = Response(req.request_id, "choose", selected=req.alternatives[0][0])
            else:
                resp = Response(
                    req.request_id,
                    "items",
                    per_item=tuple((i[0], preview_answer) for i in req.items),
                )
            answer(log, a, resp)
        else:
            break
    return out


def test_correction_policy_actions_are_unchanged_by_the_refactor():
    got = {k: _trace(*v) for k, v in SCENARIOS.items()}
    if os.environ.get("OA_RECORD_TRACES") == "1":
        FIXTURE.write_text(json.dumps(got, indent=1))
        pytest.skip("recorded")
    assert got == json.loads(FIXTURE.read_text())
