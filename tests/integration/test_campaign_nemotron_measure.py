"""The measurement's shape on the mock provider (no spend): proves the table, not Nemotron."""

import json

from open_apprentice.campaign.explain import template_explanation
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.procedures import APPLY_PLAN
from open_apprentice.evaluation.campaign_nemotron import ROLE_BANNERS, measure, render_markdown
from open_apprentice.providers.mock import MockProvider

from .conftest import TOKEN


def _truth_for(messages):
    ids = {x["id"] for x in json.loads(messages[-1].content)["layers"]}
    for fid in ROLE_BANNERS:
        nodes = load_fixture(fid)["scene"]["nodes"]
        if ids == {n["id"] for n in nodes if n.get("parent") == "banner"}:
            return {"roles": {n["id"]: n["role"] for n in nodes if n.get("role")}}
    raise AssertionError("unknown banner")


def test_the_measurement_table_on_the_mock(engine_url):
    provider = MockProvider(
        {},
        functions={
            "campaign_roles": _truth_for,
            "campaign_explain": lambda m: {"text": template_explanation(json.loads(m[-1].content))},
            "campaign_procedure": lambda m: {
                "candidates": [{"program": APPLY_PLAN, "summary": "s"}]
            },
        },
    )
    m = measure(provider, engine_url, TOKEN)
    assert len(m["roles"]) == 6 and all(
        r["model_correct"] and r["heuristic_correct"] for r in m["roles"]
    )
    assert [e["origin"] for e in m["explanations"]] == ["model"] * 3
    assert [p["origin"] for p in m["procedures"]] == ["model", "model"]
    md = render_markdown(m, live=False)
    assert "MOCK provider" in md and "Nemotron correct on **6 of 6**" in md
