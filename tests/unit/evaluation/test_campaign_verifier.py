import copy
import unicodedata

import pytest

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.evaluation.campaign_gold import GOLD_KEYS, load_gold
from open_apprentice.evaluation.campaign_verifier import verify_story

APPLICABLE = [(f, o) for f, o in GOLD_KEYS if load_gold(f, o) is not None]


def _case(fid: str, outcome: str):
    gold = load_gold(fid, outcome)["scene"]
    return load_fixture(fid)["scene"], copy.deepcopy(gold), gold


def _node(scene: dict, role: str, board: str = "story-1") -> dict:
    return next(n for n in scene["nodes"] if n.get("role") == role and n.get("parent") == board)


@pytest.mark.parametrize("fid,outcome", APPLICABLE)
def test_gold_result_passes_every_check(fid, outcome):
    source, final, gold = _case(fid, outcome)
    report = verify_story(source, final, gold)
    assert report.passed, report.failed()
    assert len(report.checks) == 15


def _fails(check: str, fid: str, outcome: str, mutate) -> None:
    source, final, gold = _case(fid, outcome)
    mutate(final)
    report = verify_story(source, final, gold)
    assert check in report.failed(), (check, report.failed())


def test_nfd_copy_fails_exact_copy():
    def m(s):
        n = _node(s, "headline")
        n["text"] = unicodedata.normalize("NFD", n["text"])

    _fails("exact_copy", "de_long_a", "split", m)


def test_trailing_space_fails_exact_copy():
    _fails(
        "exact_copy",
        "short_a",
        "layout",
        lambda s: _node(s, "headline").update(text=_node(s, "headline")["text"] + " "),
    )


def test_duplicated_price_fails_copy_once():
    def m(s):
        dup = dict(
            _node(s, "price", "story-2"), id="dup-price", parent="story-2", y=1100, role=None
        )
        s["nodes"].append(dup)

    _fails("copy_once", "de_long_a", "split", m)


def test_changed_link_fails_link_preserved():
    _fails(
        "link_preserved",
        "short_a",
        "layout",
        lambda s: _node(s, "cta").update(link="https://evil.example/"),
    )


def test_swapped_logo_fails_logo_preserved():
    _fails(
        "logo_preserved",
        "short_a",
        "layout",
        lambda s: _node(s, "brand_mark").update(asset="h7-headphones"),
    )


def test_squashed_image_fails_image_aspect():
    _fails(
        "image_aspect", "short_a", "layout", lambda s: _node(s, "product_image").update(height=700)
    )


def test_cropped_image_fails_image_uncropped():
    crop = {"x": 0, "y": 0, "width": 500, "height": 500}
    _fails(
        "image_uncropped",
        "short_a",
        "layout",
        lambda s: _node(s, "product_image").update(crop=crop),
    )


def test_focal_point_off_card_fails_focal_visible():
    _fails("focal_visible", "short_a", "layout", lambda s: _node(s, "product_image").update(x=-700))


def test_legal_above_cta_fails_role_order():
    _fails("role_order", "short_a", "layout", lambda s: _node(s, "legal").update(y=1290))


def test_repeated_sequence_fails_card_sequence():
    _fails(
        "card_sequence",
        "de_long_a",
        "split",
        lambda s: next(n for n in s["nodes"] if n["id"] == "story-2").update(sequence=1),
    )


def test_logo_in_top_margin_fails_inside_safe():
    _fails("inside_safe", "short_a", "layout", lambda s: _node(s, "brand_mark").update(y=100))


def test_small_legal_font_fails_minimum_sizes():
    _fails("minimum_sizes", "short_a", "layout", lambda s: _node(s, "legal").update(fontSize=20))


def test_short_headline_frame_fails_text_fits():
    _fails("text_fits", "de_long_a", "shrink", lambda s: _node(s, "headline").update(height=80))


def test_price_over_cta_fails_no_overlap():
    _fails("no_overlap", "short_a", "layout", lambda s: _node(s, "price").update(y=1380))


def test_recoloured_headline_fails_non_writable_unchanged():
    _fails(
        "non_writable_unchanged",
        "short_a",
        "layout",
        lambda s: _node(s, "headline").update(fill="#ff0000"),
    )


def test_nudged_headline_fails_matches_gold():
    _fails("matches_gold", "short_a", "layout", lambda s: _node(s, "headline").update(y=1085))


def test_no_gold_means_no_commit():
    source, final, _ = _case("de_long_a", "shrink")
    assert "matches_gold" in verify_story(source, final, None).failed()


def test_unexpected_extra_node_fails_non_writable_unchanged():
    def m(s):
        s["nodes"].append(
            {
                "id": "stray",
                "type": "rect",
                "parent": "story-1",
                "x": 0,
                "y": 0,
                "width": 1,
                "height": 1,
            }
        )

    _fails("non_writable_unchanged", "short_a", "layout", m)


# Final review fixes (scale, safe-area source, no-break spaces).
def test_scaled_down_legal_fails_minimum_sizes():
    _fails(
        "minimum_sizes",
        "short_a",
        "layout",
        lambda s: _node(s, "legal").update(scaleX=0.5, scaleY=0.5),
    )


def test_squashing_scale_fails_image_aspect():
    _fails(
        "image_aspect", "short_a", "layout", lambda s: _node(s, "product_image").update(scaleY=0.5)
    )


def test_scaled_up_image_pushes_focal_off_card():
    _fails(
        "focal_visible",
        "short_a",
        "layout",
        lambda s: _node(s, "product_image").update(scaleX=3, scaleY=3),
    )


def test_missing_safe_metadata_does_not_switch_off_inside_safe():
    def m(s):
        del next(n for n in s["nodes"] if n["id"] == "story-1")["safe"]
        _node(s, "brand_mark").update(y=100)

    _fails("inside_safe", "short_a", "layout", m)


def test_altered_safe_metadata_fails_card_sequence():
    _fails(
        "card_sequence",
        "short_a",
        "layout",
        lambda s: next(n for n in s["nodes"] if n["id"] == "story-1").update(safe={}),
    )
