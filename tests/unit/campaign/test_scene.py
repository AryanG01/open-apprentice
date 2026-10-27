import pytest

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.limits import ROLES, fit_limits
from open_apprentice.campaign.scene import RoleError, role_map


def test_teach_after_has_every_role_once():
    roles = role_map(load_fixture("teach_after")["scene"], "story-1")
    assert set(roles) == set(ROLES)


def test_missing_role_is_named():
    with pytest.raises(RoleError) as e:
        role_map(load_fixture("missing_role")["scene"], "banner")
    assert any("headline" in p and "missing" in p for p in e.value.problems)


def test_duplicate_role_is_named():
    with pytest.raises(RoleError) as e:
        role_map(load_fixture("duplicate_role")["scene"], "banner")
    assert any("headline" in p and "more than one" in p for p in e.value.problems)


def test_fit_limits_match_the_frozen_values():
    assert fit_limits() == {
        "safe": {"top": 220, "right": 72, "bottom": 220, "left": 72},
        "min_font": 40,
        "min_legal_font": 24,
        "min_cta_height": 96,
        "min_hero_width": 432,
        "min_hero_tall_height": 480,  # 27 Oct amendment: width OR height; every earlier result passes both versions
    }
