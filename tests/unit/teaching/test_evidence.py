from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import derive
from open_apprentice.teaching.events import Event
from open_apprentice.teaching.evidence import EvidenceItem, item_fits, item_from_json, item_to_json
from open_apprentice.teaching.step import run_output

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
RIGHT = rule_for_spec(Spec("right", None, "all", F(12)))


def test_full_item_fits_its_own_output_and_rejects_another():
    out = run_output(RIGHT, SCENE)
    item = EvidenceItem("e1:0", "full", "s", SCENE, output=out)
    assert item_fits(RIGHT, item)[0]
    other = dict(out, l1=(F(0), F(260)))
    assert not item_fits(RIGHT, EvidenceItem("e1:1", "full", "s", SCENE, output=other))[0]


def test_masked_item_checks_only_masked_labels():
    out = run_output(RIGHT, SCENE)
    masked = EvidenceItem("e2:0", "masked", "s", SCENE, output={"l0": out["l0"]}, mask=("l0",))
    assert item_fits(RIGHT, masked)[0]
    notes_only = rule_for_spec(Spec("right", None, "notes", F(12)))  # leaves l1 alone
    assert item_fits(notes_only, masked)[0]


def test_excludes_item_rejects_a_reproduced_output():
    out = run_output(RIGHT, SCENE)
    assert not item_fits(RIGHT, EvidenceItem("e3:0", "excludes", "s", SCENE, excluded=(out,)))[0]


def test_json_round_trip():
    item = EvidenceItem(
        "e4:0",
        "masked",
        "s",
        SCENE,
        output={"l0": (F(1, 3), F(2))},
        mask=("l0",),
        source="correction",
    )
    once = item_from_json(item_to_json(item))
    assert item_from_json(codec.loads(codec.dumps(item_to_json(once)))) == once


def test_derive_produces_identified_items():
    evs = [
        Event(
            "e1",
            None,
            1,
            "SceneRegistered",
            "system",
            {
                "scene_id": "d",
                "scene_hash": codec.digest(SCENE),
                "scene": codec.loads(codec.dumps(SCENE)),
                "role": "demo",
            },
        ),
        Event(
            "e2",
            "e1",
            2,
            "DemonstrationRecorded",
            "human",
            {"scene_id": "d", "output": codec.loads(codec.dumps(run_output(RIGHT, SCENE)))},
        ),
    ]
    items = derive(evs).items
    assert [(i.id, i.kind, i.scene_id) for i in items] == [("e2:0", "full", "d")]
