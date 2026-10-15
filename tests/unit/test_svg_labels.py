"""Real-file label path: scene extraction, rule -> byte-exact patch, round trip, refusals."""

import pathlib
from fractions import Fraction as F

import pytest

from open_apprentice.evaluation.labels import Spec, check_after, oracle, rule_for_spec
from open_apprentice.svg.labels_io import LabelsNotApplicable, apply_rule_to_svg, scene_from_svg

D = pathlib.Path("src/open_apprentice/svg/samples")
FILES = ["pipeline", "crowded-services", "mixed-layout"]
SPECS = [
    Spec("right", None, "all", F(12)),
    Spec("right", "below", "all", F(12)),
    Spec("right", None, "notes", F(12)),
]


def test_scene_extraction_counts_boxes_and_labels_and_skips_the_background():
    sc, rep = scene_from_svg((D / "crowded-services.svg").read_text())
    assert (rep["nodes"], rep["labels"]) == (7, 7) and not rep["not_editable"]
    assert "bg" not in {o["id"] for o in sc["objects"]}
    assert {o["role"] for o in sc["objects"] if o["kind"] == "label"} == {"note", "warning"}


@pytest.mark.parametrize("name", FILES)
@pytest.mark.parametrize("spec", SPECS)
def test_rule_patch_changes_only_label_xy_and_round_trips_to_the_oracle(name, spec):
    text = (D / f"{name}.svg").read_text()
    out = apply_rule_to_svg(text, rule_for_spec(spec))
    assert out["result"].unrelated_byte_changes == 0
    assert {d["attribute"] for d in out["result"].diff} <= {"x", "y"}
    before = out["scene"]
    after, _ = scene_from_svg(out["text"])
    r = check_after(before, after, oracle(spec, before))
    assert r["intent"] and r["preservation"], r["problems"]


def test_the_conditional_rule_differs_from_the_plain_one_on_the_crowded_file():
    text = (D / "crowded-services.svg").read_text()
    plain = apply_rule_to_svg(text, rule_for_spec(SPECS[0]))["targets"]
    cond = apply_rule_to_svg(text, rule_for_spec(SPECS[1]))["targets"]
    assert plain != cond


def test_refuses_what_it_cannot_do_instead_of_guessing():
    text = (D / "pipeline.svg").read_text()
    with pytest.raises(LabelsNotApplicable):
        scene_from_svg(text.replace('data-for="n1"', 'data-for="nope"'))
    with pytest.raises(Exception):  # active content is rejected by the shared validator
        scene_from_svg(text.replace("<title>", "<script>1</script><title>"))
    bad = [
        {
            "op": "emit_target",
            "kind": "move_existing",
            "target": {"ref": "objects[0]"},
            "x": 1,
            "y": 1,
        }
    ]
    with pytest.raises(LabelsNotApplicable):  # moving a box is not this lane's job
        apply_rule_to_svg(text, bad)
