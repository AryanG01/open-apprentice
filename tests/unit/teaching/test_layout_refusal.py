from fractions import Fraction as F

import pytest

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.events import SessionLog
from open_apprentice.teaching.executor import Executor
from open_apprentice.teaching.layout import layout_problems
from open_apprentice.teaching.step import StepConfig, run_output
from tests.unit.teaching.test_executor import ApprovingTeacher

RIGHT = rule_for_spec(Spec("right", None, "all", F(12)))


def _node(i, x, y, w=100, h=50):
    return {"id": i, "kind": "node", "role": "", "attached": "", "x": x, "y": y, "w": w, "h": h}


def _label(i, n, x, y):
    return {
        "id": i,
        "kind": "label",
        "role": "note",
        "attached": n,
        "x": x,
        "y": y,
        "w": 40,
        "h": 20,
    }


EDGE = {
    "objects": [_node("n0", 540, 10, 50), _label("l0", "n0", 540, 70)],
    "canvas": {"w": 600, "h": 400},
}
CLEAR = {
    "objects": [_node("n0", 10, 10), _label("l0", "n0", 10, 70)],
    "canvas": {"w": 600, "h": 400},
}
CROWD = {
    "objects": [_node("n0", 10, 10), _node("n1", 125, 10), _label("l0", "n0", 10, 70)],
    "canvas": {"w": 600, "h": 400},
}


def test_layout_problems_name_the_document_and_label():
    assert layout_problems(RIGHT, {"d": EDGE}) == ["d: l0 leaves the page"]
    assert layout_problems(RIGHT, {"d": CROWD}) == ["d: l0 overlaps n1"]
    assert layout_problems(RIGHT, {"d": CLEAR}) == []


class Proposer:
    def propose(self, evidence, round_kind, feedback):
        return (
            ([{"rule": RIGHT, "summary": "right", "text": ""}] if round_kind == "initial" else []),
            {},
            F(0),
        )


def _log(tmp_path, demo):
    store = LocalStore(tmp_path)
    log = SessionLog(store, "s")
    log.create(owner="o")
    for sid, sc, role in (("d", demo, "demo"), ("b", CLEAR, "batch")):
        log.append("SceneRegistered", "system", {"scene_id": sid, "scene_hash": codec.digest(sc),
                   "scene": codec.loads(codec.dumps(sc)), "role": role})  # fmt: skip
    out = codec.loads(codec.dumps(run_output(RIGHT, demo)))
    log.append("DemonstrationRecorded", "human", {"scene_id": "d", "output": out})
    return store, log


@pytest.mark.parametrize("demo,status", [(EDGE, "abstained"), (CLEAR, "committed")])
def test_a_convention_that_leaves_the_page_is_refused_before_any_preview(tmp_path, demo, status):
    store, log = _log(tmp_path, demo)
    t = ApprovingTeacher()
    got = Executor(store, log, Proposer(), t, Ledger(store, F(5)), StepConfig()).run()
    assert got == status
    if status == "abstained":
        reason = next(e.payload["reason"] for e in log.events() if e.type == "Abstained")
        assert reason.startswith("refusing to apply") and "leaves the page" in reason
        assert t.asked == 0


def test_b_is_not_offered_commit_for_a_refused_rule(tmp_path):
    from open_apprentice.concepts.catalogue_programs import program_text
    from open_apprentice.learner.agent_b import AgentB, AgentBudgets

    store, log = _log(tmp_path, EDGE)
    b = AgentB(lambda: None, log, ApprovingTeacher(), Ledger(store, F(5)), AgentBudgets(), F(0))
    b.t_propose("p", {"rules_text": [program_text("right", None, "all", 12)]})
    assert "approve" in b.t_preview("v", {"doc_ids": ["b"], "program": "P1"})
    assert not any(o["id"].startswith("commit") for o in b.options())
    assert b.t_commit("c", {"program": "P1"}).startswith("refused: refusing to apply")


def test_a_correction_commit_runs_the_layout_check(monkeypatch):
    import open_apprentice.teaching.correction_step as cs
    from tests.unit.teaching.test_correction_step import (
        test_scope_affected_and_revision_preview_complete_within_budget,
    )

    monkeypatch.setattr(cs, "layout_problems", lambda rule, scenes: ["o1: l1 leaves the page"])
    with pytest.raises(AssertionError, match="refusing to apply"):
        test_scope_affected_and_revision_preview_complete_within_budget()


def test_b_is_told_when_a_program_would_be_refused_and_is_not_offered_its_preview(tmp_path):
    from open_apprentice.concepts.catalogue_programs import program_text
    from open_apprentice.learner.agent_b import AgentB, AgentBudgets

    store, log = _log(tmp_path, EDGE)
    b = AgentB(lambda: None, log, ApprovingTeacher(), Ledger(store, F(5)), AgentBudgets(), F(0))
    msg = b.t_propose("p", {"rules_text": [program_text("right", None, "all", 12)]})
    assert "refusing to apply" in msg and "leaves the page" in msg
    ids = {o["id"] for o in b.options()}
    assert not any(i.startswith(("preview", "commit")) for i in ids) and "abstain" in ids
    prog = b._state(8)["programs"][0]
    assert "leaves the page" in prog["layout_problem"]
