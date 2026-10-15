from fractions import Fraction as F

import pytest

from open_apprentice.evaluation.labels import Spec, oracle
from open_apprentice.evaluation.teacher_sim import SimTeacher
from open_apprentice.teaching import codec
from open_apprentice.teaching.teacher import (
    ConfirmCorrectionScope,
    Interpretation,
    ProtocolError,
    Response,
    request_from_json,
    request_to_json,
    validate_request,
    validate_response,
)

SCENE = {
    "objects": [
        {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
        {
            "id": "n1",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": 0,
            "y": 200,
            "w": 100,
            "h": 50,
        },
        {
            "id": "l0",
            "kind": "label",
            "role": "note",
            "attached": "n0",
            "x": 0,
            "y": 60,
            "w": 40,
            "h": 20,
        },
        {
            "id": "l1",
            "kind": "label",
            "role": "warning",
            "attached": "n1",
            "x": 0,
            "y": 260,
            "w": 40,
            "h": 20,
        },
    ],
    "canvas": {"w": 600, "h": 400},
}
H = codec.digest(SCENE)
NEW = Spec("right", None, "notes", F(12))  # intended: warnings stay put


def labels_out(spec):
    moved = oracle(spec, SCENE)
    return {
        o["id"]: moved.get(o["id"], (F(o["x"]), F(o["y"])))
        for o in SCENE["objects"]
        if o["kind"] == "label"
    }


def req():
    right_all = labels_out(Spec("right", None, "all", F(12)))
    notes = labels_out(NEW)
    return ConfirmCorrectionScope(
        "c1",
        (
            Interpretation(
                "i1", "revise", 'o.role == "warning"', "warnings stay", (("s", H, notes),)
            ),
            Interpretation(
                "i2", "revise", 'o.kind == "label"', "nothing changes", (("s", H, right_all),)
            ),
            Interpretation("i3", "override", None, "only this document", ()),
            Interpretation("i4", "accidental", None, "undo my edit", ()),
        ),
    )


def test_validation_and_json_round_trip():
    r = req()
    validate_request(r, {"s": H})
    assert request_from_json(request_to_json(r)) == r
    validate_response(r, Response("c1", "select", selected="i1"))
    with pytest.raises(ProtocolError):
        validate_response(r, Response("c1", "select", selected="zz"))
    with pytest.raises(ProtocolError):
        validate_request(ConfirmCorrectionScope("c2", req().interpretations[:1]), {"s": H})


def test_simulator_selects_by_meaning():
    intent = {
        "kind": "revise",
        "selector": 'o.role == "warning"',
        "diagnostic_scenes": ["s"],
        "new_spec": NEW,
    }
    t = SimTeacher(NEW, {"s": SCENE}, scope_intent=intent)
    assert t.answer(req()).selected == "i1"


def test_simulator_says_none_when_no_interpretation_means_the_intent():
    intent = {
        "kind": "revise",
        "selector": 'o.role == "note"',
        "diagnostic_scenes": ["s"],
        "new_spec": NEW,
    }
    t = SimTeacher(NEW, {"s": SCENE}, scope_intent=intent)
    assert t.answer(req()).kind == "none"


def test_simulator_chooses_override_when_that_is_the_intent():
    t = SimTeacher(NEW, {"s": SCENE}, scope_intent={"kind": "override"})
    assert t.answer(req()).selected == "i3"
