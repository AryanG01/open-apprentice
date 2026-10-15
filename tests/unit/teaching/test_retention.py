from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.teaching.evidence import EvidenceItem
from open_apprentice.teaching.retention import behaviour_diff, retention_report
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
            "id": "n2",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": 300,
            "y": 0,
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
        {
            "id": "l2",
            "kind": "label",
            "role": "warning",
            "attached": "n2",
            "x": 300,
            "y": 60,
            "w": 40,
            "h": 20,
        },
    ],
    "canvas": {"w": 600, "h": 400},
}
BASE = rule_for_spec(Spec("right", None, "all", F(12)))
NOTES_ONLY = rule_for_spec(Spec("right", None, "notes", F(12)))


def test_correcting_one_warning_updates_other_warnings_in_scope_and_leaves_notes():
    d = behaviour_diff(BASE, NOTES_ONLY, {"s": SCENE}, 'o.role == "warning"', frozenset())
    assert sorted(d["in_scope"]) == [("s", "l1"), ("s", "l2")]
    assert d["unexplained"] == []
    assert run_output(NOTES_ONLY, SCENE)["l0"] == run_output(BASE, SCENE)["l0"]


def test_change_outside_selector_is_unexplained_unless_an_approved_exception():
    d = behaviour_diff(BASE, NOTES_ONLY, {"s": SCENE}, 'o.role == "note"', frozenset())
    assert sorted(d["unexplained"]) == [("s", "l1"), ("s", "l2")]
    d2 = behaviour_diff(
        BASE, NOTES_ONLY, {"s": SCENE}, 'o.role == "note"', frozenset({("s", "l1"), ("s", "l2")})
    )
    assert d2["unexplained"] == [] and len(d2["exception"]) == 2


def test_retention_report_flags_regressions_and_counts_retained():
    keep = EvidenceItem("a", "full", "s", SCENE, output=run_output(NOTES_ONLY, SCENE))
    lost = EvidenceItem("b", "full", "s", SCENE, output=run_output(BASE, SCENE))
    d = behaviour_diff(BASE, NOTES_ONLY, {"s": SCENE}, 'o.role == "warning"', frozenset())
    rep = retention_report(NOTES_ONLY, [keep, lost], {}, [], d, 1)
    assert [r["id"] for r in rep["retained"] if r["ok"]] == ["a"]
    assert rep["unexplained_regressions"] == ["b"] and rep["scope_violations"] == []
