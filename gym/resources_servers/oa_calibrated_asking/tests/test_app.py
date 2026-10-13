"""Contract test for the calibrated-asking resources server: a seeded session, tools, and a verify that returns SEPARATE reward components.
Run from gym/:  PYTHONPATH=../src .venv/bin/python -m pytest resources_servers/oa_calibrated_asking/tests -q"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from nemo_gym.openai_utils import NeMoGymResponse
from nemo_gym.server_utils import ServerClient
from resources_servers.oa_calibrated_asking.app import OACalibratedAskingConfig, OACalibratedAskingServer

EPISODE = {"split": "development", "seed": 0, "index": 0, "kind": "badge"}  # an ambiguous demonstration


def make_app():
    config = OACalibratedAskingConfig(host="0.0.0.0", port=8080, entrypoint="", name="")
    server = OACalibratedAskingServer(config=config, server_client=MagicMock(spec=ServerClient))
    return server.setup_webserver()  # one app; each TestClient over it keeps its own cookie jar, i.e. its own session


def verify_body() -> dict:
    empty = NeMoGymResponse(
        id="r", created_at=0.0, model="m", object="response", output=[], parallel_tool_calls=False, tool_choice="auto", tools=[]
    ).model_dump()
    return {"responses_create_params": {"input": []}, "response": empty, **EPISODE}


def test_a_full_episode_scores_separate_components_and_names_one_reward():
    client = TestClient(make_app())
    client.post("/seed_session", json=EPISODE)
    asked = client.post("/ask", json={"card_widths": [300]}).json()
    assert asked["ok"] and asked["asks_left"] == 2
    bad = client.post("/commit", json={"rule": "not a rule"}).json()
    assert not bad["ok"]  # reported, can be retried
    assert client.post("/abstain", json={"reason": "demo"}).json()["ok"]
    v = client.post("/verify", json=verify_body()).json()
    assert set(v["reward_components"]) == {"correct", "held_out", "asking", "not_confidently_wrong", "economy"}
    assert v["reward"] == v["correct"] == 0.0  # abstaining is never counted as correct
    assert v["asking"] == 1.0 and v["ambiguous"] is True and v["abstained"] is True and v["asks_used"] == 1
    assert v["reward"] != sum(v["reward_components"].values())  # one named component, not a blend


def test_sessions_are_isolated_and_a_tool_call_without_an_episode_is_refused():
    app = make_app()
    a, b, nobody = TestClient(app), TestClient(app), TestClient(app)
    a.post("/seed_session", json=EPISODE)
    a.post("/ask", json={"card_widths": [200]})
    b.post("/seed_session", json={**EPISODE, "index": 1})
    assert b.post("/ask", json={"card_widths": [200]}).json()["asks_left"] == 2  # untouched by session a's question
    refused = nobody.post("/ask", json={"card_widths": [200]}).json()
    assert refused["ok"] is False and "seed_session" in refused["error"]
