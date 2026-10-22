"""End to end on real Konva: learn once, then run every development banner; every committed result must pass the
independent verifier against its authored gold."""

import asyncio

import pytest

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.learn import learn_layout
from open_apprentice.campaign.preferences import PreferenceStore, scope_key
from open_apprentice.campaign.run import answer, close_run, start_run
from open_apprentice.evaluation.campaign_gold import load_gold
from open_apprentice.evaluation.campaign_verifier import verify_story
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.storage.store import LocalStore

from .conftest import TOKEN

OWNER = "campaign-run"
SHRINK, SPLIT = "builtin_shrink_hero", "builtin_split_two_cards"


@pytest.fixture
def ctx(engine_url, tmp_path):
    harness = EvaluatorHarness(engine_url, TOKEN)
    learned = asyncio.run(
        learn_layout(load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"])
    )
    prefs = PreferenceStore(LocalStore(tmp_path))
    open_session = lambda scene: harness.open_session(scene, owner=OWNER)[0]

    def run(fid):
        f = load_fixture(fid)
        return f["scene"], start_run(f["scene"], f["locale"], learned, open_session, prefs)

    def verified(fid, outcome, src, r):
        native = harness.native(r.result_session, OWNER)
        report = verify_story(src, native, load_gold(fid, outcome)["scene"])
        assert report.passed, (fid, outcome, report.failed())

    return run, verified, prefs


def test_short_banners_take_the_learned_layout(ctx):
    run, verified, _ = ctx
    for fid in ("short_a", "short_b"):
        src, r = run(fid)
        try:
            assert r.status == "ready", (fid, r.problems)
            verified(fid, "layout", src, r)
            assert (
                r.provenance["learned_origin"] == "search"
                and r.provenance["procedure_origin"] == "reference"
            )
        finally:
            close_run(r)


def test_question_answer_and_reuse(ctx):
    run, verified, prefs = ctx
    src, r = run("de_long_a")
    try:
        assert r.status == "question"
        assert r.previews[SHRINK].fits and r.previews[SPLIT].fits
        r = answer(r, SHRINK, prefs, expected_version=None)
        assert r.status == "applied" and r.provenance["outcome_origin"] == "builtin"
        verified("de_long_a", "shrink", src, r)
    finally:
        close_run(r)
    assert prefs.get(scope_key("de")).outcome == SHRINK

    src, r = run("de_long_b")  # preference says shrink, but shrink does not fit: ask again
    try:
        assert r.status == "question" and not r.previews[SHRINK].fits and r.previews[SPLIT].fits
        r = answer(r, SPLIT, prefs, expected_version=1)
        verified("de_long_b", "split", src, r)
    finally:
        close_run(r)
    assert prefs.get(scope_key("de")).version == 2

    src, r = run("de_long_a")  # now the saved split preference applies without a question
    try:
        assert r.status == "applied" and r.preference.outcome == SPLIT
        verified("de_long_a", "split", src, r)
    finally:
        close_run(r)

    _, r = run("fr_long")  # the German preference does not apply to French
    try:
        assert r.status == "question"
    finally:
        close_run(r)


def test_a_tool_error_midway_fails_the_run_and_closes_its_sessions(engine_url, tmp_path):
    import copy

    from open_apprentice.campaign.learn import Learned

    harness = EvaluatorHarness(engine_url, TOKEN)
    learned = asyncio.run(
        learn_layout(load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"])
    )
    rule = copy.deepcopy(learned.rule)
    for stmt in rule[0]["body"]:
        if stmt["cond"]["args"][1] == "headline":
            stmt["then"][0]["z"] = 50  # valid rule, but set_order refuses an out-of-range index
    src = load_fixture("short_a")["scene"]
    r = start_run(
        src,
        "en",
        Learned(rule, "search"),
        lambda s: harness.open_session(s, owner=OWNER)[0],
        PreferenceStore(LocalStore(tmp_path)),
    )
    assert r.status == "failed" and "z must be" in r.problems[0]
    assert r.sessions == {} and r.result_session is None
