"""Label-placement family: hand-calculated geometry, rule-vs-oracle agreement, and the independent checker's verdicts."""

from fractions import Fraction as F

import pytest

from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.evaluation.labels import (
    INTENTS,
    apply_oracle,
    check_after,
    intended_after,
    make_scene,
    overlaps,
    rule_for,
)

GAP = F(12)


def _scene(extra=()):
    # node 100..200 x 100..150; label 50x20 below it. canvas 1200x800.
    objs = [
        {
            "id": "n0",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": 100,
            "y": 100,
            "w": 100,
            "h": 50,
        },
        {
            "id": "l0",
            "kind": "label",
            "role": "note",
            "attached": "n0",
            "x": 100,
            "y": 154,
            "w": 50,
            "h": 20,
        },
        *extra,
    ]
    return {"objects": objs, "canvas": {"w": 1200, "h": 800}}


def test_right_pose_by_hand():
    # right: x = 100 + 100 + 12 = 212 ; y = 100 + (50 - 20)/2 = 115
    assert intended_after("right", GAP, _scene())["l0"] == (212, 115)


def test_conditional_branch_flips_exactly_at_the_overlap_threshold():
    # label would occupy x 212..262, y 115..135. A blocker starting at x=262 only TOUCHES it: still right.
    touching = {
        "id": "b",
        "kind": "node",
        "role": "",
        "attached": "",
        "x": 262,
        "y": 100,
        "w": 40,
        "h": 60,
    }
    assert intended_after("right_else_below", GAP, _scene([touching]))["l0"] == (212, 115)
    # starting 1 unit earlier gives positive-area overlap: falls back to below. x = 100 + (100-50)/2 = 125 ; y = 100+50+12
    overlapping = dict(touching, x=261)
    assert intended_after("right_else_below", GAP, _scene([overlapping]))["l0"] == (125, 162)


def test_off_canvas_right_pose_falls_back_below():
    s = _scene()
    s["objects"][0]["x"] = 1100  # right pose would need x 1212 > 1200
    s["objects"][1]["x"] = 1100
    assert intended_after("right_else_below", GAP, s)["l0"][1] == 162


def test_scope_intent_leaves_warnings_alone():
    s = _scene()
    s["objects"][1]["role"] = "warning"
    assert intended_after("notes_only", GAP, s) == {}


@pytest.mark.parametrize("intent", INTENTS)
@pytest.mark.parametrize("seed", range(25))
def test_the_rule_language_agrees_with_the_oracle(intent, seed):
    scene = make_scene(seed, n_nodes=3 + seed % 6, warnings=seed % 3)
    state = evaluate_rule(rule_for(intent, GAP), scene["objects"], scene["canvas"])
    want = intended_after(intent, GAP, scene)
    for o in scene["objects"]:
        moved = (state[o["id"]]["x"], state[o["id"]]["y"]) != (o["x"], o["y"])
        if o["id"] in want:
            assert (state[o["id"]]["x"], state[o["id"]]["y"]) == want[o["id"]], (
                intent,
                seed,
                o["id"],
            )
        else:
            assert not moved, (intent, seed, o["id"])


def test_the_family_actually_exercises_both_branches():
    flips = total = 0
    for seed in range(60):
        scene = make_scene(seed, n_nodes=10)
        right = intended_after("right", GAP, scene)
        cond = intended_after("right_else_below", GAP, scene)
        total += len(right)
        flips += sum(right[k] != cond[k] for k in right)
    assert 0.05 < flips / total < 0.7, (
        flips / total
    )  # enough scenes have a blocked label to select them by property; not all


def test_checker_reports_axes_separately_and_catches_each_failure():
    scene = _scene()
    want = intended_after("right", GAP, scene)
    good = apply_oracle(scene, want)
    assert all(check_after(scene, good, want)[k] for k in ("intent", "preservation", "layout"))
    # wrong place: intent fails, preservation still ok
    wrong = apply_oracle(scene, {"l0": (213, 115)})
    r = check_after(scene, wrong, want)
    assert not r["intent"] and r["preservation"]
    # a node nudged: preservation fails even though the label is right
    bumped = apply_oracle(scene, want)
    bumped["objects"][0]["x"] += 1
    assert not check_after(scene, bumped, want)["preservation"]
    # label resized: preservation fails
    resized = apply_oracle(scene, want)
    resized["objects"][1]["w"] = 51
    assert not check_after(scene, resized, want)["preservation"]
    # moved onto another object: layout fails
    blocker = {
        "id": "b",
        "kind": "node",
        "role": "",
        "attached": "",
        "x": 230,
        "y": 100,
        "w": 40,
        "h": 60,
    }
    s2 = _scene([blocker])
    r2 = check_after(s2, apply_oracle(s2, want), want)
    assert r2["intent"] and not r2["layout"]


def test_edge_contact_is_not_overlap():
    assert not overlaps((0, 0, 10, 10), (10, 0, 5, 5))
    assert overlaps((0, 0, 10, 10), (9, 0, 5, 5))
