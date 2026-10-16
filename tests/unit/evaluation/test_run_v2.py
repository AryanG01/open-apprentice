import json
from pathlib import Path
from functools import lru_cache

import pytest

from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.evaluation.battery_v2 import FrozenMismatch, build_battery, freeze
from open_apprentice.evaluation.label_episodes import consistent_classes
from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.evaluation.run_v2 import load_split, run_battery, score
from open_apprentice.evaluation.specs_v2 import oracle_v


@lru_cache(maxsize=None)
def _dev():
    return tuple(build_battery("dev"))


def _outcome(status, rule=None, correction=None, events=()):
    return {
        "status": status,
        "program": {"rule": rule} if rule is not None else None,
        "correction": correction,
        "events": list(events),
        "boundary_violation": False,
        "reason": None,
        "usage": {},
        "spend": {},
    }


def test_a_program_that_fits_the_demonstrations_but_not_a_fresh_document_is_wrong_commit():
    ep = next(e for e in _dev() if e.stratum == "catalogue" and e.clarification_required)
    truth = ep.spec.params[0]
    demos = list(zip(ep.demo_scenes, ep.demo_outputs))
    other = next(
        specs[0]
        for specs in consistent_classes(demos).values()
        if truth not in specs
        and any(
            oracle_v(ep.spec, s) != oracle_v(type(ep.spec)("catalogue", (specs[0],)), s)
            for s in ep.scoring_scenes
        )
    )
    assert (
        score(ep, _outcome("committed", rule_for_spec(other)))["terminal_outcome"] == "wrong_commit"
    )
    assert (
        score(ep, _outcome("committed", rule_for_spec(truth)))["terminal_outcome"]
        == "correct_complete"
    )


def test_abstaining_where_a_correct_program_exists_is_unnecessary_abstention():
    ep = next(e for e in _dev() if e.stratum == "beyond")
    assert score(ep, _outcome("abstained"))["terminal_outcome"] == "unnecessary_abstention"


def test_inconsistent_episode_surfaced_conflict_is_appropriate_refusal():
    ep = next(e for e in _dev() if e.stratum == "inconsistent")
    assert score(ep, _outcome("abstained"))["terminal_outcome"] == "appropriate_refusal"
    rule = rule_for_spec(ep.spec.params[0])
    assert score(ep, _outcome("committed", rule))["terminal_outcome"] == "wrong_commit"


def test_unsupported_refusals_pass_and_commits_fail():
    for ep in (e for e in _dev() if e.stratum == "unsupported"):
        assert score(ep, _outcome("abstained"))["terminal_outcome"] == "appropriate_refusal"
        spec = ep.spec.params[0] if ep.spec.kind == "catalogue" else Spec()
        assert (
            score(ep, _outcome("committed", rule_for_spec(spec)))["terminal_outcome"]
            == "wrong_commit"
        )


def test_learner_errors_and_boundary_violations_are_error():
    ep = _dev()[0]
    o = _outcome("error")
    o["boundary_violation"] = True
    s = score(ep, o)
    assert s["terminal_outcome"] == "error" and "boundary_violation" in s["release_blocking"]


WARN_BELOW = """for o in objects {{
  if o.kind == "label" {{
    let a = object(o.attached)
    if o.role == "warning" {{
      move o to (a.x + (a.w - o.w) / 2, a.y + a.h + {g})
    }} else {{
      move o to (a.x + a.w + {g}, a.y + (a.h - o.h) / 2)
    }}
  }}
}}"""


