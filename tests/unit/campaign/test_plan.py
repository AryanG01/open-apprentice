import json
from fractions import Fraction

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.layout_rule import LayoutOutcome, Target
from open_apprentice.campaign.plan import plan_from_layout
from open_apprentice.campaign.procedures import APPLY_PLAN, APPLY_TOOLS, plan_inputs
from open_apprentice.skills.interpreter import validate_program


def taught_outcome() -> LayoutOutcome:
    """The teaching target written out by hand from teach_after (what the learner must produce in Task 4)."""
    after = {n["id"]: n for n in load_fixture("teach_after")["scene"]["nodes"]}
    out = LayoutOutcome()
    for nid, n in after.items():
        if n["type"] == "artboard":
            continue
        t = Target(nid, x=Fraction(str(n["x"])), y=Fraction(str(n["y"])), z=n.get("z"))
        if n["type"] != "group":
            t.w, t.h = Fraction(str(n["width"])), Fraction(str(n["height"]))
        t.parent = n["parent"] if n["parent"] == "story-1" else None
        t.contain = n["type"] == "image"
        t.font_size = Fraction(str(n["fontSize"])) if n["type"] == "text" else None
        t.corner_radius = Fraction(str(n["cornerRadius"])) if n["type"] == "shape" else None
        out.targets[nid] = t
    return out


def test_apply_plan_is_a_valid_restricted_program():
    validate_program(APPLY_PLAN, APPLY_TOOLS)


def test_plan_inputs_are_json_and_cover_every_target():
    src = load_fixture("teach_before")["scene"]
    plan = plan_from_layout(taught_outcome(), src, "banner", origin="search")
    inputs = plan_inputs(plan)
    json.dumps(inputs)
    assert inputs["source_artboard"] == "banner"
    assert [a["artboard_id"] for a in inputs["artboards"]] == ["story-1"]
    moved = {m["node_id"] for m in inputs["moves"]} | {c["node_id"] for c in inputs["contains"]}
    assert moved == set(taught_outcome().targets)
    assert {r["parent_id"] for r in inputs["reparents"]} == {"story-1"}
    assert "tb-cta-plate" not in {
        i for r in inputs["reparents"] for i in r["node_ids"]
    }  # stays inside its CTA group
    assert {"node_id": "tb-cta-plate", "style": {"cornerRadius": 16.0}} in inputs["styles"]
