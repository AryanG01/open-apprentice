import json
from dataclasses import asdict
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


def test_live_runner_alternates_systems_and_stops_at_the_cap(tmp_path, monkeypatch):
    import open_apprentice.evaluation.run_v2 as rv
    from open_apprentice.evaluation.metrics import Row  # noqa: F401

    root = tmp_path / "budget"
    root.mkdir()
    spend = root / "spend.jsonl"
    calls = []

    def fake(
        ep,
        system,
        mode,
        seed,
        repeat,
        out_dir,
        model="Fixture",
        extra=(),
        wall_s=0,
        engine_url=None,
    ):
        calls.append((ep.id, system, dict(zip(extra[::2], extra[1::2]))["--cap-usd"]))
        with open(spend, "a") as f:  # every run spends 0.3 of the run id's money
            f.write(
                json.dumps({"run": dict(zip(extra[::2], extra[1::2]))["--run-id"], "usd": 0.3})
                + "\n"
            )
        return rv.RowV2(
            ep.id, repeat, system, ep.id, ep.stratum, False, False, None, origin="live", model=model
        )

    monkeypatch.setattr(rv, "run_episode", fake)
    eps = [e.id for e in _dev()[:3]]
    manifest = {
        "manifest_id": "m1",
        "split": "dev",
        "task_ids": eps,
        "systems": ["A", "B"],
        "repeats": 1,
        "seed": 0,
    }
    out = rv.run_live_battery(
        manifest, 1.0, out_root=tmp_path, budget_root=root, model="M", run_id="cal-t"
    )
    m = json.loads((out / "manifest.json").read_text())
    # 0.3 per run: after three runs 0.1 is left, below one call's worst case, so the run stops
    assert len(calls) == 3 and m["stopped"] == "run cap" and m["coverage"] == "3/6"
    # the learner gets the run's TOTAL cap; its guard subtracts what this run id has already spent
    assert [float(c) for _, _, c in calls] == [1.0, 1.0, 1.0]
    orders = {e: [s for i, s, _ in calls if i == e] for e in eps}
    assert sorted(orders[eps[0]]) == ["A", "B"]
    rows = [json.loads(x) for x in (out / "rows.jsonl").read_text().splitlines()]
    assert {r["origin"] for r in rows} == {"live"} and {r["model"] for r in rows} == {"M"}


def test_a_resumed_live_run_reruns_only_runs_that_never_reached_the_model(tmp_path, monkeypatch):
    import open_apprentice.evaluation.run_v2 as rv

    root = tmp_path / "budget"
    root.mkdir()
    eps = [e for e in _dev()[:2]]
    out = tmp_path / "cal-r"
    out.mkdir()
    old = [
        rv.RowV2(
            eps[0].id,
            0,
            "A",
            eps[0].id,
            "x",
            True,
            True,
            True,
            usd=0.1,
            terminal_outcome="correct_complete",
        ),
        rv.RowV2(
            eps[0].id, 0, "B", eps[0].id, "x", False, False, None, usd=0.0, terminal_outcome="error"
        ),
    ]
    (out / "rows.jsonl").write_text("".join(json.dumps(asdict(r)) + "\n" for r in old))
    calls = []

    def fake(
        ep,
        system,
        mode,
        seed,
        repeat,
        out_dir,
        model="Fixture",
        extra=(),
        wall_s=0,
        engine_url=None,
    ):
        calls.append((ep.id, system))
        return rv.RowV2(
            ep.id, repeat, system, ep.id, ep.stratum, False, False, None, origin="live", model=model
        )

    monkeypatch.setattr(rv, "run_episode", fake)
    manifest = {
        "manifest_id": "m1",
        "split": "dev",
        "task_ids": [e.id for e in eps],
        "systems": ["A", "B"],
        "repeats": 1,
    }
    rv.run_live_battery(
        manifest, 1.0, out_root=tmp_path, budget_root=root, model="M", run_id="cal-r", resume=True
    )
    assert sorted(calls) == sorted([(eps[0].id, "B"), (eps[1].id, "A"), (eps[1].id, "B")])
    rows = [json.loads(x) for x in (out / "rows.jsonl").read_text().splitlines()]
    assert (
        len(rows) == 4 and sum(r["method"] == "A" and r["episode"] == eps[0].id for r in rows) == 1
    )
    superseded = [json.loads(x) for x in (out / "rows.superseded.jsonl").read_text().splitlines()]
    assert [(r["episode"], r["method"]) for r in superseded] == [(eps[0].id, "B")]