def test_sequential_scores_acquisition_and_correction_separately():
    ep = next(
        e
        for e in _dev()
        if e.stratum == "sequential"
        and e.correction["template"] == "warn_below"
        and e.correction["kind"] == "compatible"
    )
    base = rule_for_spec(ep.spec.params[0])
    g = int(ep.spec.params[0].gap)
    fixed = parse_rule_text(WARN_BELOW.format(g=g))
    good = score(
        ep, _outcome("committed", base, {"status": "activated", "program": {"rule": fixed}})
    )
    assert good["correction"]["acquired"] and good["correction"]["success"]
    assert good["terminal_outcome"] == "correct_complete"
    same = score(
        ep, _outcome("committed", base, {"status": "activated", "program": {"rule": base}})
    )
    assert same["correction"]["acquired"] and not same["correction"]["success"]
    assert same["correction"]["retention_ok"] and not same["correction"]["scope_ok"]
    assert same["terminal_outcome"] == "wrong_commit"
    lost = score(ep, _outcome("abstained"))
    assert not lost["correction"]["acquired"] and lost["correction"]["success"] is None


@pytest.mark.parametrize("kind,status", [("override", "override"), ("accidental", "dismissed")])
def test_override_and_accidental_succeed_only_without_a_skill_change(kind, status):
    ep = next(e for e in _dev() if e.stratum == "sequential" and e.correction["kind"] == kind)
    base = rule_for_spec(ep.spec.params[0])
    ok = score(ep, _outcome("committed", base, {"status": status, "program": None}))
    assert ok["correction"]["success"] and ok["terminal_outcome"] == "correct_complete"
    bad = score(ep, _outcome("committed", base, {"status": "activated", "program": {"rule": base}}))
    assert not bad["correction"]["success"]


def test_a_changed_frozen_file_is_refused_before_any_run(tmp_path):
    hashes = freeze("dev", tmp_path)
    assert len(load_split(tmp_path, hashes)) == 18
    victim = sorted((tmp_path / "learner").glob("*.json"))[0]
    victim.write_bytes(victim.read_bytes() + b" ")
    with pytest.raises(FrozenMismatch):
        load_split(tmp_path, hashes)


def test_mock_run_over_the_dev_battery_labels_every_row(tmp_path):
    out = run_battery("dev", ["A", "C", "D"], repeats=1, mode="mock", out_root=tmp_path)
    rows = [json.loads(x) for x in (out / "rows.jsonl").read_text().splitlines()]
    assert len(rows) == 54
    assert {(r["origin"], r["model"]) for r in rows} == {("mock", "Fixture")}
    assert all(
        r["terminal_outcome"]
        in (
            "correct_complete",
            "wrong_commit",
            "appropriate_refusal",
            "unnecessary_abstention",
            "error",
        )
        for r in rows
    )
    assert not any("boundary_violation" in r["release_blocking"] for r in rows)
    manifest = json.loads((out / "manifest.json").read_text())
    assert (
        manifest["split"] == "dev"
        and manifest["mode"] == "mock"
        and manifest["systems"] == ["A", "C", "D"]
    )


def test_cli_run_writes_rows_for_the_chosen_episodes(tmp_path):
    from typer.testing import CliRunner

    from open_apprentice.cli import app

    ep = _dev()[2]
    r = CliRunner().invoke(app, ["eval", "run", "--split", "dev", "--systems", "A,C", "--repeats", "1",
                                 "--mode", "mock", "--episodes", ep.id, "--out", str(tmp_path)])  # fmt: skip
    assert r.exit_code == 0, r.output
    out = Path(json.loads(r.output)["run_dir"])
    rows = [json.loads(x) for x in (out / "rows.jsonl").read_text().splitlines()]
    assert [x["method"] for x in rows] == ["A", "C"] and {x["episode"] for x in rows} == {ep.id}


def test_boundary_refusals_and_loaded_evaluator_modules_are_release_blocking():
    ep = _dev()[0]
    refused = _outcome("error") | {"refused": True, "boundary_refusal": True}
    loaded = _outcome("abstained") | {"evaluator_modules": ["open_apprentice.evaluation.labels"]}
    for o in (refused, loaded):
        s = score(ep, o)
        assert s["terminal_outcome"] == "error" and "boundary_violation" in s["release_blocking"]


def test_the_final_split_is_refused_outside_the_gated_live_run(tmp_path):
    with pytest.raises(PermissionError, match="final"):
        run_battery("final", ["C"], repeats=1, mode="mock", out_root=tmp_path)
