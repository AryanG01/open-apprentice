from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.teaching import codec
from open_apprentice.teaching.correction_step import (
    CommitCorrection,
    CorrectionConfig,
    Dismiss,
    RecordOverride,
    correction_step,
)
from open_apprentice.teaching.corrections import derive_draft
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.evidence import EvidenceItem, item_to_json
from open_apprentice.teaching.step import (
    Abstain,
    AskTeacher,
    PresentPreview,
    RequestModelProposal,
    run_output,
)
from open_apprentice.teaching.teacher import Response, request_to_json, response_to_json

SCENE = {
    "objects": [
        {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
        {
            "id": "n1",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": 0,
            "y": 200,
            "w": 100,
            "h": 50,
        },
        {
            "id": "n2",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": 300,
            "y": 0,
            "w": 100,
            "h": 50,
        },
        {
            "id": "l0",
            "kind": "label",
            "role": "note",
            "attached": "n0",
            "x": 0,
            "y": 60,
            "w": 40,
            "h": 20,
        },
        {
            "id": "l1",
            "kind": "label",
            "role": "warning",
            "attached": "n1",
            "x": 0,
            "y": 260,
            "w": 40,
            "h": 20,
        },
        {
            "id": "l2",
            "kind": "label",
            "role": "warning",
            "attached": "n2",
            "x": 300,
            "y": 60,
            "w": 40,
            "h": 20,
        },
    ],
    "canvas": {"w": 600, "h": 400},
}
OTHER = {
    "objects": [o for o in SCENE["objects"] if o["id"] not in ("n2", "l2")],
    "canvas": SCENE["canvas"],
}
BASE = rule_for_spec(Spec("right", None, "all", F(12)))
NOTES = rule_for_spec(Spec("right", None, "notes", F(12)))
CFG = CorrectionConfig()


class Log:
    def __init__(self):
        self.evs = []

    def add(self, t, payload, origin="system"):
        n = len(self.evs) + 1
        self.evs.append(Event(f"e{n}", f"e{n-1}" if n > 1 else None, n, t, origin, payload))


def scene_json(sc):
    return codec.loads(codec.dumps(sc))


def started(log, base_items):
    base = {
        "skill_id": "k",
        "version": 1,
        "program": {"rule": BASE, "summary": "right"},
        "evidence": [item_to_json(i) for i in base_items],
        "superseded": {},
    }
    log.add(
        "CorrectionStarted",
        {
            "skill_id": "k",
            "base_version": 1,
            "base_pointer_generation": 1,
            "base_artifact": codec.loads(codec.dumps(base)),
            "scene_id": "c",
            "scene": scene_json(SCENE),
            "scene_hash": codec.digest(SCENE),
            "corrected_output": {"l1": [0, 260]},
            "mask": ["l1"],
            "full_approval": False,
        },
        "human",
    )
    for sid, sc in (("o1", OTHER),):
        log.add(
            "SceneRegistered",
            {
                "scene_id": sid,
                "scene_hash": codec.digest(sc),
                "scene": scene_json(sc),
                "role": "batch",
            },
        )


def propose(log, cands, kind="scope"):
    a = correction_step(log.evs, CFG)
    assert isinstance(a, RequestModelProposal) and a.round_kind == kind, a
    log.add(
        "ActionIssued",
        {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": kind},
    )
    log.add(
        "ModelProposalReturned",
        {"action_id": a.action_id, "usage": {}, "candidates": cands},
        "model",
    )


def answer(log, action, resp):
    log.add("ActionIssued", {"action_id": action.action_id, "kind": type(action).__name__})
    log.add(
        "RequestIssued", {"request": request_to_json(action.request), "action_id": action.action_id}
    )
    log.add("ResponseRecorded", {"response": response_to_json(resp)}, "simulator")


def base_items():
    return [EvidenceItem("b1", "full", "o1", OTHER, output=run_output(BASE, OTHER))]


WARN = {"rule": NOTES, "selector": 'o.role == "warning"', "summary": "warnings stay below"}


def select_revise(log):
    a = correction_step(log.evs, CFG)
    assert isinstance(a, AskTeacher) and type(a.request).__name__ == "ConfirmCorrectionScope"
    revise = next(i.interp_id for i in a.request.interpretations if i.kind == "revise")
    answer(log, a, Response(a.request.request_id, "select", selected=revise))


def test_scope_affected_and_revision_preview_complete_within_budget():
    log = Log()
    started(log, base_items())
    propose(log, [WARN])
    select_revise(log)
    b = correction_step(log.evs, CFG)  # base item b1 (warning l1 to the right on o1) now conflicts
    assert isinstance(b, PresentPreview) and b.request.purpose == "affected_examples"
    answer(
        log,
        b,
        Response(
            b.request.request_id,
            "items",
            per_item=tuple((i[0], "approve") for i in b.request.items),
        ),
    )
    c = correction_step(log.evs, CFG)
    assert isinstance(c, PresentPreview) and c.request.purpose == "revision_preview"
    answer(
        log,
        c,
        Response(
            c.request.request_id,
            "items",
            per_item=tuple((i[0], "approve") for i in c.request.items),
        ),
    )
    d = correction_step(log.evs, CFG)
    assert isinstance(d, CommitCorrection), d
    rep = d.artifact["retention_report"]
    assert rep["scope_violations"] == [] and rep["unexplained_regressions"] == []
    assert list(d.artifact["superseded"]) == ["b1"]
    assert derive_draft(log.evs).clarifications == 1


def test_scope_violating_interpretation_is_never_shown():
    log = Log()
    started(log, base_items())
    propose(
        log,
        [
            {
                "rule": NOTES,
                "selector": 'o.role == "note"',
                "summary": "claims notes but moves warnings",
            }
        ],
    )
    a = correction_step(log.evs, CFG)
    if isinstance(a, RequestModelProposal):
        propose(log, [], kind="revision")
        a = correction_step(log.evs, CFG)
    assert isinstance(a, AskTeacher)
    assert all(
        i.kind != "revise" for i in a.request.interpretations
    )  # only override / accidental remain


def test_cancel_after_affected_approval_leaves_base_untouched():
    log = Log()
    started(log, base_items())
    propose(log, [WARN])
    select_revise(log)
    b = correction_step(log.evs, CFG)
    answer(
        log,
        b,
        Response(
            b.request.request_id,
            "items",
            per_item=tuple((i[0], "approve") for i in b.request.items),
        ),
    )
    c = correction_step(log.evs, CFG)
    answer(
        log,
        c,
        Response(
            c.request.request_id, "items", per_item=tuple((i[0], "unsure") for i in c.request.items)
        ),
    )
    assert isinstance(correction_step(log.evs, CFG), Abstain)
    assert [e["id"] for e in log.evs[0].payload["base_artifact"]["evidence"]] == ["b1"]


def test_override_and_accidental_are_not_learning():
    for kind, expected in (("override", RecordOverride), ("accidental", Dismiss)):
        log = Log()
        started(log, base_items())
        propose(log, [])
        a = correction_step(log.evs, CFG)
        if isinstance(a, RequestModelProposal):  # revision round for the empty pool
            propose(log, [], kind="revision")
            a = correction_step(log.evs, CFG)
        pick = next(i.interp_id for i in a.request.interpretations if i.kind == kind)
        answer(log, a, Response(a.request.request_id, "select", selected=pick))
        assert isinstance(correction_step(log.evs, CFG), expected)
