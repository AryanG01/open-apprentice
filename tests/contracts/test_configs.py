"""Every protocol config declares what spec 24.5 requires, and budgets stay consistent."""

import pathlib

import pytest
import yaml

CONFIGS = sorted(pathlib.Path("configs").glob("*.yaml"))
REQUIRED = {"protocol", "primary_comparison", "model", "budgets", "supported_domain"}


def test_all_five_configs_exist():
    assert {p.stem for p in CONFIGS} == {"dev", "pilot", "counterexample", "portable", "final"}


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_declares_required_sections(path):
    cfg = yaml.safe_load(path.read_text())
    assert REQUIRED <= cfg.keys()


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_c_ref_matches_episode_cap(path):
    b = yaml.safe_load(path.read_text())["budgets"]
    assert b["c_ref_token_units"] == b["episode_total_tokens"] // b["scored_tasks_per_episode"]


def test_final_is_unfrozen_until_freeze_commit():
    cfg = yaml.safe_load(pathlib.Path("configs/final.yaml").read_text())
    assert cfg["freeze"]["frozen"] is False and cfg["freeze"]["freeze_commit"] is None


def test_counterexample_episode_split():
    cfg = yaml.safe_load(pathlib.Path("configs/counterexample.yaml").read_text())
    assert cfg["no_change_episodes"] + cfg["drift_episodes"] == cfg["episodes"] == 12
    assert (cfg["no_change_episodes"], cfg["drift_episodes"]) == (4, 8)
