from fractions import Fraction as F

from open_apprentice.concepts.hypotheses import Constraint, derived_relations, describe
from open_apprentice.concepts.rules import evaluate_rule
from tests.fixtures_rules import CONST_MARGIN, gap_rule

CANVAS = {"w": F(800), "h": F(600)}


def test_created_object_relations_expose_the_equal_right_and_top_gaps():
    objs = [
        {"id": "card0", "x": F(10), "y": F(340), "w": F(90), "h": F(40)},
        {"id": "proto", "x": F(0), "y": F(0), "w": F(20), "h": F(20)},
    ]
    c = Constraint(
        "positive",
        {"objects": objs, "canvas": CANVAS},
        evaluate_rule(CONST_MARGIN, objs, CANVAS),
        source="demonstration",
    )  # inset 12
    r = derived_relations(c)["created_objects_vs_each_existing_object"]
    to_card = [x for x in r if x["relative_to"] == "objects[0]"][0]
    assert (to_card["ref_right_minus_right_edge"], to_card["top_edge_minus_ref_top"]) == (12, 12)
    assert to_card["width_ratio_new_to_ref"] == F(2, 9)
    assert {x["relative_to"] for x in r} == {
        "objects[0]",
        "objects[1]",
    }  # symmetric: every existing object is a reference


def test_moved_row_relations_give_shifts_gaps_and_centre_distances():
    objs = [
        {"id": f"c{i}", "x": F(10 * i), "y": F(300), "w": F(w), "h": F(50)}
        for i, w in enumerate((100, 60, 40))
    ]
    c = Constraint(
        "positive",
        {"objects": objs, "canvas": CANVAS},
        evaluate_rule(gap_rule(24, 80, 120), objs, CANVAS),
        source="demonstration",
    )
    r = derived_relations(c)
    assert r["changes_to_existing_objects"]["objects[0]"] == {
        "dx": 80,
        "dy": -180,
        "dw": 0,
        "dh": 0,
    }
    assert [g["edge_gap"] for g in r["after_state_between_consecutive_objects"]] == [24, 24]
    # centres: 130 -> 234 -> 308, i.e. distances 104 and 74 (width/2 of both neighbours + gap)
    assert [g["center_distance_x"] for g in r["after_state_between_consecutive_objects"]] == [
        104,
        74,
    ]
    assert r["after_state_first_object"] == {"left": 80, "top": 120}


def test_digest_is_derived_from_public_geometry_only_and_present_in_the_prompt_payload():
    objs = [
        {"id": "card0", "x": F(0), "y": F(0), "w": F(100), "h": F(50)},
        {"id": "proto", "x": F(0), "y": F(0), "w": F(20), "h": F(20)},
    ]
    c = Constraint(
        "positive",
        {"objects": objs, "canvas": CANVAS},
        evaluate_rule(CONST_MARGIN, objs, CANVAS),
        source="demonstration",
    )
    import open_apprentice.concepts.hypotheses as H

    H.INCLUDE_RELATIONS = True
    try:
        d = describe([c])[0]
    finally:
        H.INCLUDE_RELATIONS = False
    assert (
        "derived_relations" in d
        and "latent" not in str(d).lower()
        and "template" not in str(d).lower()
    )
    neg = Constraint(
        "excludes", {"objects": objs, "canvas": CANVAS}, excluded=(c.expected,), source="neither"
    )
    assert "derived_relations" not in describe([neg])[0]


def test_relations_are_off_by_default_because_the_live_experiment_showed_no_benefit():
    objs = [
        {"id": "card0", "x": F(0), "y": F(0), "w": F(100), "h": F(50)},
        {"id": "proto", "x": F(0), "y": F(0), "w": F(20), "h": F(20)},
    ]
    c = Constraint(
        "positive",
        {"objects": objs, "canvas": CANVAS},
        evaluate_rule(CONST_MARGIN, objs, CANVAS),
        source="demonstration",
    )
    assert "derived_relations" not in describe([c])[0]
