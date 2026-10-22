from open_apprentice.campaign.fixtures import FIXTURE_IDS, load_fixture

EXPECTED = {
    "teach_before",
    "teach_after",
    "short_a",
    "short_b",
    "de_long_a",
    "de_long_b",
    "fr_long",
    "missing_role",
    "duplicate_role",
}


def test_every_fixture_is_listed_and_loads():
    assert set(FIXTURE_IDS) == EXPECTED
    for fid in FIXTURE_IDS:
        f = load_fixture(fid)
        assert f["locale"] in {"en", "de", "fr"}
        assert f["provenance"] == "authored in-repo, development fixture, not held out"


def test_text_uses_only_the_vendored_font():
    for fid in FIXTURE_IDS:
        for n in load_fixture(fid)["scene"]["nodes"]:
            if n["type"] == "text":
                assert n["fontFamily"] == "Liberation Sans", (fid, n["id"])


def test_load_returns_independent_copies():
    a = load_fixture("short_a")
    a["scene"]["nodes"].clear()
    assert load_fixture("short_a")["scene"]["nodes"]


def test_short_fixtures_use_their_own_node_ids():
    ids = {
        fid: {n["id"] for n in load_fixture(fid)["scene"]["nodes"] if n["type"] != "artboard"}
        for fid in ("teach_before", "short_a", "short_b")
    }
    assert not ids["teach_before"] & ids["short_a"]
    assert not ids["short_a"] & ids["short_b"]


def test_teach_after_layout_is_the_taught_story():
    all_nodes = load_fixture("teach_after")["scene"]["nodes"]
    nodes = {n.get("role"): n for n in all_nodes if n.get("role")}
    plate = next(n for n in all_nodes if n["id"] == "tb-cta-plate")

    def box(r):
        n = nodes[r]
        if r == "cta":
            return (n["x"], n["y"], plate["width"], plate["height"])
        return (n["x"], n["y"], n["width"], n["height"])

    assert box("brand_mark") == (72, 220, 240, 60)
    assert box("product_image") == (180, 320, 720, 720)
    assert box("headline") == (72, 1080, 936, 160)
    assert box("price") == (72, 1256, 936, 72)
    assert box("cta") == (72, 1360, 936, 112)
    assert box("legal") == (72, 1540, 936, 160)
