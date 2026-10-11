import json
import subprocess
import sys

from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.evaluation.episodes import (
    BADGE_TEMPLATES,
    STAGES,
    WIDTH_RANGE,
    agent_visible,
    make_manifest,
)

DOM = DomainManifest()
SPLITS = ("development", "validation", "final")


def test_manifest_shape_and_balance():
    m = make_manifest("final", 0, 12)
    assert len(m.episodes) == 12 and all(len(e.tasks) == 8 for e in m.episodes)
    assert [t.stage for t in m.episodes[0].tasks] == list(STAGES)
    assert (
        sum(e.drift is None for e in m.episodes) == 4
        and sum(e.drift is not None for e in m.episodes) == 8
    )
    for parity in (0, 1):  # balanced across backend direction
        eps = [e for e in m.episodes if e.index % 2 == parity]
        assert sum(e.drift is None for e in eps) == 2 and sum(e.drift is not None for e in eps) == 4
    assert {(e.source_backend, e.target_backend) for e in m.episodes} == {
        ("konva", "fabric"),
        ("fabric", "konva"),
    }


def test_templates_and_snapshots_are_disjoint_across_splits():
    ms = {s: make_manifest(s, 0, 12) for s in SPLITS}
    for a in SPLITS:
        for b in SPLITS:
            if a < b:
                assert not ms[a].template_ids() & ms[b].template_ids()
                assert not ms[a].snapshot_hashes() & ms[b].snapshot_hashes()
    assert set(BADGE_TEMPLATES["final"]) == {"clamp", "affine"} and not set(
        BADGE_TEMPLATES["final"]
    ) & set(BADGE_TEMPLATES["development"])


def test_final_split_holds_out_object_size_ranges():
    dev_lo, dev_hi = WIDTH_RANGE["development"]
    ws = {
        int(o["w"])
        for e in make_manifest("final", 0, 12).episodes
        for t in e.tasks
        for o in t.scene["objects"]
        if o["id"].startswith("card")
    }
    assert any(w < dev_lo for w in ws) and any(w >= 200 for w in ws)
    dev = {
        int(o["w"])
        for e in make_manifest("development", 0, 12).episodes
        for t in e.tasks
        for o in t.scene["objects"]
        if o["id"].startswith("card")
    }
    assert all(dev_lo <= w < dev_hi for w in dev)


def test_every_task_is_inside_the_declared_symbolic_domain_and_rows_fit_the_canvas():
    for s in SPLITS:
        for e in make_manifest(s, 0, 12).episodes:
            for t in e.tasks:
                cards = [o for o in t.scene["objects"] if o["id"] in t.selected]
                assert DOM.contains(cards, t.scene["canvas"]), (s, e.index, t.task_id)
                out = evaluate_rule(e.spacing, cards, t.scene["canvas"])
                assert all(o["x"] + o["w"] <= t.scene["canvas"]["w"] for o in out.values())


def test_demonstrations_are_consistent_with_the_private_latent_rules():
    for e in make_manifest("development", 0, 4).episodes:
        for name, rule in (("spacing", e.spacing), ("badge", e.badge)):
            d = e.demos[name]
            assert evaluate_rule(rule, d["scene"]["objects"], d["scene"]["canvas"]) == d["after"]


def test_agent_view_contains_no_evaluator_only_information():
    m = make_manifest("final", 0, 12)
    for e in m.episodes:
        for t in e.tasks:
            v = json.dumps(agent_visible(t)).lower()
            for secret in (
                t.stage,
                e.episode_id,
                e.split,
                "drift",
                "template",
                "latent",
                "recovery",
                "move_origin",
                "move_anchor",
                "clamp",
                "affine",
                "edge",
                "pitch",
                "same_backend",
                "transfer",
            ):
                assert secret not in v, (secret, v[:200])
    ids = [t.task_id for e in m.episodes for t in e.tasks]
    assert len(set(ids)) == len(ids)


def test_manifest_hash_is_deterministic_across_processes_and_hash_seeds():
    code = "from open_apprentice.evaluation.episodes import make_manifest;print(make_manifest('final',3,12).content_hash())"
    outs = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "src", "PYTHONHASHSEED": h},
        ).stdout.strip()
        for h in ("0", "7", "99")
    }
    assert len(outs) == 1 and len(next(iter(outs))) == 64
    assert (
        make_manifest("final", 3, 12).content_hash() != make_manifest("final", 4, 12).content_hash()
    )


def test_freeze_records_hash_and_detects_later_edits():
    m = make_manifest("final", 0, 12)
    assert not m.verify_frozen()
    h = m.freeze("abc123")
    assert m.verify_frozen() and m.freeze_info == {"commit": "abc123", "hash": h}
    m.episodes[0].tasks[0].scene["objects"][0]["w"] += 10  # tamper with a frozen manifest
    assert not m.verify_frozen()
