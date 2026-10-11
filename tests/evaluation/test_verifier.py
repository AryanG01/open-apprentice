"""Verifier golden scenes and the six seeded faults of spec 12.4."""

import copy

import pytest

from open_apprentice.evaluation.verifier import VerifierInputError, verify_gap_row, world_bounds

TASK = {
    "canvas": {"width": 800, "height": 500},
    "selected_ids": ["a", "b", "c"],
    "parameters": {"gap_px": 24, "left_px": 80, "top_px": 120},
}


def node(i, x, y, w=50, h=40, parent=None, **kw):
    return {
        "id": i,
        "parent": parent,
        "type": "rect",
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "fill": "red",
        **kw,
    }


INITIAL = {
    "nodes": [
        node("a", 10, 300, 100),
        node("b", 200, 310, 60),
        node("c", 400, 320, 80),
        node("d", 600, 50),
    ]
}


def golden():
    f = copy.deepcopy(INITIAL)
    n = {x["id"]: x for x in f["nodes"]}
    n["a"].update(x=80, y=120)
    n["b"].update(x=80 + 100 + 24, y=120)
    n["c"].update(x=80 + 100 + 24 + 60 + 24, y=120)
    return f


def test_golden_passes():
    r = verify_gap_row(INITIAL, golden(), TASK)
    assert r.passed, r.failed()


def test_golden_nested_with_scaled_parent_passes():
    """Children live in a scaled+offset group; only world geometry counts."""
    init = {
        "nodes": [
            {
                "id": "g",
                "parent": None,
                "type": "group",
                "x": 40,
                "y": 20,
                "scaleX": 2.0,
                "scaleY": 2.0,
            },
            node("a", 0, 50, 50, 20, parent="g"),
            node("b", 100, 50, 30, 20, parent="g"),
            node("c", 200, 50, 40, 20, parent="g"),
        ]
    }
    # world widths: 100, 60, 80. Place world-left at 80 with gap 24 => local x = (world-40)/2.
    fin = copy.deepcopy(init)
    n = {x["id"]: x for x in fin["nodes"]}
    n["a"].update(x=(80 - 40) / 2, y=(120 - 20) / 2)
    n["b"].update(x=(80 + 100 + 24 - 40) / 2, y=(120 - 20) / 2)
    n["c"].update(x=(80 + 100 + 24 + 60 + 24 - 40) / 2, y=(120 - 20) / 2)
    assert verify_gap_row(init, fin, TASK).passed


def test_world_bounds_composes_parent_scale():
    s = {
        "nodes": [
            {"id": "g", "x": 10, "y": 10, "scaleX": 2, "scaleY": 3},
            node("r", 5, 5, 10, 10, parent="g"),
        ]
    }
    assert world_bounds(s)["r"] == (20.0, 25.0, 20.0, 30.0)


def _fail(fin, expect):
    r = verify_gap_row(INITIAL, fin, TASK)
    assert not r.passed and expect in r.failed(), (r.failed(), expect)


def test_fault_wrong_object_moved():
    f = golden()
    {x["id"]: x for x in f["nodes"]}["d"]["x"] += 40
    _fail(f, "no_unauthorized_move")


def test_fault_constant_offset_shift():
    f = golden()
    for x in f["nodes"]:
        if x["id"] in "abc":
            x["x"] += 5
    _fail(f, "left_edge_matches")


def test_fault_centers_preserved_widths_changed():
    f = golden()
    for x in f["nodes"]:
        if x["id"] == "b":
            x["x"] -= 10
            x["width"] += 20  # same center, wider
    _fail(f, "sizes_preserved")


def test_fault_duplicate_and_delete():
    dup = golden()
    dup["nodes"].append(copy.deepcopy(dup["nodes"][0]))
    _fail(dup, "objects_exist_exactly_once")
    gone = golden()
    gone["nodes"] = [x for x in gone["nodes"] if x["id"] != "c"]
    _fail(gone, "objects_exist_exactly_once")


def test_fault_parent_transform_with_misleading_local_coords():
    """Local coords look right, but wrapping in a shifted parent moves world geometry."""
    f = golden()
    for x in f["nodes"]:
        if x["id"] in "abc":
            x["parent"] = "g"
    f["nodes"].append({"id": "g", "parent": None, "type": "group", "x": 30, "y": 0})
    r = verify_gap_row(INITIAL, f, TASK)
    assert not r.passed


def test_fault_success_without_mutation():
    r = verify_gap_row(INITIAL, copy.deepcopy(INITIAL), TASK)
    assert not r.passed


def test_agent_measurement_cannot_change_truth():
    """The verifier takes only native scene state; a lying measure tool has no input path."""
    import inspect
    from open_apprentice.evaluation import verifier

    src = inspect.getsource(verifier)
    assert "measure_node" not in src.replace("`measure_node`", "").replace("(`measure_node`,", "")


def test_rotation_rejected_not_approximated():
    f = golden()
    f["nodes"][0]["rotation"] = 15
    with pytest.raises(VerifierInputError):
        verify_gap_row(INITIAL, f, TASK)
