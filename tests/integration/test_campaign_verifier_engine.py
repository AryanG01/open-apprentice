"""The campaign verifier on real Konva native state, and a case where the engine says "fits" and the verifier must refuse."""

import pytest

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.limits import fit_limits
from open_apprentice.environments.client import EngineSession
from open_apprentice.evaluation.campaign_gold import GOLD_KEYS, load_gold
from open_apprentice.evaluation.campaign_verifier import verify_story
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.evaluation.text_layout import advance_width

from .conftest import TOKEN

APPLICABLE = [(f, o) for f, o in GOLD_KEYS if load_gold(f, o) is not None]


@pytest.mark.parametrize("fid,outcome", APPLICABLE)
def test_gold_scene_read_back_from_konva_passes(engine_url, fid, outcome):
    gold = load_gold(fid, outcome)["scene"]
    session, native = EvaluatorHarness(engine_url, TOKEN).open_session(gold, owner="verifier")
    try:
        report = verify_story(load_fixture(fid)["scene"], native, gold)
        assert report.passed, report.failed()
    finally:
        session.close()


def test_engine_fit_is_not_trusted_when_it_disagrees(engine_url):
    """Kerning lets the browser fit a line the font tables cannot: the verifier, not the engine, decides."""
    text = "AVATAR WAVY TOYS"
    gold = load_gold("short_a", "layout")["scene"]
    head = next(n for n in gold["nodes"] if n.get("role") == "headline")
    head.update(text=text, width=2000)
    s = EngineSession.create(engine_url, gold, owner="verifier")
    try:
        kerned = s.call("observe_fit", artboard_id="story-1", limits=fit_limits())
        kerned_w = next(t for t in kerned["text"] if t["id"] == head["id"])["line_widths"][0]
    finally:
        s.close()
    plain_w = advance_width(text, head["fontSize"], True)
    assert kerned_w < plain_w - 2, (kerned_w, plain_w)  # the font kerns these pairs

    head["width"] = (kerned_w + plain_w) / 2  # one line for the browser, two for the font tables
    head["height"] = 80
    s = EngineSession.create(engine_url, gold, owner="verifier")
    try:
        obs = s.call("observe_fit", artboard_id="story-1", limits=fit_limits())
    finally:
        s.close()
    assert not [v for v in obs["violations"] if v["node_id"] == head["id"]], obs["violations"]

    source = load_fixture("short_a")["scene"]
    next(n for n in source["nodes"] if n.get("role") == "headline")["text"] = text
    report = verify_story(source, gold, gold)
    assert "text_fits" in report.failed(), report.failed()
