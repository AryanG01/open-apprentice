from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.teaching import codec
from open_apprentice.teaching.step import (
    Abstain,
    AskTeacher,
    CommitVersion,
    RenderProbe,
    StepConfig,
    run_output,
    step,
)
from tests.unit.teaching.test_step import Log, issue_proposal, registered

RIGHT = parse_rule_text(
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n    move o to (a.x + a.w + 12, a.y)\n  }\n}'
)
FIXED = parse_rule_text(
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n    move o to (200, a.y)\n  }\n}'
)


def scene(node_y):
    return {
        "objects": [
            {
                "id": "n1",
                "kind": "node",
                "role": "",
                "attached": "",
                "x": 88,
                "y": node_y,
                "w": 100,
                "h": 50,
            },
            {
                "id": "l1",
                "kind": "label",
                "role": "note",
                "attached": "n1",
                "x": 0,
                "y": node_y + 60,
                "w": 40,
                "h": 14,
            },
        ],
        "canvas": {"w": 600, "h": 400},
    }


DEMO, BATCH = scene(40), scene(200)  # both rules put the label at x = 200 on both documents
ON = StepConfig(probes=True)


def started():
    log = Log()
    registered(log, "d", DEMO, "demo")
    registered(log, "b", BATCH, "batch")
    log.add(
        "DemonstrationRecorded",
        {"scene_id": "d", "output": codec.loads(codec.dumps(run_output(RIGHT, DEMO)))},
        "human",
    )
    a = step(log.evs, ON)
    issue_proposal(log, a)
    log.add("ModelProposalReturned", {"action_id": a.action_id, "usage": {},
            "candidates": [{"rule": RIGHT, "summary": "right", "text": ""}, {"rule": FIXED, "summary": "fixed", "text": ""}]}, "model")  # fmt: skip
    return log


def to_render(log, cfg=ON):
    for _ in range(4):  # the contrastive round (no new candidates) may come first
        a = step(log.evs, cfg)
        if isinstance(a, RenderProbe) or not hasattr(a, "round_kind"):
            return a
        issue_proposal(log, a)
        log.add(
            "ModelProposalReturned",
            {"action_id": a.action_id, "usage": {}, "candidates": []},
            "model",
        )
    return a


def rendered(log, a, ok=True):
    log.add(
        "ActionIssued",
        {"action_id": a.action_id, "kind": "RenderProbe", "probe_id": a.probe.probe_id},
    )
    if ok:
        registered(log, f"probe:{a.probe.probe_id}", a.probe.scene, "probe")
        log.add(
            "ProbeRendered",
            {
                "action_id": a.action_id,
                "probe_id": a.probe.probe_id,
                "ok": True,
                "scene_id": f"probe:{a.probe.probe_id}",
            },
        )
    else:
        log.add(
            "ProbeRendered",
            {
                "action_id": a.action_id,
                "probe_id": a.probe.probe_id,
                "ok": False,
                "reason": "measured geometry differs by 3",
            },
        )


def test_rules_that_agree_on_every_document_lead_to_a_rendered_probe():
    a = to_render(started())
    assert isinstance(a, RenderProbe) and a.probe.source_scene_id in ("d", "b")


def test_an_accepted_probe_is_asked_about():
    log = started()
    a = to_render(log)
    rendered(log, a)
    q = step(log.evs, ON)
    assert isinstance(q, AskTeacher) and q.request.scene_id == f"probe:{a.probe.probe_id}"


def test_a_failed_probe_is_never_asked_about_and_the_next_is_tried():
    log = started()
    a = to_render(log)
    rendered(log, a, ok=False)
    b = step(log.evs, ON)
    assert not (isinstance(b, AskTeacher) and b.request.scene_id == f"probe:{a.probe.probe_id}")
    assert not isinstance(b, RenderProbe) or b.probe.probe_id != a.probe.probe_id


def test_budget_exhaustion_abstains_and_never_commits():
    cfg = StepConfig(probes=True, max_evaluations=1)
    a = to_render(started(), cfg)
    assert isinstance(a, Abstain) and "budget_exhausted" in a.reason
    assert not isinstance(a, CommitVersion)


def test_probes_off_keeps_the_old_behaviour():
    log = started()
    for _ in range(4):
        a = step(log.evs, StepConfig())
        assert not isinstance(a, RenderProbe)
        if not hasattr(a, "round_kind"):
            break
        issue_proposal(log, a)
        log.add(
            "ModelProposalReturned",
            {"action_id": a.action_id, "usage": {}, "candidates": []},
            "model",
        )


def test_spent_question_budget_with_separable_rules_abstains_not_previews_or_commits():
    # the batch documents cannot separate the rules, a probe could, but no question may be asked any more (spec 4 rule 5)
    cfg = StepConfig(probes=True, max_choose=0)
    log = started()
    for _ in range(4):
        a = step(log.evs, cfg)
        if not hasattr(a, "round_kind"):
            break
        issue_proposal(log, a)
        log.add(
            "ModelProposalReturned",
            {"action_id": a.action_id, "usage": {}, "candidates": []},
            "model",
        )
    assert isinstance(a, Abstain) and a.reason == "unresolved disagreement", a
