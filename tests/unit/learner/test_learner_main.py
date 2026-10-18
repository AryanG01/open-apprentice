import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from open_apprentice.evaluation.battery_v2 import build_battery, episode_to_json, learner_view
from open_apprentice.teaching import codec

REPO = Path(__file__).resolve().parents[3]
ENV = {**os.environ, "PYTHONPATH": f"{REPO / 'src'}{os.pathsep}{REPO}"}


@lru_cache(maxsize=None)
def _dev():
    return tuple(build_battery("dev"))


def _ep(pred):
    return next(e for e in _dev() if pred(e))


def run_learner(
    tmp_path, ep, system="A", prefix=None, learner_dir=None, env=None, mode="mock", extra=()
):
    ldir = learner_dir or tmp_path / "learner"
    pdir = tmp_path / "private"
    ldir.mkdir(parents=True, exist_ok=True)
    pdir.mkdir(parents=True, exist_ok=True)
    lf, pf = ldir / f"{ep.id}.json", pdir / f"{ep.id}.private.json"
    lf.write_bytes(codec.dumps(learner_view(ep)))
    pf.write_bytes(codec.dumps(episode_to_json(ep)))
    teacher = subprocess.Popen(
        [sys.executable, "-m", "open_apprentice.evaluation.teacher_sim", str(pf), str(pdir / "log.jsonl")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=ENV,
    )  # fmt: skip
    fds = (teacher.stdout.fileno(), teacher.stdin.fileno())
    out = tmp_path / "outcome.json"
    args = ["--episode", str(lf), "--system", system, "--teacher-fds", f"{fds[0]},{fds[1]}"]
    args += ["--mode", mode, "--seed", "0", "--out", str(out), *extra]
    head = prefix or [sys.executable, "-m", "open_apprentice.learner.main"]
    try:
        r = subprocess.run([*head, *args], env=env or ENV, capture_output=True, text=True,
                           timeout=120, pass_fds=fds)  # fmt: skip
    finally:
        teacher.stdin.close()
        teacher.wait(timeout=10)
    assert out.exists(), r.stderr[-2000:]
    return json.loads(out.read_text()), r


def _inject(body):
    return [sys.executable, "-c",
            "import open_apprentice.learner.main as m\n"
            f"def bad(ctx):\n{body}\n"
            "m.SYSTEMS['A'] = bad\nm.cli()\n"]  # fmt: skip


def test_the_learner_is_never_given_the_private_episode_path(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue")
    o, _ = run_learner(
        tmp_path, ep, prefix=_inject("    import sys\n    ctx.result['argv'] = sys.argv")
    )
    assert o["argv"] and not any(".private.json" in a or "teacher_sim" in a for a in o["argv"])


def test_opening_a_benchmarks_file_is_a_boundary_violation_even_if_caught(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue")
    target = REPO / "benchmarks" / "development" / "battery" / "manifest.private.json"
    body = f"    try:\n        open({str(target)!r}).read()\n    except Exception:\n        pass\n    ctx.result['status'] = 'abstained'"
    o, _ = run_learner(tmp_path, ep, prefix=_inject(body))
    assert o["boundary_violation"] is True and o["violations"]


def test_a_swallowed_evaluator_import_is_still_a_boundary_violation(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue")
    body = "    try:\n        import open_apprentice.evaluation.labels\n    except Exception:\n        pass\n    ctx.result['status'] = 'abstained'"
    o, _ = run_learner(tmp_path, ep, prefix=_inject(body))
    assert o["boundary_violation"] is True


def test_spawning_a_process_is_a_boundary_violation(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue")
    body = "    import subprocess\n    subprocess.run(['true'])"
    o, _ = run_learner(tmp_path, ep, prefix=_inject(body))
    assert o["status"] == "error" and o["boundary_violation"] is True


def test_offline_a_reaches_a_terminal_status_without_loading_the_evaluator(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue" and not e.clarification_required)
    o, r = run_learner(tmp_path, ep)
    assert o["status"] in ("committed", "abstained"), (o.get("reason"), r.stderr[-1500:])
    assert o["system"] == "A" and o["evaluator_modules"] == [] and not o["boundary_violation"]
    assert o["probe_render"] == "synthetic"
    if o["status"] == "committed":
        assert o["program"]["rule"]
    assert any(e["type"] == "DemonstrationRecorded" for e in o["events"])


def test_an_injected_evaluator_import_is_a_boundary_violation(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue")
    inject = (
        "import open_apprentice.learner.main as m\n"
        "def bad(ctx):\n"
        "    import open_apprentice.evaluation.labels\n"
        "m.SYSTEMS['A'] = bad\n"
        "m.cli()\n"
    )
    o, _ = run_learner(tmp_path, ep, prefix=[sys.executable, "-c", inject])
    assert o["status"] == "error" and o["boundary_violation"] is True


def test_an_episode_under_benchmarks_final_is_refused(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue")
    o, r = run_learner(tmp_path, ep, learner_dir=tmp_path / "benchmarks" / "final" / "battery")
    assert o["status"] == "error" and "benchmarks/final" in o["reason"]
    assert r.returncode != 0


def test_an_environment_naming_the_private_manifest_is_refused(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue")
    env = {**ENV, "OA_SECRET": "/x/benchmarks/final/battery/manifest.private.json"}
    o, _ = run_learner(tmp_path, ep, env=env)
    assert o["status"] == "error" and "environment" in o["reason"]


def test_an_unsupported_structure_is_refused_with_a_reason(tmp_path):
    ep = _ep(lambda e: e.meta.get("subtype") == "unsupported_structure")
    o, _ = run_learner(tmp_path, ep)
    assert o["status"] == "abstained" and "rotation" in o["reason"]


def test_a_sequential_episode_runs_learning_then_the_correction(tmp_path):
    ep = _ep(lambda e: e.stratum == "sequential" and e.correction["kind"] == "override")
    o, r = run_learner(tmp_path, ep)
    assert o["status"] in ("committed", "abstained"), (o.get("reason"), r.stderr[-1500:])
    if o["status"] == "committed":
        assert o["correction"]["status"] in (
            "activated",
            "override",
            "dismissed",
            "abstained",
            "error",
            "activation_rejected",
        ), o["correction"]


def test_system_c_commits_a_catalogue_program_on_an_identifiable_episode(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue" and not e.clarification_required)
    o, r = run_learner(tmp_path, ep, system="C")
    assert o["system"] == "C" and o["status"] == "committed", (o["reason"], r.stderr[-1500:])
    sources = {
        e["payload"]["usage"].get("source")
        for e in o["events"]
        if e["type"] == "ModelProposalReturned"
    }
    assert sources == {"catalogue"}


def test_system_d_runs_a_policy_with_uniform_questions(tmp_path):
    ep = _ep(lambda e: e.stratum == "sequential" and e.clarification_required)
    o, r = run_learner(tmp_path, ep, system="D")
    assert o["system"] == "D" and o["status"] in ("committed", "abstained"), (
        o["reason"],
        r.stderr[-1500:],
    )
    assert o["question_selection"] == "uniform"


def test_system_b_runs_offline_with_the_scripted_fixture_policy(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue" and not e.clarification_required)
    o, r = run_learner(tmp_path, ep, system="B")
    assert o["system"] == "B" and o["status"] in ("committed", "abstained"), (
        o["reason"],
        r.stderr[-1500:],
    )
    assert o["policy"] == "scripted_fixture" and o["correction_policy"] == "B"
    assert any(e["type"] == "AgentTurn" for e in o["events"])


def test_live_mode_refuses_without_a_live_provider_or_a_cap(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue")
    dotenv = tmp_path / "mock.env"
    dotenv.write_text("PROVIDER_MODE=mock\n")
    env = {k: v for k, v in ENV.items() if k != "PROVIDER_MODE"}
    common = ["--run-id", "t", "--budget-root", str(tmp_path), "--dotenv", str(dotenv)]
    o, r = run_learner(tmp_path, ep, mode="live", env=env, extra=[*common, "--cap-usd", "0.5"])
    assert o["status"] == "error" and "nebius" in o["reason"] and r.returncode == 2
    o, _ = run_learner(tmp_path, ep, mode="live", env=env, extra=[*common, "--cap-usd", "0"])
    assert "cap" in o["reason"]
    assert not (tmp_path / "spend.jsonl").exists()


def test_system_a2_runs_offline_to_a_terminal_status_and_is_marked_v2(tmp_path):
    ep = _ep(lambda e: e.stratum == "catalogue" and not e.clarification_required)
    o, r = run_learner(tmp_path, ep, system="A2")
    assert o["system"] == "A2" and o["status"] in ("committed", "abstained"), (
        o["reason"],
        r.stderr[-1500:],
    )
    assert o["policy_version"] == "v2" and o["question_selection"] == "best"


def test_system_d2_is_a2_with_uniform_questions(tmp_path):
    ep = _ep(lambda e: e.stratum == "sequential" and e.clarification_required)
    o, _ = run_learner(tmp_path, ep, system="D2")
    assert (
        o["system"] == "D2" and o["policy_version"] == "v2" and o["question_selection"] == "uniform"
    )


def test_a2_and_d2_differ_from_a_and_d_only_in_the_two_v2_settings():
    from open_apprentice.teaching.step import V2_SETTINGS, StepConfig

    assert V2_SETTINGS == {"max_revisions": 3, "tolerate_truncation": True}
    base = StepConfig(probes=True)
    v2 = StepConfig(probes=True, **V2_SETTINGS)
    assert {k for k in vars(base) if getattr(base, k) != getattr(v2, k)} == {
        "max_revisions",
        "tolerate_truncation",
    }


def test_an_early_refusal_still_carries_the_policy_version(tmp_path):
    ep = _ep(lambda e: e.meta.get("subtype") == "unsupported_structure")
    o, _ = run_learner(tmp_path, ep, system="A2")
    assert o["status"] == "abstained" and o["policy_version"] == "v2"
