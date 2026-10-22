"""Sealed-set tooling on a temporary toy set built from copies of public fixtures (never the real private set)."""

import json

import pytest

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.evaluation.campaign_gold import load_gold
from open_apprentice.evaluation.campaign_sealed import SealError, run_sealed, seal, validate_set


def _write(root, banner_id, src_fid, outcomes):
    (root / "banners").mkdir(parents=True, exist_ok=True)
    (root / "gold").mkdir(parents=True, exist_ok=True)
    f = load_fixture(src_fid)
    f.update(id=banner_id, expected_outcomes=list(outcomes), provenance="toy set for tests")
    (root / "banners" / f"{banner_id}.json").write_text(json.dumps(f))
    for o in outcomes:
        g = load_gold(src_fid, o)
        g["fixture"] = banner_id
        (root / "gold" / f"{banner_id}.{o}.json").write_text(json.dumps(g))


@pytest.fixture
def toy(tmp_path):
    root = tmp_path / "set"
    _write(root, "toy_short", "short_b", ["layout"])
    _write(root, "toy_long", "de_long_a", ["shrink", "split"])
    return root


def test_a_valid_set_validates_and_seals(toy, tmp_path):
    assert validate_set(toy) == []
    m = seal(toy, tmp_path / "manifest.json")
    assert len(m["files"]) == 5 and len(m["combined_sha256"]) == 64
    assert json.loads((tmp_path / "manifest.json").read_text()) == m


def test_missing_gold_is_named(toy):
    (toy / "gold" / "toy_long.split.json").unlink()
    assert any("toy_long" in p and "split" in p for p in validate_set(toy))


def test_duplicate_and_public_ids_are_refused(toy):
    b = json.loads((toy / "banners" / "toy_short.json").read_text())
    (toy / "banners" / "copy.json").write_text(json.dumps(b))
    b["id"] = "short_a"
    (toy / "banners" / "public.json").write_text(json.dumps(b))
    problems = validate_set(toy)
    assert any("duplicate" in p and "toy_short" in p for p in problems)
    assert any("public" in p and "short_a" in p for p in problems)


def test_foreign_font_and_unknown_asset_are_refused(toy):
    b = json.loads((toy / "banners" / "toy_short.json").read_text())
    for n in b["scene"]["nodes"]:
        if n["type"] == "text":
            n["fontFamily"] = "Arial"
        if n["type"] == "image":
            n["asset"] = "stock-photo"
    (toy / "banners" / "toy_short.json").write_text(json.dumps(b))
    problems = validate_set(toy)
    assert any("Arial" in p for p in problems) and any("stock-photo" in p for p in problems)


def test_sealing_refuses_an_invalid_set(toy, tmp_path):
    (toy / "gold" / "toy_short.layout.json").unlink()
    with pytest.raises(SealError):
        seal(toy, tmp_path / "manifest.json")
    assert not (tmp_path / "manifest.json").exists()


def test_a_changed_file_after_sealing_refuses_the_run_before_any_engine_call(toy, tmp_path):
    seal(toy, tmp_path / "manifest.json")
    (toy / "gold" / "toy_short.layout.json").write_text("{}")
    with pytest.raises(SealError, match="toy_short.layout.json"):
        run_sealed(
            toy, tmp_path / "manifest.json", "http://127.0.0.1:9", "unused", tmp_path / "out"
        )


def test_an_empty_or_missing_set_is_refused(tmp_path):
    assert any("no banners" in p for p in validate_set(tmp_path / "missing"))
    with pytest.raises(SealError):
        seal(tmp_path / "missing", tmp_path / "manifest.json")


def test_the_run_revalidates_a_sealed_set(toy, tmp_path):
    seal(toy, tmp_path / "manifest.json")
    b = json.loads((toy / "banners" / "toy_short.json").read_text())
    b["id"] = (
        "short_a"  # e.g. a public fixture added later with this id; the manifest is re-sealed by hand
    )
    (toy / "banners" / "toy_short.json").write_text(json.dumps(b))
    from open_apprentice.evaluation.campaign_sealed import _hashes

    m = json.loads((tmp_path / "manifest.json").read_text())
    m["files"] = _hashes(toy)
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(SealError, match="public"):
        run_sealed(
            toy, tmp_path / "manifest.json", "http://127.0.0.1:9", "unused", tmp_path / "out"
        )


def test_a_missing_manifest_is_a_plain_refusal(toy, tmp_path):
    from open_apprentice.evaluation.campaign_sealed import check_sealed

    with pytest.raises(SealError, match="no manifest"):
        check_sealed(toy, tmp_path / "absent.json")
