import asyncio
import copy

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.layout_rule import evaluate_layout, objects_for_rule, wrap_learned
from open_apprentice.campaign.learn import learn_layout
from open_apprentice.campaign.scene import RoleError
from open_apprentice.evaluation.campaign_gold import load_gold
from open_apprentice.providers.mock import MockProvider

FACTS = {"output_format": "9:16", "overflows": False}


def _scene(fid):
    return load_fixture(fid)["scene"]


def _learn(**kw):
    return asyncio.run(learn_layout(_scene("teach_before"), _scene("teach_after"), **kw))


def _boxes(scene, board):
    return {o["role"]: (o["x"], o["y"], o["w"], o["h"]) for o in objects_for_rule(scene, board)}


def test_search_learning_reproduces_the_taught_story():
    learned = _learn()
    assert learned.origin == "search"
    out = evaluate_layout(
        wrap_learned(learned.rule), objects_for_rule(_scene("teach_before"), "banner"), FACTS
    )
    after = {n["id"]: n for n in _scene("teach_after")["nodes"]}
    for nid, t in out.targets.items():
        assert (t.x, t.y) == (after[nid]["x"], after[nid]["y"]), nid
    assert (
        out.targets["tb-head"].font_size == 72 and out.targets["tb-cta-plate"].corner_radius == 16
    )


def test_learned_rule_transfers_by_role_to_another_banner():
    learned = _learn()
    out = evaluate_layout(
        wrap_learned(learned.rule), objects_for_rule(_scene("short_a"), "banner"), FACTS
    )
    gold = {
        o["role"]: o for o in objects_for_rule(load_gold("short_a", "layout")["scene"], "story-1")
    }
    by_role = {o["role"]: o["id"] for o in objects_for_rule(_scene("short_a"), "banner")}
    for role, g in gold.items():
        t = out.targets[by_role[role]]
        assert (t.x, t.y) == (g["x"], g["y"]), role
        if role not in ("cta",):
            assert (t.w, t.h) == (g["w"], g["h"]), role


def _model(rule):
    return MockProvider(
        {"campaign_layout": [{"candidates": [{"rule": rule, "summary": "candidate"}]}]}
    )


def _ledger():
    return Ledger(Limits(tokens=500_000, calls=8))


def test_behaviourally_identical_model_candidate_is_reported_but_search_wins():
    rule = _learn().rule
    learned = _learn(provider=_model(rule), ledger=_ledger())
    assert learned.origin == "search"
    model = [c for c in learned.candidates if c.origin == "model"]
    assert len(model) == 1 and model[0].reproduces


def _emit_for(rule, role):
    for stmt in rule[0]["body"]:
        if stmt["cond"]["args"][1] == role:
            return stmt["then"][0]
    raise AssertionError(role)


def test_model_candidate_writing_text_is_rejected():
    rule = copy.deepcopy(_learn().rule)
    _emit_for(rule, "headline")["text"] = "Buy now"
    learned = _learn(provider=_model(rule), ledger=_ledger())
    model = [c for c in learned.candidates if c.origin == "model"][0]
    assert not model.reproduces and "properties" in model.reason


def test_model_candidate_off_by_four_pixels_is_rejected():
    rule = copy.deepcopy(_learn().rule)
    _emit_for(rule, "headline")["y"] += 4
    learned = _learn(provider=_model(rule), ledger=_ledger())
    model = [c for c in learned.candidates if c.origin == "model"][0]
    assert not model.reproduces and "headline" in model.reason


def test_missing_role_stops_before_any_model_call():
    provider = _model([])
    with pytest.raises(RoleError):
        asyncio.run(
            learn_layout(
                _scene("missing_role"), _scene("teach_after"), provider=provider, ledger=_ledger()
            )
        )
    assert provider.calls == []
