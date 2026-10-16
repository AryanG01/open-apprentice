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


def test_hand_placed_positions_within_tolerance_are_explained():
    # a person drags labels: positions are close to the rule's output (here off by 1/128 and by 0.3), never exact
    scene = {
        "objects": [
            {
                "id": "n1",
                "kind": "node",
                "role": "",
                "attached": "",
                "x": 300,
                "y": 400,
                "w": 100,
                "h": 50,
            },
            {
                "id": "l1",
                "kind": "label",
                "role": "note",
                "attached": "n1",
                "x": 0,
                "y": 0,
                "w": "4953/64",
                "h": 14,
            },
            {
                "id": "n2",
                "kind": "node",
                "role": "",
                "attached": "",
                "x": 0,
                "y": 0,
                "w": 120,
                "h": 50,
            },
            {
                "id": "l2",
                "kind": "label",
                "role": "note",
                "attached": "n2",
                "x": 0,
                "y": 100,
                "w": 40,
                "h": 14,
            },
        ],
        "canvas": {"w": 900, "h": 700},
    }
    exact_l1_x = 300 + (100 - 4953 / 64) / 2  # 311.3046875, a multiple of 1/128
    moves = {"l1": [str(round(exact_l1_x * 64) / 64), 458], "l2": [40.3, 58]}
    ev = {
        "teaching_evidence": [
            {"evidence": "demonstration", "scene": scene, "labels_moved_to": moves}
        ]
    }
    cands, _, _ = LabelEnumerator().propose(ev, "initial", ())
    assert any("a.y + a.h + 8" in c["text"] for c in cands), [c["summary"] for c in cands]


def test_near_identical_gaps_collapse_to_the_whole_unit_one():
    # measured positions are a hair off whole units; "gap 7.984375" and "gap 8" must not both survive (no question can
    # separate them, so the learner would stop with "unresolved disagreement")
    def obj(i, kind, attached, x, y, w, h):
        return {"id": i, "kind": kind, "role": "note" if kind == "label" else "", "attached": attached,
                "x": x, "y": y, "w": w, "h": h}  # fmt: skip

    scene = {
        "objects": [
            obj("n1", "node", "", 40, 57.5, 60, 50),
            obj("l1", "label", "n1", 0, 0, 30, 14),
            obj("n2", "node", "", 40, 207.5, 60, 50),
            obj("l2", "label", "n2", 0, 300, 30, 14),
        ],
        "canvas": {"w": 600, "h": 400},
    }
    # gap 8 puts l1 at (55, 115.5) and l2 at (55, 265.5); the measured positions are 1/64 off
    moves = {"l1": ["3521/64", "7391/64"], "l2": ["3521/64", "16991/64"]}
    ev = {
        "teaching_evidence": [
            {"evidence": "demonstration", "scene": scene, "labels_moved_to": moves}
        ]
    }
    cands, _, _ = LabelEnumerator().propose(ev, "initial", ())
    below = [c for c in cands if "a.y + a.h +" in c["text"] and "o.role" not in c["text"]]
    assert len(below) == 1 and "a.y + a.h + 8" in below[0]["text"], [c["summary"] for c in cands]
