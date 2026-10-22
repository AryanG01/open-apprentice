"""Engine (browser canvas, kerning on) and the verifier's font-table layout must agree on every line count in the fixtures."""

from open_apprentice.campaign.fixtures import FIXTURE_IDS, load_fixture
from open_apprentice.campaign.limits import fit_limits
from open_apprentice.environments.client import EngineSession
from open_apprentice.evaluation.campaign_gold import GOLD_KEYS, load_gold
from open_apprentice.evaluation.text_layout import fit


def _scenes():
    for fid in FIXTURE_IDS:
        yield fid, load_fixture(fid)["scene"]
    for fid, outcome in GOLD_KEYS:
        g = load_gold(fid, outcome)
        if g is not None:
            yield f"{fid}.{outcome}", g["scene"]


def test_engine_and_verifier_agree_on_line_counts(engine_url):
    mismatches = []
    for name, scene in _scenes():
        s = EngineSession.create(engine_url, scene, owner="crosscheck")
        try:
            by_id = {n["id"]: n for n in scene["nodes"]}
            for board in (n for n in scene["nodes"] if n["type"] == "artboard"):
                obs = s.call("observe_fit", artboard_id=board["id"], limits=fit_limits())
                for t in obs["text"]:
                    n = by_id[t["id"]]
                    mine = fit(n["text"], n["width"], n["fontSize"], n["fontStyle"] == "bold", n["lineHeight"]).lines
                    if len(mine) != len(t["lines"]):
                        mismatches.append((name, t["id"], t["lines"], mine))
        finally:
            s.close()
    assert not mismatches, "\n".join(map(str, mismatches))
