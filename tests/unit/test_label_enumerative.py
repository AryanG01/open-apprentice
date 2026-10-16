from open_apprentice.concepts.label_enumerative import LabelEnumerator
from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.concepts.rules import evaluate_rule

SCENE = {
    "objects": [
        {"id": "n1", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
        {
            "id": "n2",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": 0,
            "y": 200,
            "w": 100,
            "h": 50,
        },
        {
            "id": "l1",
            "kind": "label",
            "role": "note",
            "attached": "n1",
            "x": 0,
            "y": 60,
            "w": 40,
            "h": 20,
        },
        {
            "id": "l2",
            "kind": "label",
            "role": "warning",
            "attached": "n2",
            "x": 0,
            "y": 260,
            "w": 40,
            "h": 20,
        },
    ],
    "canvas": {"w": 600, "h": 400},
}
BASE = parse_rule_text(
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n'
    "    move o to (a.x + a.w + 12, a.y + (a.h - o.h) / 2)\n  }\n}"
)


def evidence(moves):
    item = {"evidence": "demonstration", "scene": SCENE, "labels_moved_to": moves}
    return {"teaching_evidence": [item]}


def pos(out, lid):
    return (out[lid]["x"], out[lid]["y"])


def test_right_side_gap_twelve_is_found_and_fits():
    cands, usage, cost = LabelEnumerator().propose(
        evidence({"l1": [112, 15], "l2": [112, 215]}), "initial", ()
    )
    assert cost == 0 and cands and len(cands) <= 4 and usage["source"] == "label_enumerative"
    for c in cands:
        out = evaluate_rule(c["rule"], SCENE["objects"], SCENE["canvas"])
        assert pos(out, "l1") == (112, 15) and pos(out, "l2") == (112, 215)
    assert any("a.x + a.w + 12" in c["text"] for c in cands)


def test_role_scoped_candidate_when_only_notes_move():
    cands, _, _ = LabelEnumerator().propose(evidence({"l1": [112, 15]}), "initial", ())
    assert any('o.role == "note"' in c["text"] for c in cands)
    for c in cands:
        out = evaluate_rule(c["rule"], SCENE["objects"], SCENE["canvas"])
        assert "l2" not in out or pos(out, "l2") == (0, 260)


def test_nothing_fits_returns_empty_not_wrong():
    cands, _, _ = LabelEnumerator().propose(evidence({"l1": [333, 7]}), "initial", ())
    assert cands == []


def test_contrastive_round_returns_different_candidates():
    ev = evidence({"l1": [112, 15], "l2": [112, 215]})
    first, _, _ = LabelEnumerator().propose(ev, "initial", ())
    more, _, _ = LabelEnumerator().propose(ev, "contrastive", ())
    assert not {c["text"] for c in first} & {c["text"] for c in more}


def test_scope_proposals_keep_base_behaviour_outside_the_selector():
    ev = {
        "base_program": {"rule": BASE},
        "corrected_scene_objects": SCENE["objects"],
        "canvas": SCENE["canvas"],
        "corrected_output": {"l2": [0, 260]},  # the warning label goes back where it was
        "corrected_labels": ["l2"],
    }
    cands, _, cost = LabelEnumerator().propose_scope(ev, "scope")
    assert cost == 0 and cands
    assert {c["selector"] for c in cands} >= {'o.role == "warning"'}
    for c in cands:
        out = evaluate_rule(c["rule"], SCENE["objects"], SCENE["canvas"])
        assert pos(out, "l2") == (0, 260)
        if c["selector"] == 'o.role == "warning"':
            assert pos(out, "l1") == (112, 15)  # the note keeps the base behaviour
