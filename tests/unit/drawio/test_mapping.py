import pytest

from open_apprentice.drawio import mapping as mp
from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.render import parse_render
from tests.unit.drawio.fixtures import drawio, label, model, node

NODES = frozenset({"a", "b"})


def box(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def setup():
    cells = [node("a", 40, 40), node("b", 300, 40), label("l1", 180, 50), label("l2", 300, 100)]
    f = load_drawio(drawio(model(cells)))
    c = classify(f.pages[0])
    r = parse_render(
        {
            "labels": {
                "l1": {"box": box(182, 53, 20, 14), "lines": 1},
                "l2": {"box": box(302, 103, 20, 14), "lines": 1},
            },
            "nodes": {"a": {"state": box(40, 40, 120, 50)}, "b": {"state": box(300, 40, 120, 50)}},
        }
    )
    return f, c, r


def test_proposes_nearest_node_by_box_gap_with_role_note():
    f, c, r = setup()
    m = mp.propose(c, r, f.doc_hash)
    assert m.labels == {
        "l1": {"node_id": "a", "role": "note"},
        "l2": {"node_id": "b", "role": "note"},
    }
    assert m.proposed == {"l1", "l2"} and m.confirmed_by_event is None


def test_edit_lowercases_role_and_validates_node():
    f, c, r = setup()
    m = mp.edit(mp.propose(c, r, f.doc_hash), "l1", node_id="b", role=" Warning ", nodes=NODES)
    assert m.labels["l1"] == {"node_id": "b", "role": "warning"} and "l1" not in m.proposed
    with pytest.raises(ValueError):
        mp.edit(m, "l1", node_id="zzz", nodes=NODES)


def test_digest_changes_with_mapping_and_round_trips():
    f, c, r = setup()
    m = mp.confirm(mp.propose(c, r, f.doc_hash), "e7")
    assert mp.from_json(mp.to_json(m)) == m
    m2 = mp.edit(m, "l1", role="warning", nodes=NODES)
    assert mp.digest(m2) != mp.digest(m) and m2.confirmed_by_event is None


def test_scene_mapping_requires_confirmation_and_the_same_document():
    f, c, r = setup()
    m = mp.propose(c, r, f.doc_hash)
    with pytest.raises(DrawioRefused, match="confirmed"):
        mp.as_scene_mapping(m, f.doc_hash, f.pages[0].id, c.movable)
    m = mp.confirm(m, "e1")
    with pytest.raises(DrawioRefused, match="another document"):
        mp.as_scene_mapping(m, "0" * 64, f.pages[0].id, c.movable)
    assert mp.as_scene_mapping(m, f.doc_hash, f.pages[0].id, c.movable)["l1"] == ("a", "note")
