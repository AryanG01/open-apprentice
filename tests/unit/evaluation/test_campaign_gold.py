from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.evaluation.campaign_gold import GOLD_KEYS, load_gold

COPY_ROLES = ("headline", "price", "legal")


def _copy(scene: dict) -> dict:
    """Role -> text for top-level copy, plus the CTA label and link."""
    nodes = scene["nodes"]
    out = {n["role"]: n["text"] for n in nodes if n.get("role") in COPY_ROLES}
    cta = next(n for n in nodes if n.get("role") == "cta")
    out["cta_label"] = next(
        n["text"] for n in nodes if n.get("parent") == cta["id"] and n["type"] == "text"
    )
    out["link"] = cta["link"]
    return out


def test_every_gold_key_loads():
    assert ("short_a", "layout") in GOLD_KEYS and ("de_long_b", "split") in GOLD_KEYS
    for fid, outcome in GOLD_KEYS:
        g = load_gold(fid, outcome)
        assert g is None or g["scene"]["nodes"], (fid, outcome)


def test_shrink_is_not_applicable_for_de_long_b():
    assert load_gold("de_long_b", "shrink") is None


def test_gold_copy_equals_fixture_copy():
    for fid, outcome in GOLD_KEYS:
        g = load_gold(fid, outcome)
        if g is not None:
            assert _copy(g["scene"]) == _copy(load_fixture(fid)["scene"]), (fid, outcome)


def test_split_golds_have_two_sequenced_cards():
    for fid, outcome in GOLD_KEYS:
        if outcome != "split":
            continue
        boards = [n for n in load_gold(fid, outcome)["scene"]["nodes"] if n["type"] == "artboard"]
        assert sorted(b["sequence"] for b in boards) == [1, 2], fid
        assert all((b["width"], b["height"]) == (1080, 1920) for b in boards), fid


def test_teaching_pair_is_its_own_gold():
    assert load_gold("teach_before", "layout")["scene"] == load_fixture("teach_after")["scene"]


def test_gold_is_returned_as_a_fresh_copy():
    load_gold("short_a", "layout")["scene"]["nodes"].clear()
    assert load_gold("short_a", "layout")["scene"]["nodes"]
