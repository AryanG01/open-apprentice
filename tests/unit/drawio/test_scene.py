from fractions import Fraction as F

import pytest

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.render import parse_render, q64
from open_apprentice.drawio.scene import build_scene
from tests.unit.drawio.fixtures import drawio, label, model, node


def box(b):
    return dict(zip("xywh", b))


def setup(
    label_box=(52, 103, 30, 14),
    lines=1,
    node_state=(40, 40, 100, 50),
    element=(40, 40, 100, 50),
):
    c = classify(
        load_drawio(drawio(model([node("n1", 40, 40, 100, 50), label("l1", 50, 100)]))).pages[0]
    )
    r = parse_render(
        {
            "labels": {"l1": {"box": box(label_box), "lines": lines, "rects": 1}},
            "nodes": {"n1": {"state": box(node_state), "element": box(element), "stroke": 1}},
            "missing": [],
            "profile": {},
            "png": None,
            "svg": None,
        }
    )
    return c, r


def test_quantum_is_one_sixty_fourth():
    assert q64(10.016) == F(641, 64) and q64("3.3").denominator in (1, 2, 4, 8, 16, 32, 64)


def test_scene_uses_measured_boxes_and_stores_offsets():
    c, r = setup()
    s = build_scene(c, r, {"l1": ("n1", "note")}, "h")
    lab = next(o for o in s.scene["objects"] if o["id"] == "l1")
    assert (lab["kind"], lab["role"], lab["attached"]) == ("label", "note", "n1")
    assert (lab["x"], lab["y"], lab["w"], lab["h"]) == (52, 103, 30, 14)
    assert s.offsets["l1"] == (2, 3) and s.scene["canvas"] == {"w": 600, "h": 400}


def test_wrapped_label_is_demoted_to_obstacle_with_reason():
    c, r = setup(lines=2)
    s = build_scene(c, r, {"l1": ("n1", "note")}, "h")
    assert s.movable == () and "more than one line" in s.demoted["l1"]
    assert next(o for o in s.scene["objects"] if o["id"] == "l1")["kind"] == "obstacle"


def test_node_mismatch_above_half_unit_blocks():
    c, r = setup(element=(42, 40, 100, 50))  # 2 units off; tolerance is 0.5 + stroke/2 = 1
    with pytest.raises(DrawioRefused, match="disagrees"):
        build_scene(c, r, {"l1": ("n1", "note")}, "h")


def test_unmapped_movable_label_is_an_error():
    c, r = setup()
    with pytest.raises(ValueError, match="mapping"):
        build_scene(c, r, {}, "h")


def test_measured_box_outside_page_is_refused():
    c, r = setup(label_box=(590, 103, 30, 14))
    with pytest.raises(DrawioRefused, match="outside the page"):
        build_scene(c, r, {"l1": ("n1", "note")}, "h")