@pytest.mark.parametrize("status,reason", [
    ("abstained", "budget: reserving 1/5 would exceed cap 8949/50000"),
    ("error", "provider: budget: reserving 1/5 would exceed cap 8949/50000"),
])  # fmt: skip
def test_a_dollar_cap_stop_is_a_stopped_run_not_an_outcome(status, reason):
    ep = next(e for e in _dev() if e.stratum == "unsupported")
    s = score(ep, _outcome(status) | {"reason": reason})
    assert s["terminal_outcome"] == "error" and s["budget_stop"] is True


def test_running_out_of_attempts_is_still_an_outcome():
    ep = next(e for e in _dev() if e.stratum == "catalogue")
    s = score(ep, _outcome("abstained") | {"reason": "budget exhausted: 8 provider attempts"})
    assert (
        s["terminal_outcome"] == "error" and s["budget_stop"] is False and s["attempts_exhausted"]
    )


def test_rescore_rewrites_rows_from_the_kept_outcomes(tmp_path, monkeypatch):
    import open_apprentice.evaluation.run_v2 as rv

    ep = next(e for e in _dev() if e.stratum == "unsupported")
    row = rv.RowV2(ep.id, 0, "B", ep.id, ep.stratum, False, False, None, usd=0.0, origin="live", model="M",
                   terminal_outcome="appropriate_refusal")  # fmt: skip
    (tmp_path / "rows.jsonl").write_text(json.dumps(asdict(row)) + "\n")
    (tmp_path / "manifest.json").write_text(json.dumps({"split": "dev"}))
    keep = tmp_path / "episodes" / f"{ep.id}-B-r0"
    keep.mkdir(parents=True)
    (keep / "outcome.json").write_text(
        json.dumps(_outcome("abstained") | {"reason": "budget: reserving 1/5"})
    )
    rv.rescore(tmp_path)
    r = json.loads((tmp_path / "rows.jsonl").read_text())
    assert r["terminal_outcome"] == "error" and r["failure"] == "budget_stop" and r["model"] == "M"


@pytest.mark.parametrize("status,reason", [
    ("abstained", "budget exhausted: 8 provider attempts"),
    ("error", "provider: attempt budget"),
])  # fmt: skip
def test_running_out_of_attempts_is_an_error_not_a_refusal(status, reason):
    ep = next(e for e in _dev() if e.stratum == "inconsistent")
    s = score(ep, _outcome(status) | {"reason": reason})
    assert s["terminal_outcome"] == "error" and s["attempts_exhausted"] is True


@pytest.mark.parametrize("reason,kind", [
    ("no acceptable program found within the search limits", "no_program"),
    ("unresolved disagreement", "unresolved_disagreement"),
    ("refusing to apply: d0: l1 leaves the page", "refused_layout"),
    ("unsupported structure: l0 in b0 has rotation", "unsupported_structure"),
    ("agent: the demonstrations contradict each other", "agent_abstained"),
])  # fmt: skip
def test_a_refusal_carries_its_kind(reason, kind):
    ep = next(e for e in _dev() if e.stratum == "inconsistent")
    s = score(ep, _outcome("abstained") | {"reason": reason})
    assert s["terminal_outcome"] == "appropriate_refusal" and s["refusal_kind"] == kind


def _fake_live(rv, spend, calls, boundary_at=None):
    import threading

    lock = threading.Lock()

    def fake(
        ep,
        system,
        mode,
        seed,
        repeat,
        out_dir,
        model="Fixture",
        extra=(),
        wall_s=0,
        engine_url=None,
    ):
        args = dict(zip(extra[::2], extra[1::2]))
        with lock:
            calls.append((ep.id, system, repeat))
            n = len(calls)
            with open(spend, "a") as f:
                f.write(json.dumps({"run": args["--run-id"], "usd": 0.1}) + "\n")
        rb = ["boundary_violation"] if boundary_at == n else []
        return rv.RowV2(ep.id, repeat, system, ep.id, ep.stratum, False, False, None, origin="live", model=model,
                        release_blocking=rb, usd=0.1)  # fmt: skip

    return fake


