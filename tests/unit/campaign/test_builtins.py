import asyncio
import copy

import pytest

from open_apprentice.campaign.builtins import BUILTINS, ORIGIN, shrink_hero, split_two_cards
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.layout_rule import evaluate_layout, objects_for_rule, wrap_learned
from open_apprentice.campaign.learn import learn_layout
from open_apprentice.campaign.plan import plan_from_layout
from open_apprentice.evaluation.campaign_gold import load_gold


def _base(fid):
    learned = asyncio.run(
        learn_layout(load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"])
    )
    src = load_fixture(fid)["scene"]
    out = evaluate_layout(
        wrap_learned(learned.rule),
        objects_for_rule(src, "banner"),
        {"output_format": "9:16", "overflows": False},
    )
    return plan_from_layout(out, src, "banner", origin=learned.origin)


def _gold_boxes(fid, outcome):
    boxes = {}
    for n in load_gold(fid, outcome)["scene"]["nodes"]:
        if n["type"] in ("artboard", "group"):
            if n["type"] == "group":
                boxes[n["id"]] = (n["x"], n["y"], n["parent"])
            continue
        boxes[n["id"]] = (n["x"], n["y"], n["width"], n["height"], n["parent"])
    return boxes


def _plan_boxes(plan, gold):
    out = {}
    for t in plan.targets:
        parent = t.parent or gold[t.node_id][-1]  # CTA children keep their group
        out[t.node_id] = (
            (t.x, t.y, parent) if plan.kinds[t.node_id] == "group" else (t.x, t.y, t.w, t.h, parent)
        )
    return out


@pytest.mark.parametrize("fid", ["de_long_a", "fr_long"])
def test_shrink_matches_the_gold(fid):
    gold = _gold_boxes(fid, "shrink")
    plan = shrink_hero(_base(fid))
    assert _plan_boxes(plan, gold) == gold
    assert plan.origin == ORIGIN == "builtin"


@pytest.mark.parametrize("fid", ["de_long_a", "de_long_b", "fr_long"])
def test_split_matches_the_gold(fid):
    gold = _gold_boxes(fid, "split")
    plan = split_two_cards(_base(fid))
    assert _plan_boxes(plan, gold) == gold
    assert [(a["id"], a["sequence"], a["x"]) for a in plan.artboards] == [
        ("story-1", 1, 0),
        ("story-2", 2, 1180),
    ]
    assert plan.origin == "builtin"


def test_split_restacks_each_card_from_zero():
    plan = split_two_cards(_base("de_long_a"))
    for card in ("story-1", "story-2"):
        zs = sorted(t.z for t in plan.targets if t.parent == card and t.z is not None)
        assert zs == list(range(len(zs))), card


def test_builtins_do_not_mutate_their_input():
    base = _base("de_long_a")
    snapshot = copy.deepcopy(base)
    shrink_hero(base)
    split_two_cards(base)
    assert base == snapshot


def test_builtin_names_match_the_rule_dialect():
    from open_apprentice.concepts.rules import ASK_OPTIONS

    assert BUILTINS == ASK_OPTIONS
