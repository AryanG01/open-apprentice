import pytest

from open_apprentice.teaching.scope import SelectorError, members, parse_selector

SCENE = {
    "objects": [
        {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 200, "h": 50},
        {
            "id": "n1",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": 0,
            "y": 200,
            "w": 80,
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
        {
            "id": "l2",
            "kind": "label",
            "role": "warning",
            "attached": "n0",
            "x": 50,
            "y": 60,
            "w": 40,
            "h": 20,
        },
    ],
    "canvas": {"w": 600, "h": 400},
}


def test_role_selector():
    assert members('o.role == "warning"', SCENE) == {"l1", "l2"}


def test_attachment_geometry_selector():
    assert members("object(o.attached).w > 100", SCENE) == {"l0", "l2"}


def test_everything_selector():
    assert members('o.kind == "label"', SCENE) == {"l0", "l1", "l2"}


@pytest.mark.parametrize(
    "bad",
    [
        'o.role == "w" } for p in objects { move p to (0, 0)',
        "o.x > 0\nmove o to (0,0)",
        "for p in objects",
        "x" * 400,
    ],
)
def test_selector_injection_is_refused(bad):
    with pytest.raises(SelectorError):
        parse_selector(bad)
