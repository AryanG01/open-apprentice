from dataclasses import replace

from open_apprentice.teaching.step import AskTeacher, StepConfig, step
from tests.unit.teaching.test_step import BLOCKED, FALLBACK, RIGHT, Log, demo, proposals, registered

BLOCKED2 = {
    "objects": [dict(o, y=4) if o["id"] == "n1" else o for o in BLOCKED["objects"]],
    "canvas": BLOCKED["canvas"],
}


def _log():
    log = Log()
    demo(log)
    registered(log, "b1", BLOCKED, "batch")
    registered(log, "b2", BLOCKED2, "batch")
    proposals(log, [(RIGHT, "right"), (FALLBACK, "fallback")])
    return log


def test_best_is_the_default_and_reproduces_todays_choice():
    log = _log()
    a, b = step(log.evs, StepConfig()), step(log.evs, StepConfig(question_selection="best"))
    assert isinstance(a, AskTeacher) and a == b and a.request.scene_id == "b1"


def test_uniform_picks_each_usable_question_for_some_seed():
    log = _log()
    picked = {
        step(log.evs, StepConfig(question_selection="uniform", seed=s)).request.scene_id
        for s in range(24)
    }
    assert picked == {"b1", "b2"}


def test_uniform_is_deterministic_per_seed_and_log():
    log = _log()
    cfg = StepConfig(question_selection="uniform", seed=7)
    assert step(log.evs, cfg) == step(log.evs, replace(cfg))


def test_uniform_draws_among_legal_probes_when_no_document_separates():
    from tests.unit.teaching.test_step_probes import started, to_render

    picked = set()
    for s in range(16):
        a = to_render(started(), StepConfig(probes=True, question_selection="uniform", seed=s))
        picked.add(a.probe.probe_id)
    assert len(picked) >= 2