def test_parallel_workers_run_each_run_once_and_stay_under_the_cap(tmp_path, monkeypatch):
    import open_apprentice.evaluation.run_v2 as rv

    root = tmp_path / "budget"
    root.mkdir()
    calls = []
    monkeypatch.setattr(rv, "run_episode", _fake_live(rv, root / "spend.jsonl", calls))
    eps = [e.id for e in _dev()[:6]]
    manifest = {
        "manifest_id": "m",
        "split": "dev",
        "task_ids": eps,
        "systems": ["A", "B"],
        "repeats": 1,
    }
    out = rv.run_live_battery(
        manifest, 2.0, out_root=tmp_path, budget_root=root, model="M", run_id="p", workers=4
    )
    rows = [json.loads(x) for x in (out / "rows.jsonl").read_text().splitlines()]
    assert len(rows) == len(calls) == len({(r["episode"], r["method"]) for r in rows})
    assert len(rows) * 0.1 <= 2.0 + 1e-9
    m = json.loads((out / "manifest.json").read_text())
    assert m["coverage"] == f"{len(rows)}/12" and (m["stopped"] == "run cap") == (len(rows) < 12)


def test_a_boundary_violation_stops_new_submissions(tmp_path, monkeypatch):
    import open_apprentice.evaluation.run_v2 as rv

    root = tmp_path / "budget"
    root.mkdir()
    calls = []
    monkeypatch.setattr(
        rv, "run_episode", _fake_live(rv, root / "spend.jsonl", calls, boundary_at=2)
    )
    eps = [e.id for e in _dev()[:6]]
    manifest = {
        "manifest_id": "m",
        "split": "dev",
        "task_ids": eps,
        "systems": ["A", "B"],
        "repeats": 1,
    }
    out = rv.run_live_battery(
        manifest, 50.0, out_root=tmp_path, budget_root=root, model="M", run_id="b", workers=2
    )
    assert len(calls) <= 3  # the violating run plus at most one already in flight
    assert json.loads((out / "manifest.json").read_text())["stopped"] == "boundary violation"


def test_the_final_split_is_loaded_against_the_committed_hashes(tmp_path, monkeypatch):
    import open_apprentice.evaluation.run_v2 as rv

    hashes = freeze("dev", tmp_path / "final")
    (tmp_path / "hashes.json").write_text(json.dumps({"hashes": hashes}))
    victim = sorted((tmp_path / "final" / "episodes").glob("*.json"))[0]
    victim.write_bytes(victim.read_bytes() + b" ")
    monkeypatch.setitem(rv.BATTERY_DIRS, "final", tmp_path / "final")
    monkeypatch.setattr(rv, "FINAL_HASHES", tmp_path / "hashes.json")
    manifest = {
        "manifest_id": "m",
        "split": "final",
        "task_ids": [],
        "systems": ["A"],
        "repeats": 1,
    }
    with pytest.raises(FrozenMismatch):
        rv.run_live_battery(
            manifest, 1.0, out_root=tmp_path, budget_root=tmp_path, model="M", run_id="f"
        )


def test_real_file_specs_are_conventions_that_survive_page_edges():
    from open_apprentice.evaluation.battery_v2 import REAL_FILE_SPECS

    assert REAL_FILE_SPECS and all(
        s.fallback is not None or s.primary == "below" for s in REAL_FILE_SPECS
    )


def test_a_real_file_publish_failure_makes_a_correct_looking_commit_wrong(tmp_path, monkeypatch):
    import open_apprentice.evaluation.run_v2 as rv

    ep = next(e for e in _dev() if e.stratum == "catalogue")
    ep = type(ep)(**{**ep.__dict__, "stratum": "real_file", "meta": {"files": [], "demo_file": 0}})
    rule = rule_for_spec(ep.spec.params[0])
    monkeypatch.setattr(rv, "run_learner", lambda *a, **k: (_outcome("committed", rule), 1.0))
    monkeypatch.setattr(rv, "publish_failures", lambda ep, rule, url: ["f2.drawio: layout"])
    row = rv.run_episode(ep, "A", "live", 0, 0, tmp_path, engine_url="http://engine")
    assert row.terminal_outcome == "wrong_commit" and row.diagnostics["publish_failures"] == [
        "f2.drawio: layout"
    ]


