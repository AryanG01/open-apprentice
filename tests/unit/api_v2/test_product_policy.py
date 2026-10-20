"""Live product sessions run a disclosed product policy (truncation-tolerant); offline sessions run policy A unchanged."""

from open_apprentice.api.v2.service import PRODUCT_POLICY, step_config
from open_apprentice.teaching.step import StepConfig
from tests.unit.api_v2.conftest import start_session


def test_live_sessions_tolerate_a_cut_reply_and_offline_ones_are_policy_a():
    assert step_config({"live": True, "policy": PRODUCT_POLICY}).tolerate_truncation
    assert step_config({"live": False, "policy": "A"}) == StepConfig(probes=True)
    assert step_config({"live": True}) == StepConfig(
        probes=True
    )  # sessions created before the policy existed


def test_session_reports_its_policy(client, v2, doc_bytes, batch_bytes):
    sid = start_session(client, v2, doc_bytes, batch_bytes, key="pol")
    assert client.get(f"/api/v2/sessions/{sid}").json()["provenance"]["policy"] == "A"
