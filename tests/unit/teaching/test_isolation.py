import os
import subprocess
import sys


def run(code: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": "src"}
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)


def test_guard_blocks_evaluation_imports_after_install():
    r = run(
        "from open_apprentice.teaching.isolation import install_learner_guard\n"
        "install_learner_guard()\n"
        "import open_apprentice.evaluation.labels\n"
    )
    assert r.returncode != 0 and "learner process may not import" in r.stderr


def test_guard_allows_teaching_modules():
    r = run(
        "from open_apprentice.teaching.isolation import install_learner_guard\n"
        "install_learner_guard()\n"
        "import open_apprentice.teaching.executor\n"
        "print('ok')\n"
    )
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


def test_learner_modules_do_not_pull_in_the_evaluator():
    r = run(
        "import sys\n"
        "import open_apprentice.teaching.executor\n"
        "bad = [m for m in sys.modules if m.startswith('open_apprentice.evaluation')]\n"
        "print(bad)\n"
        "assert not bad\n"
    )
    assert r.returncode == 0, r.stdout + r.stderr
