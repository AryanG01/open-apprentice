from fractions import Fraction as F

from open_apprentice.evaluation.labels import Spec
from open_apprentice.evaluation.teacher_sim import SimTeacher
from open_apprentice.skills.versions import SkillStore
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.correction_executor import CorrectionExecutor, start_correction
from open_apprentice.teaching.evidence import EvidenceItem, item_to_json
from open_apprentice.teaching.step import run_output
from tests.unit.teaching.test_correction_step import BASE, NOTES, OTHER, SCENE

NEW = Spec("right", None, "notes", F(12))


class ScriptedScope:
    def __init__(self):
        self.calls = 0

    def propose_scope(self, evidence_json, round_kind):
        self.calls += 1
        return (
            [{"rule": NOTES, "selector": 'o.role == "warning"', "summary": "warnings stay below"}],
            {},
            F(1, 100),
        )


def install_base(store):
    skills = SkillStore(store)
    item = EvidenceItem("b1", "full", "o1", OTHER, output=run_output(BASE, OTHER))
    skills.store_version(
        "k",
        {
            "skill_id": "k",
            "program": {"rule": BASE, "summary": "right"},
            "evidence": [item_to_json(item)],
            "superseded": {},
            "retention_report": {},
        },
    )
    skills.activate("k", 1, None, "op0", "learn")
    return skills


def corrected():
    return dict(run_output(BASE, SCENE), l1=(F(0), F(260)))


def teacher():
    intent = {
        "kind": "revise",
        "selector": 'o.role == "warning"',
        "diagnostic_scenes": ["c", "o1"],
        "new_spec": NEW,
    }
    return SimTeacher(NEW, {"c": SCENE, "o1": OTHER}, scope_intent=intent)


def test_full_correction_activates_a_new_version(tmp_path):
    store = LocalStore(tmp_path)
    skills = install_base(store)
    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})
    status = CorrectionExecutor(store, log, ScriptedScope(), teacher(), Ledger(store, F(5))).run()
    assert status == "activated"
    v, _, _ = skills.active("k")
    assert v == 2 and skills.version("k", 2)["parent_version"] == 1
    assert skills.version("k", 2)["retention_report"]["unexplained_regressions"] == []


def test_second_concurrent_correction_is_rejected(tmp_path):
    store = LocalStore(tmp_path)
    skills = install_base(store)
    log_a = start_correction(store, "ca", "k", "c", SCENE, corrected(), ["l1"], {})
    log_b = start_correction(
        store, "cb", "k", "c", SCENE, corrected(), ["l1"], {}
    )  # same base generation
    assert (
        CorrectionExecutor(store, log_a, ScriptedScope(), teacher(), Ledger(store, F(5))).run()
        == "activated"
    )
    pointer = skills.active("k")
    status = CorrectionExecutor(store, log_b, ScriptedScope(), teacher(), Ledger(store, F(5))).run()
    assert status == "activation_rejected"
    assert skills.active("k") == pointer  # the first correction is not overwritten


def test_failed_correction_does_not_change_the_pointer(tmp_path):
    store = LocalStore(tmp_path)
    skills = install_base(store)
    pointer = skills.active("k")

    class NoScope(ScriptedScope):
        def propose_scope(self, evidence_json, round_kind):
            self.calls += 1
            return [], {}, F(0)

    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})
    status = CorrectionExecutor(store, log, NoScope(), teacher(), Ledger(store, F(5))).run()
    assert status in ("abstained", "dismissed", "override")
    assert skills.active("k") == pointer
