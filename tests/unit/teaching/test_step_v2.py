from dataclasses import replace
from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.providers.base import TruncatedOutput
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.executor import Executor
from open_apprentice.teaching.step import Abstain, RequestModelProposal, StepConfig, step
from tests.unit.teaching.test_executor import ApprovingTeacher, start
from tests.unit.teaching.test_step import CLEAR, Log, demo, issue_proposal, proposals, registered

WRONG = rule_for_spec(
    Spec("below", None, "all", F(40))
)  # contradicts the demonstration (labels go right)


def _empty_round(log, cfg, kind):
    a = step(log.evs, cfg)
    assert isinstance(a, RequestModelProposal) and a.round_kind == kind, a
    issue_proposal(log, a)
    log.add(
        "ModelProposalReturned", {"action_id": a.action_id, "usage": {}, "candidates": []}, "model"
    )


def _log_with_a_rejected_proposal():
    log = Log()
    demo(log)
    registered(log, "b1", CLEAR, "batch")
    proposals(log, [(WRONG, "wrong")])  # rejected by the evidence: the pool is empty
    return log


def test_default_allows_one_revision_and_then_abstains():
    cfg = StepConfig()
    log = _log_with_a_rejected_proposal()
    _empty_round(log, cfg, "revision")
    assert isinstance(step(log.evs, cfg), Abstain)


def test_extra_revisions_are_asked_up_to_the_limit_and_then_it_abstains():
    cfg = StepConfig(max_revisions=3)
    log = _log_with_a_rejected_proposal()
    for _ in range(3):
        _empty_round(log, cfg, "revision")
    a = step(log.evs, cfg)
    assert isinstance(a, Abstain) and "no acceptable program" in a.reason


def test_extra_revisions_never_exceed_the_attempt_budget():
    cfg = StepConfig(max_revisions=10, max_attempts=3)
    log = _log_with_a_rejected_proposal()  # attempt 1
    _empty_round(log, cfg, "revision")  # 2
    _empty_round(log, cfg, "revision")  # 3
    assert isinstance(step(log.evs, cfg), Abstain)


class Truncating:
    def propose(self, evidence, round_kind, feedback):
        raise TruncatedOutput("cut at the completion cap")


def test_a_double_truncation_is_a_recorded_empty_round_when_tolerated(tmp_path):
    store, log = start(tmp_path)
    cfg = StepConfig(tolerate_truncation=True, max_revisions=1)
    status = Executor(store, log, Truncating(), ApprovingTeacher(), Ledger(store, F(5)), cfg).run()
    assert (
        status == "abstained"
    )  # initial and revision rounds were both empty, nothing was invented
    rounds = [e for e in log.events() if e.type == "ModelProposalReturned"]
    assert [r.payload["usage"].get("truncated") for r in rounds] == [True, True]
    assert not any(e.type == "Errored" for e in log.events())


def test_without_the_flag_a_double_truncation_is_a_terminal_error_as_before(tmp_path):
    store, log = start(tmp_path)
    status = Executor(
        store, log, Truncating(), ApprovingTeacher(), Ledger(store, F(5)), StepConfig()
    ).run()
    assert status == "error"


def test_default_config_is_unchanged():
    assert (
        replace(StepConfig()) == StepConfig()
        and StepConfig().max_revisions == 1
        and not StepConfig().tolerate_truncation
    )
