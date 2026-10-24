"""The probe's plumbing on the mock provider and the REAL engine (no spend): renders each banner, sends the image part,
scores the reply. Proves the harness, not Nemotron."""

import asyncio

from open_apprentice.evaluation.campaign_vision_eval import (
    DEV_BANNERS,
    gold_layers,
    run_dev,
    verdict,
)
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.providers.mock import MockProvider

from .conftest import TOKEN


def test_the_probe_renders_scores_and_decides_on_the_mock(engine_url):
    replies = []
    for fid in DEV_BANNERS:
        gold = gold_layers(load_fixture(fid)["scene"])
        replies.append(
            {
                "language": "en",
                "layers": [
                    {
                        "role": r,
                        "box": [
                            g["box"][0] / 1.28,
                            g["box"][1] / 0.72,
                            (g["box"][0] + g["box"][2]) / 1.28,
                            (g["box"][1] + g["box"][3]) / 0.72,
                        ],
                        "text": g["text"],
                        "font_px": g["font_px"] or 20,
                        "bold": True,
                        "color": "#ffffff",
                    }
                    for r, g in gold.items()
                ],
            }
        )
    provider = MockProvider({"campaign_vision": replies})
    rows = asyncio.run(run_dev(provider, engine_url, TOKEN))
    assert [r["banner"] for r in rows] == list(DEV_BANNERS)
    for call in provider.calls:  # every call carried a real rendered PNG as an image part
        part = call[1][-1].content[-1]
        assert part["type"] == "image_url" and part["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
    assert all(r["score"]["all_matched"] for r in rows)
    assert verdict([r["score"] for r in rows])["decision"] == "go"
