from fractions import Fraction as F

import pytest

from open_apprentice.evaluation.labels import Spec, inside, make_scene, oracle
from open_apprentice.evaluation.specs_v2 import STRATA, VSpec, oracle_v, scene_v


def _node(i, x, y, w, h):
    return {"id": i, "kind": "node", "role": "", "attached": "", "x": x, "y": y, "w": w, "h": h}


def _label(i, node, role="note", w=40, h=20):
    return {
        "id": i,
        "kind": "label",
        "role": role,
        "attached": node,
        "x": 0,
        "y": 0,
        "w": w,
        "h": h,
    }


def _scene(*objs, w=1200, h=800):
    return {"objects": list(objs), "canvas": {"w": w, "h": h}}


def test_catalogue_wraps_the_labels_oracle():
    scene = make_scene(3, 8, warnings=2)
    spec = Spec("right", "below", "notes", F(8))
    assert oracle_v(VSpec("catalogue", (spec,)), scene) == oracle(spec, scene)


def test_gap_by_width_scales_with_the_node_and_clamps():
    scene = _scene(
        _node("a", 100, 100, 140, 40),
        _label("la", "a"),
        _node("b", 100, 400, 50, 40),
        _label("lb", "b"),
        _node("c", 100, 600, 400, 40),
        _label("lc", "c"),
    )
    out = oracle_v(VSpec("gap_by_width", ()), scene)
    assert out["la"] == (F(100 + 140 + 14), F(110))
    assert out["lb"] == (F(100 + 50 + 8), F(410))
    assert out["lc"] == (F(100 + 400 + 24), F(610))


def test_role_sides_sends_notes_right_and_warnings_below():
    scene = _scene(
        _node("a", 100, 100, 100, 40),
        _label("la", "a", "note"),
        _node("b", 400, 100, 100, 40),
        _label("lb", "b", "warning"),
    )
    out = oracle_v(VSpec("role_sides", (F(10),)), scene)
    assert out["la"] == (F(210), F(110))
    assert out["lb"] == (F(430), F(150))


def test_fallback_chain_takes_left_when_right_and_below_are_blocked():
    scene = _scene(
        _node("a", 300, 100, 100, 40),
        _label("la", "a"),
        _node("r", 405, 90, 60, 60),  # blocks the right pose
        _node("d", 300, 145, 100, 40),  # blocks the below pose
    )
    out = oracle_v(VSpec("fallback_chain", (F(12),)), scene)
    assert out == {"la": (F(300 - 12 - 40), F(110))}


def test_fallback_chain_takes_below_when_only_right_is_blocked():
    scene = _scene(_node("a", 1100, 100, 80, 40), _label("la", "a"))  # right runs off the page
    out = oracle_v(VSpec("fallback_chain", (F(12),)), scene)
    assert out == {"la": (F(1120), F(152))}


def test_size_side_follows_node_aspect():
    scene = _scene(
        _node("wide", 100, 100, 100, 40),
        _label("lw", "wide"),
        _node("tall", 400, 100, 50, 80),
        _label("lt", "tall"),
        _node("sq", 700, 100, 60, 60),
        _label("ls", "sq"),
    )
    out = oracle_v(VSpec("size_side", (F(12),)), scene)
    assert out["lw"] == (F(212), F(110))
    assert out["lt"] == (F(405), F(192))
    assert out["ls"] == (F(710), F(172))  # w == h is not wide: below


def test_unobservable_depends_on_a_hidden_key():
    scene = scene_v("grid", 5)
    a = oracle_v(VSpec("unobservable", ("k1",)), scene)
    b = oracle_v(VSpec("unobservable", ("k2",)), scene)
    assert set(a) == set(b) == {o["id"] for o in scene["objects"] if o["kind"] == "label"}
    assert a != b


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        oracle_v(VSpec("nope", ()), scene_v("grid", 1))


@pytest.mark.parametrize("stratum", STRATA)
def test_strata_are_deterministic_and_inside_the_page(stratum):
    for seed in range(20):
        s = scene_v(stratum, seed)
        assert s == scene_v(stratum, seed)
        boxes = [(F(o["x"]), F(o["y"]), F(o["w"]), F(o["h"])) for o in s["objects"]]
        assert all(inside(b, s["canvas"]) for b in boxes)
        kinds = [o["kind"] for o in s["objects"]]
        assert kinds.count("label") == kinds.count("node") >= 2
    assert scene_v(stratum, 1) != scene_v(stratum, 2)


def test_narrow_stratum_is_600_wide_and_strata_cover_both_aspects():
    assert scene_v("narrow", 4)["canvas"]["w"] == 600
    nodes = [o for s in range(10) for o in scene_v("rows", s)["objects"] if o["kind"] == "node"]
    assert any(n["w"] > n["h"] for n in nodes) and any(n["w"] <= n["h"] for n in nodes)


@pytest.mark.parametrize(
    "spec",
    [
        VSpec("gap_by_width", ()),
        VSpec("role_sides", (F(12),)),
        VSpec("fallback_chain", (F(12),)),
        VSpec("size_side", (F(8),)),
        VSpec("unobservable", ("k",)),
        VSpec("catalogue", (Spec("right", "below", "all", F(12)),)),
    ],
)
def test_oracles_never_move_nodes(spec):
    for stratum in STRATA:
        scene = scene_v(stratum, 7)
        labels = {o["id"] for o in scene["objects"] if o["kind"] == "label"}
        assert set(oracle_v(spec, scene)) <= labels
