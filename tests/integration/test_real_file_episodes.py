from fractions import Fraction as F
from pathlib import Path

from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.evaluation.labels import Spec, rule_for_spec
from open_apprentice.evaluation.real_files import publish_failures, real_file_episode
from open_apprentice.evaluation.run_v2 import score
from open_apprentice.evaluation.specs_v2 import VSpec

DEV = [Path(f"tests/fixtures/drawio_corpus/dev/d{i}.drawio") for i in (1, 2, 3)]
SPEC = VSpec(
    "catalogue", (Spec("below", None, "all", F(12)),)
)  # publishes cleanly on the dev files


def _outcome(rule):
    return {
        "status": "committed",
        "program": {"rule": rule},
        "correction": None,
        "events": [],
        "reason": None,
    }


def test_dev_real_file_episodes_build_from_the_engine(engine_url):
    for k in range(3):
        ep = real_file_episode(DEV, k, SPEC, engine_url, "dev-real")
        assert ep.stratum == "real_file" and len(ep.demo_scenes) == 1
        assert (
            len(ep.batch_scenes) == 1 and len(ep.scoring_scenes) == 1
        )  # the scored file was never shown
        assert any(o["kind"] == "label" for o in ep.demo_scenes[0]["objects"])
        assert ep.demo_outputs[0] != ep.demo_scenes[0]


def test_real_file_scoring_tells_right_from_wrong(engine_url):
    ep = real_file_episode(DEV, 0, SPEC, engine_url, "dev-real")
    assert (
        score(ep, _outcome(rule_for_spec(SPEC.params[0])))["terminal_outcome"] == "correct_complete"
    )
    wrong = rule_for_spec(Spec("right", "below", "all", F(16)))
    assert score(ep, _outcome(wrong))["terminal_outcome"] == "wrong_commit"


def test_a_publish_failure_is_reported(engine_url):
    ep = real_file_episode(DEV, 0, SPEC, engine_url, "dev-real")
    off_page = parse_rule_text(
        'for o in objects {\n  if o.kind == "label" {\n    move o to (o.x - 5000, o.y)\n  }\n}'
    )
    assert publish_failures(ep, off_page, engine_url)
    assert publish_failures(ep, rule_for_spec(SPEC.params[0]), engine_url) == []


def test_only_the_gated_paths_name_the_final_folder():
    allowed = {"evaluation/battery_v2.py", "evaluation/run_v2.py", "cli.py", "learner/main.py"}
    hits = {
        str(p.relative_to("src/open_apprentice"))
        for p in Path("src/open_apprentice").rglob("*.py")
        if "benchmarks/final" in p.read_text()
    }
    assert hits <= allowed, hits - allowed


def test_a_real_file_episode_can_actually_be_solved_by_a_learner(engine_url, tmp_path):
    """Without a batch document no preview is possible and nothing can ever be committed (Plan 6 review C1)."""
    from open_apprentice.evaluation.run_v2 import run_learner, score

    ep = real_file_episode(DEV, 0, SPEC, engine_url, "dev-real")
    for system in ("A", "B"):
        outcome, _ = run_learner(ep, system, "mock", 0, tmp_path / system)
        assert outcome["status"] == "committed", (system, outcome["reason"])
        assert score(ep, outcome)["terminal_outcome"] == "correct_complete"


def test_a_changed_real_file_is_refused_not_silently_scored(engine_url, tmp_path):
    import hashlib
    import shutil

    import pytest

    from open_apprentice.evaluation.battery_v2 import FrozenMismatch

    files = []
    for f in DEV:
        shutil.copy(f, tmp_path / f.name)
        files.append(tmp_path / f.name)
    want = [hashlib.sha256(f.read_bytes()).hexdigest() for f in files]
    ep = real_file_episode(files, 0, SPEC, engine_url, "dev-real", expected=want)
    assert ep.meta["sha256"] == want
    files[2].write_bytes(files[2].read_bytes() + b"\n")  # a changed scoring file
    with pytest.raises(FrozenMismatch):
        publish_failures(ep, rule_for_spec(SPEC.params[0]), engine_url)
    with pytest.raises(FrozenMismatch):
        real_file_episode(files, 0, SPEC, engine_url, "dev-real", expected=want)
