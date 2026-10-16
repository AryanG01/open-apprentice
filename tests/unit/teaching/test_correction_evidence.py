from fractions import Fraction as F

from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.correction_executor import CorrectionExecutor, start_correction
from tests.unit.teaching.test_correction_executor import corrected, install_base, teacher
from tests.unit.teaching.test_correction_step import SCENE


def test_scope_evidence_carries_the_corrected_scene_and_positions(tmp_path):
    store = LocalStore(tmp_path)
    install_base(store)
    log = start_correction(store, "c1", "k", "c", SCENE, corrected(), ["l1"], {})
    seen = {}

    class Capture:
        def propose_scope(self, evidence_json, round_kind):
            seen.update(evidence_json)
            return [], {}, F(0)

    CorrectionExecutor(store, log, Capture(), teacher(), Ledger(store, F(5))).run(max_steps=3)
    assert {o["id"] for o in seen["corrected_scene_objects"]} == {o["id"] for o in SCENE["objects"]}
    assert seen["canvas"] == {"w": 600, "h": 400}
    assert set(seen["corrected_output"]) == {"l1"}
