"""The reward components must SEPARATE the scripted behaviours; otherwise the environment cannot tell good agents from bad ones."""

import pytest

from open_apprentice.evaluation.asking_baselines import POLICIES, run_policy
from open_apprentice.evaluation.asking_env import ambiguity_label


@pytest.fixture(scope="module")
def tasks():
    ambiguous = [i for i in range(12) if ambiguity_label("development", 0, i, "badge")]
    unamb = next(i for i in range(12) if not ambiguity_label("development", 0, i, "spacing"))
    # never_ask guesses the simplest fitting rule, which is sometimes right by luck: pick a task where it is wrong
    wrong = next(
        (
            i
            for i in ambiguous
            if run_policy("never_ask", "development", 0, i, "badge")["reward"] == 0.0
        ),
        None,
    )
    assert (
        wrong is not None
    ), "expected at least one ambiguous task where the unasked guess is wrong"
    return {"ambiguous": (wrong, "badge"), "unambiguous": (unamb, "spacing")}


def _c(policy, task):
    i, kind = task
    return run_policy(policy, "development", 0, i, kind)["components"]


def test_never_asking_is_confidently_wrong_when_the_demonstration_is_ambiguous(tasks):
    c = _c("never_ask", tasks["ambiguous"])
    assert c["asking"] == 0.0 and c["economy"] == 1.0
    assert c["correct"] == 0.0 and c["not_confidently_wrong"] == 0.0


def test_always_asking_is_penalised_for_needless_questions(tasks):
    c = _c("always_ask", tasks["unambiguous"])
    assert c["correct"] == 1.0 and c["asking"] == 0.0 and c["economy"] == 0.0


def test_calibrated_asking_is_correct_and_calibrated_on_both_kinds_of_task(tasks):
    for kind in ("ambiguous", "unambiguous"):
        c = _c("calibrated", tasks[kind])
        assert c["correct"] == 1.0 and c["asking"] == 1.0 and c["not_confidently_wrong"] == 1.0
    assert _c("calibrated", tasks["unambiguous"])["economy"] == 1.0


def test_abstaining_is_never_counted_as_correct(tasks):
    for kind in ("ambiguous", "unambiguous"):
        r = run_policy("always_abstain", "development", 0, *tasks[kind])
        assert r["reward"] == 0.0 and r["abstained"] and not r["committed"]


def test_every_policy_is_listed():
    assert set(POLICIES) == {"never_ask", "always_ask", "calibrated", "always_abstain"}
