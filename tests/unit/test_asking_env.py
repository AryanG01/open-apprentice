"""The 'calibrated asking' environment: an agent sees ONE demonstration of a hidden layout rule, may ask the teacher to show the
true outcome on a few new inputs, then commits a rule (closed text grammar) or abstains. Scoring is on separate components,
never one blended number, and the ambiguity label comes from the ENVIRONMENT (not from anything the agent proposes)."""

import pytest

from open_apprentice.evaluation.asking_env import MAX_ASKS, AskingEnv, ambiguity_label


@pytest.fixture(scope="module")
def ambiguous_badge():
    # development episode 0 is ambiguous for the badge concept: several simple rules fit its single demonstration
    return AskingEnv("development", seed=0, index=0, kind="badge")


def test_the_ambiguity_label_comes_from_the_environment_and_matches_the_measured_mix():
    labels = [
        ambiguity_label("development", 0, i, kind)
        for i in range(12)
        for kind in ("badge", "spacing")
    ]
    assert sum(labels) == 15 and len(labels) == 24  # measured: 12 of 12 badge, 3 of 12 spacing


def test_the_agent_sees_the_demonstration_but_never_the_hidden_rule(ambiguous_badge):
    obs = ambiguous_badge.observation()
    assert set(obs) >= {"demonstration", "tools", "rule_grammar"}
    assert "latent" not in str(obs).lower() and "ambiguous" not in str(obs).lower()
    assert ambiguous_badge.max_asks == MAX_ASKS


def test_asking_returns_the_true_outcome_and_is_counted_and_capped(ambiguous_badge):
    env = AskingEnv("development", seed=0, index=0, kind="badge")
    first = env.ask({"card_widths": [300]})
    assert first["ok"] and "after" in first and env.asks_used == 1
    for _ in range(MAX_ASKS - 1):
        assert env.ask({"card_widths": [200]})["ok"]
    over = env.ask({"card_widths": [100]})
    assert not over["ok"] and "limit" in over["error"] and env.asks_used == MAX_ASKS


def test_out_of_domain_questions_are_refused_not_answered():
    env = AskingEnv("development", seed=0, index=0, kind="badge")
    assert not env.ask({"card_widths": [5]})["ok"]
    assert not env.ask({"card_widths": [9999]})["ok"]
    assert env.asks_used == 0  # a refused question costs nothing


def test_committing_the_true_behaviour_scores_correct_and_separate_components(ambiguous_badge):
    env = AskingEnv("development", seed=0, index=0, kind="badge")
    env.ask({"card_widths": [300]})
    out = env.commit(env.hidden_rule())
    assert out["ok"]
    s = env.score()
    assert s["reward"] == s["components"]["correct"] == 1.0
    assert s["components"]["held_out"] == 1.0
    assert s["components"]["asking"] == 1.0  # ambiguous task, and it asked
    assert s["components"]["not_confidently_wrong"] == 1.0
    assert s["reward"] != sum(s["components"].values())  # the axes are reported, never blended


def test_a_confident_wrong_commit_on_an_ambiguous_task_is_flagged(ambiguous_badge):
    env = AskingEnv("development", seed=0, index=0, kind="badge")
    # several rules of the grammar fit the one demonstration; take one that is NOT the hidden rule's behaviour
    for cand in env.fitting_candidates():
        probe = AskingEnv("development", seed=0, index=0, kind="badge")
        probe.commit(cand.rule)
        if probe.score()["components"]["correct"] == 0.0:
            env.commit(cand.rule)
            break
    else:
        pytest.fail("expected a plausible but wrong candidate on an ambiguous demonstration")
    s = env.score()["components"]
    assert s["correct"] == 0.0 and s["asking"] == 0.0 and s["not_confidently_wrong"] == 0.0


def test_a_rule_written_as_text_is_parsed_and_scored():
    env = AskingEnv("development", seed=0, index=0, kind="badge")
    text = (
        "let m = 12\n"
        "clone objects[1] as badge at (objects[0].x + objects[0].w - m - objects[1].w, objects[0].y + m)"
    )
    assert env.commit(text)["ok"]
    s = env.score()
    assert s["committed"] and 0.0 <= s["components"]["held_out"] <= 1.0


def test_unparseable_rules_are_reported_and_can_be_retried_but_abstaining_scores_no_correctness():
    env = AskingEnv("development", seed=0, index=0, kind="badge")
    bad = env.commit("this is not a rule")
    assert not bad["ok"] and "error" in bad and not env.finished
    env.abstain()
    s = env.score()
    assert env.finished and s["reward"] == 0.0 and s["components"]["held_out"] == 0.0
    assert s["abstained"] is True


def test_an_unambiguous_task_should_be_answered_without_asking():
    idx = next(i for i in range(12) if not ambiguity_label("development", 0, i, "spacing"))
    env = AskingEnv("development", seed=0, index=idx, kind="spacing")
    env.commit(env.hidden_rule())
    assert env.score()["components"]["asking"] == 1.0  # needed no question and asked none
    asked = AskingEnv("development", seed=0, index=idx, kind="spacing")
    asked.ask({"card_widths": [100, 100, 100]})
    asked.commit(asked.hidden_rule())
    assert asked.score()["components"]["asking"] == 0.0  # a needless question is not calibrated
