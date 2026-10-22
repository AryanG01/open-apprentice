import pytest

from open_apprentice.campaign.preferences import PreferenceConflict, PreferenceStore, scope_key
from open_apprentice.storage.store import LocalStore

DE = scope_key("de")


def _prefs(tmp_path):
    return PreferenceStore(LocalStore(tmp_path))


def test_set_then_get(tmp_path):
    p = _prefs(tmp_path)
    assert p.get(DE) is None
    v1 = p.set(DE, "builtin_shrink_hero", {"run_id": "r1"}, expected_version=None)
    assert (v1.version, v1.parent, v1.outcome) == (1, None, "builtin_shrink_hero")
    assert p.get(DE) == v1


def test_stale_expected_version_conflicts(tmp_path):
    p = _prefs(tmp_path)
    p.set(DE, "builtin_shrink_hero", {}, expected_version=None)
    with pytest.raises(PreferenceConflict):
        p.set(DE, "builtin_split_two_cards", {}, expected_version=None)
    assert p.set(DE, "builtin_split_two_cards", {}, expected_version=1).parent == 1


def test_rollback_restores_and_keeps_history(tmp_path):
    p = _prefs(tmp_path)
    p.set(DE, "builtin_shrink_hero", {}, expected_version=None)
    p.set(DE, "builtin_split_two_cards", {}, expected_version=1)
    back = p.rollback(DE, to_version=1, expected_version=2)
    assert back.outcome == "builtin_shrink_hero" and p.get(DE).version == 1
    assert [h.version for h in p.history(DE)] == [1, 2]
    with pytest.raises(PreferenceConflict):
        p.rollback(DE, to_version=2, expected_version=2)


def test_unknown_outcome_is_refused(tmp_path):
    with pytest.raises(ValueError):
        _prefs(tmp_path).set(DE, "neither", {}, expected_version=None)


def test_scopes_are_per_locale(tmp_path):
    p = _prefs(tmp_path)
    p.set(DE, "builtin_shrink_hero", {}, expected_version=None)
    assert scope_key("de") != scope_key("fr") and p.get(scope_key("fr")) is None
    assert scope_key("de") == "promo_card/9:16/overflow/de"


def test_an_orphaned_version_from_a_lost_race_does_not_block_the_locale(tmp_path):
    store = LocalStore(tmp_path)
    p = PreferenceStore(store)
    p.set(DE, "builtin_shrink_hero", {}, expected_version=None)
    store.create(
        f"campaign/preferences/{DE}/v2.json", b"{}"
    )  # a writer created v2, then lost the pointer race
    v = p.set(DE, "builtin_split_two_cards", {}, expected_version=1)
    assert v.version == 3 and p.get(DE).outcome == "builtin_split_two_cards"
    assert p.set(DE, "builtin_shrink_hero", {}, expected_version=3).version == 4
