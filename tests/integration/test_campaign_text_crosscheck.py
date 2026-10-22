"""Engine (browser canvas, kerning on) and the verifier's font-table layout must agree on every fit verdict in the fixtures
(line counts may differ by platform near a wrap boundary)."""

import pytest
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


@pytest.mark.parametrize("backend", ["konva", "fabric"])
def test_engine_and_verifier_agree_on_line_counts(engine_url, backend):
    mismatches = []
    for name, scene in _scenes():
        s = EngineSession.create(engine_url, scene, owner="crosscheck", backend=backend)
        try:
            by_id = {n["id"]: n for n in scene["nodes"]}
            for board in (n for n in scene["nodes"] if n["type"] == "artboard"):
                obs = s.call("observe_fit", artboard_id=board["id"], limits=fit_limits())
                too_wide = {v["node_id"] for v in obs["violations"] if v["kind"] == "word_too_wide"}
                for t in obs["text"]:
                    n = by_id[t["id"]]
                    f = fit(
                        n["text"],
                        n["width"],
                        n["fontSize"],
                        n["fontStyle"] == "bold",
                        n["lineHeight"],
                    )
                    if f.word_too_wide or t["id"] in too_wide:
                        # an over-wide word has no common layout (Konva breaks it, Fabric widens the box): both sides
                        # must still call it a failure
                        if not (f.word_too_wide and t["id"] in too_wide):
                            mismatches.append(
                                (backend, name, t["id"], "word_too_wide disagreement")
                            )
                    elif (f.height <= n["height"]) != (t["text_height"] <= t["frame_height"]):
                        # the fit VERDICT must agree; exact line counts may differ by platform near a wrap boundary
                        # (Linux and macOS Chromium measure the same font slightly differently)
                        mismatches.append((backend, name, t["id"], t["lines"], f.lines))
        finally:
            s.close()
    assert not mismatches, "\n".join(map(str, mismatches))
