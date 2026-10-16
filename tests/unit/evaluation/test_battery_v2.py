import json
from collections import Counter
from functools import lru_cache

import pytest

from open_apprentice.evaluation.battery_v2 import (
    FrozenMismatch,
    build_battery,
    episode_from_json,
    episode_to_json,
    freeze,
    learner_view,
    verify_frozen,
)
from open_apprentice.evaluation.label_episodes import consistent_classes


TEST_FINAL_BASE = (
    170_000  # a stand-in: the real final seed base is drawn at freeze time and kept private
)


@lru_cache(maxsize=None)
def _battery(split):
    return tuple(build_battery(split, TEST_FINAL_BASE if split == "final" else None))


def test_the_final_split_cannot_be_rebuilt_without_its_private_seed_base():
    with pytest.raises(ValueError, match="seed base"):
        build_battery("final")


def _demos(ep):
    return list(zip(ep.demo_scenes, ep.demo_outputs))


def test_final_split_has_the_spec_strata_counts():
    eps = _battery("final")
    assert len(eps) == 36
    assert Counter(e.stratum for e in eps) == {
        "catalogue": 8,
        "beyond": 8,
        "inconsistent": 4,
        "unsupported": 4,
        "sequential": 12,
    }
    cat = [e for e in eps if e.stratum == "catalogue"]
    assert sum(e.clarification_required for e in cat) == 4
    beyond = {e.spec for e in eps if e.stratum == "beyond"}
    assert len({s.kind for s in beyond}) >= 4
    kinds = Counter(e.correction["kind"] for e in eps if e.stratum == "sequential")
    assert kinds["compatible"] + kinds["superseding"] == 8
    assert kinds["conflict"] + kinds["override"] + kinds["accidental"] == 4


def test_dev_split_is_half_size_with_the_same_strata():
    eps = _battery("dev")
    assert len(eps) == 18
    assert Counter(e.stratum for e in eps) == {
        "catalogue": 4,
        "beyond": 4,
        "inconsistent": 2,
        "unsupported": 2,
        "sequential": 6,
    }


def test_dev_and_final_seeds_are_disjoint_and_ids_unique():
    dev, final = _battery("dev"), _battery("final")
    assert not {e.seed for e in dev} & {e.seed for e in final}
    ids = [e.id for e in dev + final]
    assert len(set(ids)) == len(ids)


def test_battery_is_deterministic():
    assert [episode_to_json(e) for e in build_battery("dev")] == [
        episode_to_json(e) for e in _battery("dev")
    ]


def test_episode_json_round_trips():
    for ep in _battery("dev"):
        assert episode_to_json(episode_from_json(episode_to_json(ep))) == episode_to_json(ep)


def test_learner_view_holds_no_spec_scoring_or_marks():
    for ep in _battery("dev") + _battery("final"):
        view = learner_view(ep)
        blob = json.dumps(view)
        for key in (
            "spec",
            "scoring",
            "stratum",
            "clarification_required",
            "selector",
            "diagnostic",
            "seed",
            "meta",
        ):
            assert f'"{key}' not in blob, (ep.id, key)
        assert set(view) == {"id", "scenes", "demonstrations", "batch", "correction"}
        assert view["id"] == ep.id
        if view["correction"] is not None:
            assert set(view["correction"]) == {"scene_id", "corrected_output", "mask"}
            assert set(view["correction"]["corrected_output"]) == set(view["correction"]["mask"])
        assert {d["scene_id"] for d in view["demonstrations"]} | set(view["batch"]) <= set(
            view["scenes"]
        )


def test_clarification_marks_match_catalogue_fits():
    for ep in _battery("dev") + _battery("final"):
        fits = len(consistent_classes(_demos(ep)))
        assert ep.clarification_required == (fits >= 2), ep.id


def test_inconsistent_episodes_share_inputs_with_incompatible_outputs():
    for ep in (e for e in _battery("final") + _battery("dev") if e.stratum == "inconsistent"):
        a, b = ep.demo_scenes
        assert a == b
        assert ep.demo_outputs[0] != ep.demo_outputs[1]


def test_beyond_demonstrations_fit_no_catalogue_behaviour():
    for ep in (e for e in _battery("final") if e.stratum == "beyond"):
        assert consistent_classes(_demos(ep)) == {}


def test_sequential_episodes_carry_a_correction_script():
    for ep in (e for e in _battery("final") if e.stratum == "sequential"):
        c = ep.correction
        assert c["mask"] and c["scene"] and c["corrected_output"]
        if c["kind"] in ("compatible", "superseding", "conflict"):
            assert c["selector"] and c["spec"] is not None and c["diagnostic_scenes"]
        else:
            assert c["selector"] is None and c["spec"] is None


def test_freeze_writes_private_and_learner_files_and_verifies(tmp_path):
    hashes = freeze("dev", tmp_path)
    assert (tmp_path / "manifest.private.json").exists()
    public = json.loads((tmp_path / "manifest.public.json").read_text())
    assert set(public) == {"split", "episodes"}
    assert len(public["episodes"]) == 18
    assert len(list((tmp_path / "learner").glob("*.json"))) == 18
    assert len(list((tmp_path / "episodes").glob("*.private.json"))) == 18
    assert "manifest.private.json" in hashes
    assert verify_frozen(tmp_path) == hashes


def test_one_changed_byte_fails_verification(tmp_path):
    freeze("dev", tmp_path)
    victim = sorted((tmp_path / "episodes").glob("*.private.json"))[3]
    raw = bytearray(victim.read_bytes())
    raw[-2] = ord(" ") if raw[-2] != ord(" ") else ord("\t")
    victim.write_bytes(bytes(raw))
    with pytest.raises(FrozenMismatch):
        verify_frozen(tmp_path)


def test_a_changed_manifest_fails_against_recorded_hashes(tmp_path):
    hashes = freeze("dev", tmp_path)
    m = tmp_path / "manifest.private.json"
    m.write_text(m.read_text().replace('"dev"', '"dew"', 1))
    with pytest.raises(FrozenMismatch):
        verify_frozen(tmp_path, expected=hashes)


def test_cli_freeze_prints_hashes_that_verify(tmp_path):
    from typer.testing import CliRunner

    from open_apprentice.cli import app

    r = CliRunner().invoke(app, ["eval", "freeze", "--split", "dev", "--out", str(tmp_path)])
    assert r.exit_code == 0, r.output
    printed = json.loads(r.output)
    assert printed["hashes"] == verify_frozen(tmp_path)
