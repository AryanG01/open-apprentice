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


def run_learner(tmp_path, ep, system="A", prefix=None, learner_dir=None, env=None):
    ldir = learner_dir or tmp_path / "learner"
    pdir = tmp_path / "private"
    ldir.mkdir(parents=True, exist_ok=True)
    pdir.mkdir(parents=True, exist_ok=True)
    lf, pf = ldir / f"{ep.id}.json", pdir / f"{ep.id}.private.json"
    lf.write_bytes(codec.dumps(learner_view(ep)))
    pf.write_bytes(codec.dumps(episode_to_json(ep)))
    teacher = [
        sys.executable,
        "-m",
        "open_apprentice.evaluation.teacher_sim",
        str(pf),
        str(pdir / "log.jsonl"),
    ]
    out = tmp_path / "outcome.json"
    args = ["--episode", str(lf), "--system", system, "--teacher-cmd", json.dumps(teacher)]
    args += ["--mode", "mock", "--seed", "0", "--out", str(out)]
    head = prefix or [sys.executable, "-m", "open_apprentice.learner.main"]
    r = subprocess.run([*head, *args], env=env or ENV, capture_output=True, text=True, timeout=120)
    assert out.exists(), r.stderr[-2000:]
    return json.loads(out.read_text()), r


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
