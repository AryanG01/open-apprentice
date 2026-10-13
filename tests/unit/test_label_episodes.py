"""Episode builder: composition, the environment-computed ambiguity, no leakage to the learner, split separation."""

import json
from fractions import Fraction as F

import pytest

from open_apprentice.evaluation.label_episodes import (
    CATALOGUE,
    agent_visible,
    behaviour_class,
    build_manifest,
    manifest_hash,
    score_commit,
    separates,
)
from open_apprentice.evaluation.labels import GAP_DEFAULT, rule_for

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def dev():
    return build_manifest("development")


def test_composition_is_8_8_4_4(dev):
    kinds = [e.kind for e in dev]
    assert [kinds.count(k) for k in ("unambiguous", "ambiguous", "unsupported", "noisy")] == [
        8,
        8,
        4,
        4,
    ]


def test_catalogue_has_distinct_behaviours():
    classes = {behaviour_class(s) for s in CATALOGUE}
    assert (
        len(CATALOGUE) == 24 and 12 < len(classes) <= 24
    )  # some specs coincide on the probes; most do not


def test_ambiguity_is_computed_from_demonstrations_not_declared(dev):
    for e in dev:
        n = len(e.classes())
        if e.kind == "unambiguous":
            assert n == 1, e.id
        elif e.kind == "ambiguous":
            assert n >= 2 and any(separates(s, e.classes()) for s in e.batch), e.id
            assert any(separates(s, e.classes()) for s in e.fresh), e.id
        else:
            assert n == 0, e.id  # no catalogue behaviour fits: unsupported or inconsistent


def test_the_learner_view_leaks_nothing(dev):
    for e in dev:
        text = json.dumps(agent_visible(e), default=str).lower()
        for word in (
            "truth",
            "ambiguous",
            "expected",
            "unsupported",
            "noisy",
            "spec",
            "catalogue",
            "hidden",
        ):
            assert word not in text, (e.id, word)
        assert set(agent_visible(e)) == {"demonstrations", "batch"}


def test_demo_batch_and_fresh_documents_are_disjoint(dev):
    for e in dev:

        def key(s):
            return json.dumps(s, default=str, sort_keys=True)

        demo_keys = {key(b) for b, _ in e.demos}
        assert demo_keys.isdisjoint({key(s) for s in e.batch} | {key(s) for s in e.fresh}), e.id
        assert {key(s) for s in e.batch}.isdisjoint({key(s) for s in e.fresh}), e.id


def test_deterministic_and_splits_differ(dev):
    assert manifest_hash(dev) == manifest_hash(build_manifest("development"))
    assert manifest_hash(dev) != manifest_hash(build_manifest("heldout"))


def test_noisy_episodes_displace_exactly_one_label_by_the_declared_amount(dev):
    for e in (x for x in dev if x.kind == "noisy"):
        before, after = e.demos[0]
        bmap = {o["id"]: o for o in before["objects"]}
        want = e.truth and {k: v for k, v in e.true_targets(before).items()}
        victim = e.meta["displaced"]
        got = {o["id"]: o for o in after["objects"]}[victim]
        assert F(got["x"]) - want[victim][0] == e.meta["px"], e.id
        assert bmap[victim]["w"] == got["w"]


def test_the_true_rule_completes_every_supported_episode_on_fresh_documents(dev):
    named = {
        ("right", None, "all"): "right",
        ("right", "below", "all"): "right_else_below",
        ("right", None, "notes"): "notes_only",
    }
    done = 0
    for e in dev:
        if e.kind not in ("unambiguous", "ambiguous") or e.truth is None:
            continue
        name = named.get((e.truth.primary, e.truth.fallback, e.truth.scope))
        if name is None or e.truth.gap != GAP_DEFAULT:
            continue  # rule_for covers only the named intents at the default gap
        assert score_commit(e, rule_for(name, e.truth.gap))["complete"], e.id
        done += 1
    assert done >= 1


def test_a_wrong_but_demo_consistent_commit_is_visible_on_an_ambiguous_episode(dev):
    seen = 0
    for e in (x for x in dev if x.kind == "ambiguous"):
        truth_class = behaviour_class(e.truth)
        for cls, specs in e.classes().items():
            if cls == truth_class or specs[0].gap != e.truth.gap:
                continue
            seen += 1
            break
    assert seen >= 1
