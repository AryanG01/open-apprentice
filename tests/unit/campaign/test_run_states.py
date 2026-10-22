import asyncio

import pytest

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.learn import learn_layout
from open_apprentice.campaign.preferences import PreferenceStore, scope_key
from open_apprentice.campaign.run import CampaignRun, Preview, answer, start_run
from open_apprentice.storage.store import LocalStore


def _question_run() -> CampaignRun:
    return CampaignRun(
        run_id="r1",
        locale="de",
        status="question",
        source_hash="abc",
        previews={
            "builtin_shrink_hero": Preview("builtin_shrink_hero", "builtin", "s1", True, []),
            "builtin_split_two_cards": Preview(
                "builtin_split_two_cards", "builtin", "s2", False, [{"kind": "x"}]
            ),
        },
    )


def test_answering_twice_is_refused(tmp_path):
    prefs = PreferenceStore(LocalStore(tmp_path))
    run = answer(
        _question_run(),
        "builtin_shrink_hero",
        prefs,
        expected_version=None,
        current_source_hash="abc",
    )
    assert run.status == "applied" and run.result_session == "s1"
    with pytest.raises(ValueError):
        answer(run, "builtin_shrink_hero", prefs, expected_version=1, current_source_hash="abc")


def test_neither_changes_nothing_and_saves_nothing(tmp_path):
    prefs = PreferenceStore(LocalStore(tmp_path))
    run = answer(
        _question_run(), "neither", prefs, expected_version=None, current_source_hash="abc"
    )
    assert run.status == "unchanged" and run.result_session is None
    assert prefs.get(scope_key("de")) is None


def test_a_preview_that_does_not_fit_cannot_be_chosen(tmp_path):
    with pytest.raises(ValueError):
        answer(
            _question_run(),
            "builtin_split_two_cards",
            PreferenceStore(LocalStore(tmp_path)),
            expected_version=None,
            current_source_hash="abc",
        )


def test_missing_role_opens_no_session(tmp_path):
    learned = asyncio.run(
        learn_layout(load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"])
    )

    def no_session(scene):
        raise AssertionError("no engine session may be opened")

    run = start_run(
        load_fixture("missing_role")["scene"],
        "en",
        learned,
        no_session,
        PreferenceStore(LocalStore(tmp_path)),
    )
    assert run.status == "needs_roles" and any("price" in p for p in run.problems)


def test_an_answer_for_a_changed_source_is_refused_and_changes_nothing(tmp_path):
    prefs = PreferenceStore(LocalStore(tmp_path))
    run = _question_run()
    with pytest.raises(ValueError, match="changed"):
        answer(
            run, "builtin_shrink_hero", prefs, expected_version=None, current_source_hash="edited"
        )
    assert run.status == "question" and prefs.get(scope_key("de")) is None
