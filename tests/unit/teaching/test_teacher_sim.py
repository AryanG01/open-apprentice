import json
import sys
from fractions import Fraction as F

import pytest

from open_apprentice.evaluation.labels import Spec, oracle
from open_apprentice.evaluation.teacher_sim import SimTeacher
from open_apprentice.teaching import codec
from open_apprentice.teaching.teacher import (
    ChooseOutput,
    ConfirmPreview,
    ProtocolError,
    SubprocessTeacher,
)

SCENE = {
    "objects": [
        {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
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
    ],
    "canvas": {"w": 600, "h": 400},
}
SPEC = Spec("right", None, "all", F(12))
TRUTH = oracle(SPEC, SCENE)  # {"l0": (112, 15)}
H = codec.digest(SCENE)


def test_chooses_the_matching_alternative_or_none():
    t = SimTeacher(SPEC, {"s": SCENE})
    q = ChooseOutput("q", "s", H, (("A", dict(TRUTH)), ("B", {"l0": (F(30), F(62))})))
    assert t.answer(q).selected == "A"
    q2 = ChooseOutput("q2", "s", H, (("A", {"l0": (F(200), F(15))}), ("B", {"l0": (F(30), F(62))})))
    assert t.answer(q2).kind == "none"


def test_ambiguous_match_is_protocol_error():
    t = SimTeacher(SPEC, {"s": SCENE})
    x, y = TRUTH["l0"]
    q = ChooseOutput(
        "q", "s", H, (("A", {"l0": (x - F(1, 4), y)}), ("B", {"l0": (x + F(1, 4), y)}))
    )
    with pytest.raises(ProtocolError):
        t.answer(q)


def test_preview_is_judged_per_item():
    t = SimTeacher(SPEC, {"s": SCENE, "u": SCENE})
    items = (("i0", "s", H, dict(TRUTH)), ("i1", "u", H, {"l0": (F(30), F(62))}))
    p = ConfirmPreview("p", "learning_preview", items)
    assert dict(t.answer(p).per_item) == {"i0": "approve", "i1": "reject"}


def test_subprocess_teacher_round_trip(tmp_path):
    spec_f, scenes_f, log_f = (
        tmp_path / "spec.json",
        tmp_path / "scenes.json",
        tmp_path / "log.jsonl",
    )
    spec_f.write_text(json.dumps({"primary": "right", "fallback": None, "scope": "all", "gap": 12}))
    scenes_f.write_text(codec.dumps({"s": SCENE}).decode())
    argv = [
        sys.executable,
        "-m",
        "open_apprentice.evaluation.teacher_sim",
        str(spec_f),
        str(scenes_f),
        str(log_f),
    ]
    t = SubprocessTeacher(argv)
    r = t.ask(ChooseOutput("q", "s", H, (("A", dict(TRUTH)), ("B", {"l0": (F(30), F(62))}))))
    t.close()
    assert r.selected == "A" and r.source == "deterministic_simulator"
    assert len(log_f.read_text().splitlines()) == 1
