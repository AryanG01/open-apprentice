from fractions import Fraction as F

from open_apprentice.skills.versions import SkillStore
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.executor import Executor
from open_apprentice.teaching.step import StepConfig
from tests.unit.teaching.test_executor import ApprovingTeacher, CountingProposer, start


def test_learning_commit_stores_version_one_with_its_evidence(tmp_path):
    store, log = start(tmp_path)
    ex = Executor(
        store,
        log,
        CountingProposer(),
        ApprovingTeacher(),
        Ledger(store, F(5)),
        StepConfig(),
        skill_id="k",
    )
    assert ex.run() == "committed"
    skills = SkillStore(store)
    v1 = skills.version("k", 1)
    assert v1["program"]["rule"] and {e["kind"] for e in v1["evidence"]} == {"full"}
    assert skills.active("k")[0] is None  # storing is not activating
    stored = next(e for e in log.events() if e.type == "VersionStored")
    assert stored.payload["skill_id"] == "k" and stored.payload["version"] == 1