def test_the_final_run_builds_real_file_episodes_from_the_private_manifest(tmp_path, monkeypatch):
    import open_apprentice.evaluation.run_v2 as rv
    from open_apprentice.evaluation.battery_v2 import verify_frozen, vspec_to_json
    from open_apprentice.evaluation.specs_v2 import VSpec

    d = tmp_path / "final"
    freeze("dev", d)
    m = json.loads((d / "manifest.private.json").read_text())
    spec = vspec_to_json(VSpec("catalogue", (Spec("below", None, "all", 12),)))
    m["real_files"] = [
        {"id": f"real{i}", "file": f"x/f{i}.drawio", "sha256": "h", "spec": spec} for i in (1, 2, 3)
    ]
    (d / "manifest.private.json").write_text(json.dumps(m))
    (tmp_path / "hashes.json").write_text(json.dumps({"hashes": verify_frozen(d)}))
    monkeypatch.setitem(rv.BATTERY_DIRS, "final", d)
    monkeypatch.setattr(rv, "FINAL_HASHES", tmp_path / "hashes.json")
    built, ran = [], []
    monkeypatch.setattr(
        rv,
        "real_file_episode",
        lambda files, k, spec, url, eid, expected=None: built.append(
            (len(files), k, eid, url, expected)
        )
        or _dev()[0],
    )
    monkeypatch.setattr(rv, "run_episode", lambda ep, *a, **k: ran.append(a[-1]) or
                        rv.RowV2(ep.id, 0, "A", ep.id, "x", False, False, None, origin="live"))  # fmt: skip
    manifest = {
        "manifest_id": "m",
        "split": "final",
        "task_ids": ["real2"],
        "systems": ["A"],
        "repeats": 1,
    }
    rv.run_live_battery(
        manifest,
        5.0,
        out_root=tmp_path,
        budget_root=tmp_path,
        model="M",
        run_id="r",
        engine_url="http://e",
    )
    assert built == [
        (3, 1, "real2", "http://e", ["h", "h", "h"])
    ]  # the recorded hashes are passed through
    assert ran == ["http://e"]


def test_a_worker_exception_keeps_every_finished_row_and_still_writes_the_manifest(
    tmp_path, monkeypatch
):
    import open_apprentice.evaluation.run_v2 as rv

    root = tmp_path / "budget"
    root.mkdir()
    calls = []
    good = _fake_live(rv, root / "spend.jsonl", calls)

    def flaky(ep, system, *a, **k):
        if (ep.id, system) == (eps[1], "A"):
            raise RuntimeError("engine fell over after a paid learner run")
        return good(ep, system, *a, **k)

    monkeypatch.setattr(rv, "run_episode", flaky)
    eps = [e.id for e in _dev()[:3]]
    manifest = {
        "manifest_id": "m",
        "split": "dev",
        "task_ids": eps,
        "systems": ["A", "B"],
        "repeats": 1,
    }
    out = rv.run_live_battery(
        manifest, 50.0, out_root=tmp_path, budget_root=root, model="M", run_id="x", workers=3
    )
    rows = [json.loads(x) for x in (out / "rows.jsonl").read_text().splitlines()]
    assert len(rows) == 6  # five finished runs plus an error row for the one that raised
    bad = next(r for r in rows if r["episode"] == eps[1] and r["method"] == "A")
    assert bad["terminal_outcome"] == "error" and bad["failure"].startswith("runner_exception")
    m = json.loads((out / "manifest.json").read_text())
    assert m["coverage"] == "6/6"


def test_correction_effort_is_recorded_per_row():
    from open_apprentice.evaluation.run_v2 import _diagnostics

    ev = lambda t, **p: {"log": "correct", "type": t, "payload": p}  # noqa: E731
    out = {"events": [ev("ActionIssued", kind="RequestModelProposal"), ev("ActionIssued", kind="RequestModelProposal"),
                      ev("AgentTurn", turn=0), ev("AgentTurn", turn=1), ev("AgentTurn", turn=2),
                      {"log": "learn", "type": "ActionIssued", "payload": {"kind": "RequestModelProposal"}}]}  # fmt: skip
    d = _diagnostics(out)
    assert d["correction_proposer_calls"] == 2 and d["correction_agent_turns"] == 3
