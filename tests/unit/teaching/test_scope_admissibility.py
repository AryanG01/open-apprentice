from pathlib import Path

from open_apprentice.teaching.correction_step import correction_step
from open_apprentice.teaching.step import AskTeacher, RequestModelProposal
from tests.unit.teaching.test_correction_step import (
    CFG,
    NOTES,
    WARN,
    Log,
    base_items,
    propose,
    started,
)


def _first_scope_question(cands):
    log = Log()
    started(log, base_items())
    propose(log, cands)
    a = correction_step(log.evs, CFG)
    if isinstance(a, RequestModelProposal):
        propose(log, [], kind="revision")
        a = correction_step(log.evs, CFG)
    assert isinstance(a, AskTeacher)
    return {i.selector for i in a.request.interpretations if i.kind == "revise"}


def test_a_selector_comparing_node_size_with_a_constant_is_never_shown():
    magic = dict(WARN, selector='o.role == "warning" and object(o.attached).w == 100')
    assert _first_scope_question([magic]) == set()


def test_role_and_relational_selectors_stay_admissible():
    rel = dict(
        WARN, selector='o.role == "warning" and object(o.attached).w >= object(o.attached).h'
    )
    assert _first_scope_question([WARN]) == {WARN["selector"]}
    assert _first_scope_question([rel]) == {rel["selector"]}


def test_the_scope_prompt_asks_for_relations_not_fixed_numbers():
    text = Path("prompts/correction_scope.md").read_text()
    assert "w > 120" not in text and "rather than with fixed numbers" in text
    assert (
        "object(o.attached).w <= object(o.attached).h" not in text
    )  # the battery's template stays hidden


assert NOTES  # fixture import kept explicit
