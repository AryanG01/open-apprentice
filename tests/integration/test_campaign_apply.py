import pytest

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.plan import plan_from_layout
from open_apprentice.campaign.procedures import apply_plan
from open_apprentice.environments.client import EngineToolError
from open_apprentice.evaluation.campaign_gold import load_gold
from open_apprentice.evaluation.campaign_verifier import verify_story
from open_apprentice.evaluation.harness import EvaluatorHarness

from ..unit.campaign.test_plan import taught_outcome
from .conftest import TOKEN


def test_reference_procedure_reproduces_the_taught_story(engine_url):
    harness = EvaluatorHarness(engine_url, TOKEN)
    src = load_fixture("teach_before")["scene"]
    session, _ = harness.open_session(src, owner="apply")
    try:
        out = apply_plan(
            session, plan_from_layout(taught_outcome(), src, "banner", origin="search")
        )
        assert out["origin"] == "reference" and out["actions"] > 0
        report = verify_story(
            src,
            harness.native(session.session_id, "apply"),
            load_gold("teach_before", "layout")["scene"],
        )
        assert report.passed, report.failed()
    finally:
        session.close()


def test_a_target_missing_from_the_scene_is_a_tool_error(engine_url):
    harness = EvaluatorHarness(engine_url, TOKEN)
    src = load_fixture("teach_before")["scene"]
    outcome = taught_outcome()
    ghost = outcome.targets.pop("tb-head")
    ghost.node_id = "ghost"
    outcome.targets["ghost"] = ghost
    session, _ = harness.open_session(src, owner="apply")
    try:
        with pytest.raises(EngineToolError):
            apply_plan(session, plan_from_layout(outcome, src, "banner", origin="search"))
    finally:
        session.close()
