import json
import sys
from fractions import Fraction as F
from functools import lru_cache

import pytest

from open_apprentice.evaluation.battery_v2 import build_battery, episode_to_json, scene_ids
from open_apprentice.evaluation.specs_v2 import oracle_v
from open_apprentice.evaluation.teacher_sim import SimTeacher, handle, teacher_for
from open_apprentice.teaching import codec
from open_apprentice.teaching.teacher import (
    ChooseOutput,
    ConfirmCorrectionScope,
    ConfirmPreview,
    Interpretation,
    ProtocolError,
    RequestDemonstration,
    SubprocessTeacher,
    request_to_json,
)


@lru_cache(maxsize=None)
def _dev():
    return tuple(build_battery("dev"))


def _ep(stratum, kind=None):
    for e in _dev():
        if e.stratum == stratum and (kind is None or e.correction["kind"] == kind):
            return e
    raise LookupError


def _full(spec, scene):
    moved = oracle_v(spec, scene)
    return {
        o["id"]: moved.get(o["id"], (F(o["x"]), F(o["y"])))
        for o in scene["objects"]
        if o["kind"] == "label"
    }


def _h(scene):
    return codec.digest(scene)


def _revise(iid, ep, selector):
    c = ep.correction
    return Interpretation(
        iid, "revise", selector, "s", (("c0", _h(c["scene"]), _full(c["spec"], c["scene"])),)
    )


def _other(iid, kind):
    return Interpretation(iid, kind, None, kind, ())


NEAR_MISS = 'o.role == "warning" and object(o.attached).w > 60'


def test_exact_scope_is_selected_and_a_near_miss_is_not():
    ep = _ep("sequential", "compatible")
    assert ep.correction["template"] in ("warn_below", "tall_below")
    t = teacher_for(ep)
    exact = _revise("a", ep, ep.correction["selector"])
    near = _revise("b", ep, NEAR_MISS if "role" in ep.correction["selector"] else "o.w > 60")
    r = t.answer(ConfirmCorrectionScope("q", (near, exact)))
    assert (r.kind, r.selected) == ("select", "a")


def test_near_miss_selector_alone_gets_none():
    ep = next(
        e
        for e in _dev()
        if e.stratum == "sequential" and e.correction["selector"] == 'o.role == "warning"'
    )
    t = teacher_for(ep)
    r = t.answer(
        ConfirmCorrectionScope("q", (_revise("b", ep, NEAR_MISS), _other("o", "override")))
    )
    assert r.kind == "none"


def test_right_scope_with_wrong_consequences_gets_none():
    ep = _ep("sequential", "compatible")
    c = ep.correction
    wrong = _full(ep.spec, c["scene"])  # the old behaviour's output
    bad = Interpretation("a", "revise", c["selector"], "s", (("c0", _h(c["scene"]), wrong),))
    r = teacher_for(ep).answer(ConfirmCorrectionScope("q", (bad, _other("o", "override"))))
    assert r.kind == "none"


@pytest.mark.parametrize("kind", ["override", "accidental"])
def test_override_and_accidental_scripts_pick_their_kind(kind):
    ep = _ep("sequential", kind)
    interps = (_other("o", "override"), _other("x", "accidental"), _other("r", "revise"))
    r = teacher_for(ep).answer(ConfirmCorrectionScope("q", interps))
    assert r.selected == {"override": "o", "accidental": "x"}[kind]


def test_conflict_script_authorizes_no_scope():
    ep = _ep("sequential", "conflict")
    exact = _revise("a", ep, ep.correction["selector"])
    r = teacher_for(ep).answer(ConfirmCorrectionScope("q", (exact, _other("o", "override"))))
    assert r.kind == "none"


def test_demonstration_uses_the_behaviour_spec():
    ep = _ep("beyond")
    s = ep.batch_scenes[0]
    r = teacher_for(ep).answer(RequestDemonstration("q", "b0", _h(s)))
    assert r.output == _full(ep.spec, s)


def test_inconsistent_demonstration_returns_the_scripted_conflicting_output():
    ep = _ep("inconsistent")
    s = ep.batch_scenes[1]
    r = teacher_for(ep).answer(RequestDemonstration("q", "b1", _h(s)))
    from open_apprentice.evaluation.battery_v2 import vspec_from_json

    assert r.output == _full(vspec_from_json(ep.meta["conflict_spec"]), s)
    assert r.output != _full(ep.spec, s)


