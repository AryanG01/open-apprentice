from fractions import Fraction as F

from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import derive
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.teacher import (
    ChooseOutput,
    ConfirmPreview,
    Response,
    request_to_json,
    response_to_json,
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


def ev(i, t, payload):
    origin = "human" if t in ("DemonstrationRecorded", "ResponseRecorded") else "system"
    return Event(f"e{i}", f"e{i-1}" if i > 1 else None, i, t, origin, payload)


def reg(i, sid, role):
    return ev(
        i,
        "SceneRegistered",
        {
            "scene_id": sid,
            "scene_hash": codec.digest(SCENE),
            "scene": codec.loads(codec.dumps(SCENE)),
            "role": role,
        },
    )


def out(x, y):
    return {"l0": (F(x), F(y))}


def resp(i, r):
    return ev(i, "ResponseRecorded", {"response": response_to_json(r)})


def test_demonstration_is_full_positive():
    evs = [
        reg(1, "d", "demo"),
        ev(2, "DemonstrationRecorded", {"scene_id": "d", "output": {"l0": [112, 15]}}),
    ]
    e = derive(evs)
    assert len(e.positives) == 1
    assert e.positives[0].expected["l0"]["x"] == 112 and e.positives[0].expected["n0"]["x"] == 0


def test_choose_adds_positive_none_excludes_all_shown_unsure_adds_nothing():
    h = codec.digest(SCENE)
    q = ChooseOutput("q1", "b", h, (("A", out(112, 15)), ("B", out(30, 62))))
    base = [
        reg(1, "b", "batch"),
        ev(2, "RequestIssued", {"request": request_to_json(q), "action_id": "a"}),
    ]
    chose = derive(base + [resp(3, Response("q1", "choose", selected="A"))])
    assert len(chose.positives) == 1 and not chose.negatives
    none = derive(base + [resp(3, Response("q1", "none"))])
    assert not none.positives and len(none.negatives) == 1 and len(none.negatives[0].excluded) == 2
    unsure = derive(base + [resp(3, Response("q1", "unsure"))])
    assert not unsure.positives and not unsure.negatives


def test_preview_rejection_excludes_only_that_item():
    h = codec.digest(SCENE)
    p = ConfirmPreview(
        "p1", "learning_preview", (("i1", "b", h, out(112, 15)), ("i2", "c", h, out(112, 15)))
    )
    evs = [
        reg(1, "b", "batch"),
        reg(2, "c", "batch"),
        ev(3, "RequestIssued", {"request": request_to_json(p), "action_id": "a"}),
        resp(4, Response("p1", "items", per_item=(("i1", "approve"), ("i2", "reject")))),
    ]
    e = derive(evs)
    assert set(e.approved) == {"b"} and set(e.rejected) == {"c"}
    assert len(e.positives) == 1 and len(e.negatives) == 1
