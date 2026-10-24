"""Scoring for the banner-reading probe: roles, box overlap and words against the fixture's own layers."""

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.vision import Layer, LayerProposal
from open_apprentice.evaluation.campaign_vision_eval import (
    gold_layers,
    iou,
    norm,
    score_case,
    verdict,
)


def _proposal_from(gold, **shift):
    layers = []
    for role, g in gold.items():
        box = list(g["box"])
        box = [box[0] + shift.get("dx", 0), box[1], box[2], box[3]]
        layers.append(
            Layer(role=role, box=box, text=shift.get("text", g["text"]), font_px=g["font_px"] or 20)
        )
    return LayerProposal(layers, "en", "model")


def test_gold_layers_come_from_the_fixtures_own_nodes():
    g = gold_layers(load_fixture("short_a")["scene"])
    assert set(g) == {"brand_mark", "product_image", "headline", "price", "cta", "legal"}
    assert g["headline"]["text"] == "Hear only what matters." and g["cta"]["text"] == "Shop now"
    assert g["cta"]["box"][2:] == [256.0, 76.8]  # the button plate, not the group


def test_iou_and_text_normalisation():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [20, 20, 5, 5]) == 0.0
    assert abs(iou([0, 0, 10, 10], [5, 0, 10, 10]) - 1 / 3) < 1e-9
    assert norm("  Hear   only\nwhat matters. ") == "Hear only what matters."


def test_a_perfect_reading_scores_everything():
    g = gold_layers(load_fixture("short_a")["scene"])
    s = score_case(_proposal_from(g), g)
    assert s["roles_present"] and s["all_matched"] and s["text_exact"] == 4 and s["text_roles"] == 4
    assert min(s["iou"].values()) == 1.0


def test_a_shifted_or_misread_layer_is_counted_not_hidden():
    g = gold_layers(load_fixture("short_a")["scene"])
    s = score_case(_proposal_from(g, dx=400), g)
    assert s["roles_present"] and not s["all_matched"]
    assert score_case(_proposal_from(g, text="x"), g)["text_exact"] == 0
    missing = _proposal_from(g)
    missing.layers = [l for l in missing.layers if l.role != "legal"]
    m = score_case(missing, g)
    assert not m["roles_present"] and m["iou"]["legal"] == 0.0


def test_the_decision_follows_the_rule_set_before_the_run():
    g = gold_layers(load_fixture("short_a")["scene"])
    good = [score_case(_proposal_from(g), g)] * 6
    assert verdict(good)["decision"] == "go"
    shifted = [score_case(_proposal_from(g, dx=400), g)] * 6
    assert verdict(shifted)["decision"] == "partial"  # roles and words right, boxes wrong
    off = [score_case(_proposal_from(g, dx=400, text="x"), g)] * 6
    assert verdict(off)["decision"] == "no-go"