def test_previews_after_the_scope_question_are_judged_by_the_corrected_behaviour():
    ep = _ep("sequential", "compatible")
    c = ep.correction
    t = teacher_for(ep)
    s = ep.batch_scenes[0]
    sid = "b0"
    before = t.answer(
        ConfirmPreview("p0", "learning_preview", (("i", sid, _h(s), _full(ep.spec, s)),))
    )
    assert before.per_item == (("i", "approve"),)
    t.answer(
        ConfirmCorrectionScope("q", (_revise("a", ep, c["selector"]), _other("o", "override")))
    )
    after = t.answer(
        ConfirmPreview("p1", "revision_preview", (("i", sid, _h(s), _full(c["spec"], s)),))
    )
    assert after.per_item == (("i", "approve"),)


def test_a_displayed_probe_scene_is_registered_by_hash():
    ep = _ep("catalogue")
    t = teacher_for(ep)
    probe = dict(ep.batch_scenes[0], canvas={"w": 700, "h": 800})
    truth = _full(ep.spec, probe)
    other = {k: (x + 40, y) for k, (x, y) in truth.items()}
    req = request_to_json(ChooseOutput("q", "p1", _h(probe), (("A", other), ("B", truth))))
    out = handle(t, dict(req, scene=codec.loads(codec.dumps(probe))))
    assert out["selected"] == "B"
    bad = handle(t, dict(req, scene_id="p2", scene=codec.loads(codec.dumps(ep.batch_scenes[1]))))
    assert "protocol_error" in bad
    unknown = handle(t, dict(req, scene_id="p3"))
    assert "protocol_error" in unknown


def test_subprocess_round_trip_on_a_sequential_episode(tmp_path):
    ep = _ep("sequential", "compatible")
    priv, log = tmp_path / "ep.private.json", tmp_path / "log.jsonl"
    priv.write_bytes(codec.dumps(episode_to_json(ep)))
    t = SubprocessTeacher(
        [sys.executable, "-m", "open_apprentice.evaluation.teacher_sim", str(priv), str(log)]
    )
    try:
        exact = _revise("a", ep, ep.correction["selector"])
        r = t.ask(ConfirmCorrectionScope("q", (exact, _other("o", "override"))))
        s = scene_ids(ep)["b0"]
        d = t.ask(RequestDemonstration("q2", "b0", _h(s)))
    finally:
        t.close()
    assert (r.selected, r.source) == ("a", "deterministic_simulator")
    assert d.output == _full(ep.spec, s)
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert [x["request"]["request_id"] for x in lines] == ["q", "q2"]


def test_legacy_spec_constructor_still_works():
    ep = _ep("catalogue")
    t = SimTeacher(ep.spec.params[0], {"b0": ep.batch_scenes[0]})
    s = ep.batch_scenes[0]
    assert t.answer(RequestDemonstration("q", "b0", _h(s))).output == _full(ep.spec, s)


def test_unknown_scene_without_payload_is_a_protocol_error():
    t = teacher_for(_ep("catalogue"))
    with pytest.raises(ProtocolError):
        t.answer(RequestDemonstration("q", "nope", "h"))


def test_scoring_and_diagnostic_scenes_are_never_answered():
    ep = _ep("sequential", "compatible")
    t = teacher_for(ep)
    for sid, scene in (("s0", ep.scoring_scenes[0]), ("x0", ep.correction["diagnostic_scenes"][0])):
        with pytest.raises(ProtocolError):
            t.answer(RequestDemonstration("q", sid, _h(scene)))


def test_a_request_whose_hash_does_not_match_the_scene_is_refused():
    ep = _ep("catalogue")
    t = teacher_for(ep)
    s = ep.batch_scenes[0]
    with pytest.raises(ProtocolError):
        t.answer(RequestDemonstration("q", "b0", _h(ep.batch_scenes[1])))
    truth = _full(ep.spec, s)
    with pytest.raises(ProtocolError):
        t.answer(ConfirmPreview("p", "learning_preview", (("i", "b0", "bad", truth),)))
