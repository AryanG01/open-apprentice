from fractions import Fraction as F

from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.teaching.probes import candidate_probes, search


def rule(text):
    return {"rule": parse_rule_text(text), "hash": text}


RIGHT = rule(
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n    move o to (a.x + a.w + 12, a.y)\n  }\n}'
)
FIXED = rule(
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n    move o to (200, a.y)\n  }\n}'
)

# node right edge at 188: "right of the node, gap 12" and "x = 200" agree here
SCENE = {
    "objects": [
        {
            "id": "n1",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": F(88),
            "y": F(40),
            "w": F(100),
            "h": F(50),
        },
        {
            "id": "l1",
            "kind": "label",
            "role": "note",
            "attached": "n1",
            "x": F(0),
            "y": F(100),
            "w": F(40),
            "h": F(14),
        },
        {
            "id": "n2",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": F(400),
            "y": F(300),
            "w": F(60),
            "h": F(40),
        },
    ],
    "canvas": {"w": F(600), "h": F(400)},
}


def probes():
    return candidate_probes({"b": SCENE}, {"b": "batch"}, [RIGHT, FIXED])


def test_node_resize_probe_separates_rules_that_agree_on_the_batch_document():
    s = search(probes(), [RIGHT, FIXED], budget=5_000_000)
    assert s.outcome == "found" and s.best is not None and len(s.groups) == 2
    changed = {cid for cid, _ in s.best.edits}
    assert s.best.source_scene_id == "b" and len(changed) == 1
    before = {o["id"]: o for o in SCENE["objects"]}
    after = {o["id"]: o for o in s.best.scene["objects"]}
    assert all(
        after[k]["kind"] == before[k]["kind"] for k in before
    )  # nothing added, no text touched


def test_probes_stay_on_the_page_never_overlap_nodes_and_are_capped():
    ps = candidate_probes({"b": SCENE}, {"b": "batch"}, [RIGHT, FIXED], limit=3)
    assert len(ps) <= 3
    for p in probes():
        W, H = p.scene["canvas"]["w"], p.scene["canvas"]["h"]
        nodes = [o for o in p.scene["objects"] if o["kind"] == "node"]
        for o in p.scene["objects"]:
            assert o["x"] >= 0 and o["y"] >= 0 and o["x"] + o["w"] <= W and o["y"] + o["h"] <= H
        for i, a in enumerate(nodes):
            for b in nodes[i + 1 :]:
                assert not (
                    a["x"] < b["x"] + b["w"]
                    and b["x"] < a["x"] + a["w"]
                    and a["y"] < b["y"] + b["h"]
                    and b["y"] < a["y"] + a["h"]
                )


def test_budget_exhaustion_is_recorded_and_finds_nothing():
    s = search(probes(), [RIGHT, FIXED], budget=1)
    assert s.outcome == "budget_exhausted" and s.best is None


def test_identical_rules_complete_with_no_disagreement():
    s = search(probes(), [RIGHT, rule(RIGHT["hash"])], budget=5_000_000)
    assert s.outcome == "completed_no_disagreement" and s.best is None and s.statements > 0


def test_probe_ids_are_stable_and_families_are_known():
    a, b = probes(), probes()
    assert [p.probe_id for p in a] == [p.probe_id for p in b]
    assert {p.family for p in a} <= {"node_resize", "obstacle", "narrow_canvas"}
