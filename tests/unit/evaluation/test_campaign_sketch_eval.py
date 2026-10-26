"""The sketch probe's plumbing on the mock provider, offline (no spend, no browser): drawing, scoring, rule, CLI refusal."""

import asyncio

from typer.testing import CliRunner

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.imageinfo import image_size
from open_apprentice.campaign.vision import Layer, LayerProposal
from open_apprentice.cli import app
from open_apprentice.evaluation.campaign_sketch_eval import (
    DEV_BANNERS,
    data_url,
    draw_wireframe,
    render_markdown,
    run_dev,
    score_case,
    to_canvas,
    verdict,
)
from open_apprentice.evaluation.campaign_vision_eval import banner_frame, gold_layers
from open_apprentice.providers.mock import MockProvider


def _scene(fid="short_a"):
    sc = load_fixture(fid)["scene"]
    return gold_layers(sc), banner_frame(sc)


def _reply(fid, shift=0.0, drop=()):
    gold, frame = _scene(fid)
    return {
        "language": "en",
        "layers": [
            {
                "role": r,
                "box": [
                    g["box"][0] / frame[0] * 1000 + shift,
                    g["box"][1] / frame[1] * 1000,
                    (g["box"][0] + g["box"][2]) / frame[0] * 1000 + shift,
                    (g["box"][1] + g["box"][3]) / frame[1] * 1000,
                ],
                "text": "",
                "font_px": 0,
            }
            for r, g in gold.items()
            if r not in drop
        ],
    }


def test_the_wireframe_is_a_deterministic_1280_by_720_png_with_every_role_drawn():
    gold, frame = _scene()
    a, ext = draw_wireframe(gold, frame)
    assert a == draw_wireframe(gold, frame)[0] != draw_wireframe(gold, frame, seed=1)[0]
    assert image_size(data_url(a)) == ("png", 1280, 720) and len(a) < 120_000
    assert set(ext) == set(gold)


def test_a_long_text_draws_more_rows_than_a_short_one():
    short, frame = _scene("short_a")
    long, _ = _scene("de_long_a")
    h = lambda g, f: (lambda e: e["headline"][3] - e["headline"][1])(draw_wireframe(g, f)[1])
    assert h(long, banner_frame(load_fixture("de_long_a")["scene"])) > h(short, frame) * 0.9


def test_a_perfect_reading_is_found_and_a_missing_or_shifted_one_is_not():
    gold, frame = _scene()
    from open_apprentice.campaign.vision import from_vision

    good = from_vision(_reply("short_a"))
    s = score_case(good, gold, frame)
    assert s["roles_present"] and s["all_found"] and all(v > 0.99 for v in s["iou"].values())
    s = score_case(from_vision(_reply("short_a", drop=("cta",))), gold, frame)
    assert not s["roles_present"] and s["iou"]["cta"] == 0.0 and not s["all_found"]
    s = score_case(from_vision(_reply("short_a", shift=400)), gold, frame)
    assert not s["all_found"]
    dup = LayerProposal([Layer(role="cta", box=[0, 0, 5, 5])] * 2, "en", "model")
    assert score_case(dup, gold, frame)["iou"]["cta"] == 0.0
    assert to_canvas(gold, frame)["headline"]["box"][0] == 640


def test_the_registered_rule():
    ok = {"roles_present": True, "all_found": True, "iou": {"a": 0.7}, "invented_words": 0}
    meh = {"roles_present": True, "all_found": False, "iou": {"a": 0.4}, "invented_words": 0}
    bad = {"roles_present": False, "all_found": False, "iou": {"a": 0.0}, "invented_words": 2}
    assert verdict([ok] * 6)["decision"] == "go"
    assert verdict([ok] * 5 + [bad])["decision"] == "go"
    assert verdict([ok] * 4 + [bad] * 2)["decision"] == "no-go"
    assert verdict([meh] * 6)["decision"] == "partial"
    assert verdict([bad] * 6)["decision"] == "no-go"
    assert verdict([ok] * 6)["invented_words"] == 0 and verdict([bad] * 6)["invented_words"] == 12


def test_the_probe_runs_end_to_end_on_the_mock_offline():
    provider = MockProvider({"campaign_sketch": [_reply(f) for f in DEV_BANNERS]})
    rows = asyncio.run(run_dev(provider))
    assert [r["sketch"] for r in rows] == list(DEV_BANNERS)
    for _, msgs in provider.calls:  # every call carried the drawn PNG as an image part
        part = msgs[-1].content[-1]
        assert part["image_url"]["url"].startswith("data:image/png;base64,")
    assert (
        all(r["score"]["all_found"] for r in rows)
        and verdict([r["score"] for r in rows])["decision"] == "go"
    )
    md = render_markdown(rows, model="mock", spent_usd=0.0, calls=6)
    assert "Decision: go" in md and "NOT hand drawn" in md


def test_the_command_refuses_to_spend_without_live():
    r = CliRunner().invoke(app, ["eval", "campaign-sketch"])
    assert r.exit_code == 2 and "--live" in r.output
