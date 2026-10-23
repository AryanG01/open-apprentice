import asyncio
import copy
from fractions import Fraction

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


def test_model_candidate_with_its_own_ask_is_rejected():
    rule = copy.deepcopy(_learn().rule)
    rule[0]["body"].append(
        {
            "op": "if",
            "cond": {
                "op": "eq",
                "args": [{"op": "get", "args": [{"ref": "locals.o"}, "role"]}, "x"],
            },
            "then": [{"op": "ask", "options": ["builtin_shrink_hero", "builtin_split_two_cards"]}],
        }
    )
    model = [
        c for c in _learn(provider=_model(rule), ledger=_ledger()).candidates if c.origin == "model"
    ][0]
    assert not model.reproduces and "built in" in model.reason


def test_model_candidate_with_different_stacking_is_rejected():
    rule = copy.deepcopy(_learn().rule)
    _emit_for(rule, "headline")["z"] = 0
    model = [
        c for c in _learn(provider=_model(rule), ledger=_ledger()).candidates if c.origin == "model"
    ][0]
    assert not model.reproduces and "stacking" in model.reason


# One teaching pair, two readings of the product image: the same frame every time, or scaled like the example.
from open_apprentice.campaign.learn import interpretations, probe_banner  # noqa: E402


def _product_box(rule, scene):
    objs = objects_for_rule(scene, "banner")
    out = evaluate_layout(wrap_learned(rule), objs, FACTS)
    pid = next(o["id"] for o in objs if o["role"] == "product_image")
    t = out.targets[pid]
    return (t.x, t.y, t.w, t.h)


def test_both_readings_reproduce_the_teaching_pair_exactly():
    readings = interpretations(_scene("teach_before"), _scene("teach_after"))
    assert set(readings) == {"fixed", "relative"}
    taught = _product_box(readings["fixed"], _scene("teach_before"))
    assert _product_box(readings["relative"], _scene("teach_before")) == taught
    for rule in readings.values():  # and every other role is placed identically
        assert _boxes_after(rule, _scene("teach_before")) == _boxes_after(
            readings["fixed"], _scene("teach_before")
        )


def _boxes_after(rule, scene):
    objs = objects_for_rule(scene, "banner")
    out = evaluate_layout(wrap_learned(rule), objs, FACTS)
    return {t.node_id: (t.x, t.y, t.w, t.h) for t in out.targets.values()}


def test_the_probe_banner_is_where_the_readings_disagree():
    before = _scene("teach_before")
    readings = interpretations(before, _scene("teach_after"))
    probe = probe_banner(before)
    fixed, rel = (_product_box(readings[k], probe) for k in ("fixed", "relative"))
    assert fixed != rel
    assert (
        rel[2] < fixed[2] and rel[3] < fixed[3]
    )  # a smaller photo stays smaller under the scaled reading
    cx = lambda b: b[0] + b[2] / 2  # noqa: E731
    assert cx(rel) == cx(fixed)  # both keep the taught centre
    assert before == _scene("teach_before")  # the teaching banner itself is not modified


def test_the_relative_reading_scales_by_the_taught_factor():
    before, after = _scene("teach_before"), _scene("teach_after")
    rel = interpretations(before, after)["relative"]
    src = next(n for n in _scene("short_a")["nodes"] if n.get("role") == "product_image")
    taught_src = next(n for n in before["nodes"] if n.get("role") == "product_image")
    taught_out = next(n for n in after["nodes"] if n.get("role") == "product_image")
    k = Fraction(str(taught_out["width"])) / Fraction(str(taught_src["width"]))
    assert _product_box(rel, _scene("short_a"))[2] == Fraction(str(src["width"])) * k


def test_learning_defaults_to_the_fixed_reading_and_can_take_the_other():
    assert _learn().rule == interpretations(_scene("teach_before"), _scene("teach_after"))["fixed"]
    rel = _learn(interpretation="relative")
    assert rel.interpretation == "relative" and rel.origin == "search"
    assert rel.rule == interpretations(_scene("teach_before"), _scene("teach_after"))["relative"]


def test_a_learned_rule_reads_as_one_row_per_role():
    from open_apprentice.campaign.learn import describe

    readings = interpretations(_scene("teach_before"), _scene("teach_after"))
    fixed = {r["role"]: r for r in describe(readings["fixed"])}
    rel = {r["role"]: r for r in describe(readings["relative"])}
    assert (
        fixed["product_image"]["size"] == "720 × 720" and "scaled" in rel["product_image"]["size"]
    )
    assert rel["headline"] == fixed["headline"]
    assert any(s.startswith("font") for s in fixed["headline"]["style"])
