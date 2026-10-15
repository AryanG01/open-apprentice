from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.teaching import codec
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.step import (
    Abstain,
    AskTeacher,
    CommitVersion,
    Error,
    PresentPreview,
    RequestModelProposal,
    StepConfig,
    WaitForResult,
    run_output,
    step,
)
from open_apprentice.teaching.teacher import Response, request_to_json, response_to_json

# A scene where "right" and "right else below" differ: n1 sits where l0's right-hand spot would be.
BLOCKED = {
    "objects": [
        {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
        {
            "id": "n1",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": 120,
            "y": 0,
            "w": 60,
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
    ],
    "canvas": {"w": 600, "h": 400},
}
CLEAR = {"objects": [o for o in BLOCKED["objects"] if o["id"] != "n1"], "canvas": BLOCKED["canvas"]}
RIGHT = rule_for_spec(Spec("right", None, "all", F(12)))
FALLBACK = rule_for_spec(Spec("right", "below", "all", F(12)))
CFG = StepConfig()


class Log:
    def __init__(self):
        self.evs: list[Event] = []

    def add(self, t, payload, origin="system"):
        n = len(self.evs) + 1
        self.evs.append(Event(f"e{n}", f"e{n-1}" if n > 1 else None, n, t, origin, payload))


def registered(log, sid, scene, role):
    log.add(
        "SceneRegistered",
        {
            "scene_id": sid,
            "scene_hash": codec.digest(scene),
            "scene": codec.loads(codec.dumps(scene)),
            "role": role,
        },
    )


def demo(log):
    registered(log, "d", CLEAR, "demo")
    out = run_output(RIGHT, CLEAR)
    log.add(
        "DemonstrationRecorded", {"scene_id": "d", "output": codec.loads(codec.dumps(out))}, "human"
    )


def issue_proposal(log, a):
    log.add(
        "ActionIssued",
        {"action_id": a.action_id, "kind": "RequestModelProposal", "round_kind": a.round_kind},
    )


def proposals(log, rules, kind="initial"):
    a = step(log.evs, CFG)
    assert isinstance(a, RequestModelProposal) and a.round_kind == kind
    issue_proposal(log, a)
    log.add(
        "ModelProposalReturned",
        {
            "action_id": a.action_id,
            "usage": {},
            "candidates": [{"rule": r, "summary": s, "text": ""} for r, s in rules],
        },
        "model",
    )


def through_contrastive(log):
    a = step(log.evs, CFG)
    if isinstance(a, RequestModelProposal):
        assert a.round_kind == "contrastive"
        issue_proposal(log, a)
        log.add(
            "ModelProposalReturned",
            {"action_id": a.action_id, "usage": {}, "candidates": []},
            "model",
        )
        a = step(log.evs, CFG)
    return a


def test_first_action_is_initial_proposal_and_waits_while_outstanding():
    log = Log()
    demo(log)
    a = step(log.evs, CFG)
    assert isinstance(a, RequestModelProposal) and a.round_kind == "initial"
    issue_proposal(log, a)
    assert isinstance(step(log.evs, CFG), WaitForResult)


def test_disagreement_on_batch_asks_choose_output():
    log = Log()
    demo(log)
    registered(log, "b1", BLOCKED, "batch")
    proposals(log, [(RIGHT, "right"), (FALLBACK, "fallback")])
    a = step(log.evs, CFG)
    assert (
        isinstance(a, AskTeacher)
        and a.request.scene_id == "b1"
        and len(a.request.alternatives) == 2
    )


def test_indistinguishable_candidates_go_to_preview_and_both_survive():
    log = Log()
    demo(log)
    registered(log, "b1", CLEAR, "batch")  # right and fallback agree here
    proposals(log, [(RIGHT, "right"), (FALLBACK, "fallback")])
    a = through_contrastive(log)
    assert isinstance(a, PresentPreview)
    assert a.request.purpose == "learning_preview" and [i[1] for i in a.request.items] == ["b1"]
    from open_apprentice.teaching.constraints import derive
    from open_apprentice.teaching.step import _filter, candidate_pool

    survivors, _ = _filter(candidate_pool(log.evs), derive(log.evs))
    assert len(survivors) == 2  # equivalent on the searched set is not interchangeable


def test_runtime_failure_rejects_candidate_without_crashing():
    bad = [
        {
            "op": "for_each",
            "var": "o",
            "over": {"ref": "objects"},
            "body": [
                {
                    "op": "emit_target",
                    "kind": "move_existing",
                    "target": {"ref": "locals.o"},
                    "x": {"op": "div", "args": [1, 0]},
                    "y": 0,
                }
            ],
        }
    ]
    log = Log()
    demo(log)
    registered(log, "b1", CLEAR, "batch")
    proposals(log, [(bad, "broken"), (RIGHT, "right")])
    assert not isinstance(step(log.evs, CFG), Abstain)


def test_approved_preview_commits_exactly_once_and_replay_commits_nothing_more():
    log = Log()
    demo(log)
    registered(log, "b1", CLEAR, "batch")
    proposals(log, [(RIGHT, "right")])
    a = through_contrastive(log)
    assert isinstance(a, PresentPreview)
    log.add("ActionIssued", {"action_id": a.action_id, "kind": "PresentPreview"})
    log.add("RequestIssued", {"request": request_to_json(a.request), "action_id": a.action_id})
    item = a.request.items[0][0]
    r = Response(a.request.request_id, "items", per_item=((item, "approve"),))
    log.add("ResponseRecorded", {"response": response_to_json(r)}, "simulator")
    c = step(log.evs, CFG)
    assert isinstance(c, CommitVersion)
    log.add("ActionIssued", {"action_id": c.action_id, "kind": "CommitVersion"})
    log.add("VersionStored", {"action_id": c.action_id, "program_hash": c.program_hash})
    assert not isinstance(step(log.evs, CFG), CommitVersion)


def test_no_candidates_after_revision_abstains_with_search_limit_wording():
    log = Log()
    demo(log)
    registered(log, "b1", CLEAR, "batch")
    proposals(log, [])
    proposals(log, [], kind="revision")
    a = step(log.evs, CFG)
    assert isinstance(a, Abstain) and "within the search limits" in a.reason


def test_provider_failure_terminal_is_error_not_abstain():
    log = Log()
    demo(log)
    a = step(log.evs, CFG)
    issue_proposal(log, a)
    log.add(
        "ModelCallFailed", {"action_id": a.action_id, "reason": "TruncatedOutput", "terminal": True}
    )
    assert isinstance(step(log.evs, CFG), Error)
