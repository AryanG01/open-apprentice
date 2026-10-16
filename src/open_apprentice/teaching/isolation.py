"""Runtime guard for learner processes: after installation, importing the evaluator raises. Complements the static
import-linter contract (which cannot stop a hidden oracle being passed in at runtime)."""

from __future__ import annotations

import os
import sys
from pathlib import PurePath
from typing import Any

_installed = False
_files_installed = False
violations: list[str] = []  # every refused access, kept even when the caller swallows the exception
SPAWN_EVENTS = ("subprocess.Popen", "os.exec", "os.posix_spawn", "os.spawn", "os.system", "os.fork")


def install_learner_guard(forbidden_prefix: str = "open_apprentice.evaluation") -> None:
    global _installed
    if _installed:
        return
    loaded = [
        m for m in sys.modules if m == forbidden_prefix or m.startswith(forbidden_prefix + ".")
    ]
    if loaded:
        raise RuntimeError(f"learner guard: evaluator modules already loaded: {sorted(loaded)[:3]}")

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if (
            event == "import"
            and args
            and isinstance(args[0], str)
            and (args[0] == forbidden_prefix or args[0].startswith(forbidden_prefix + "."))
        ):
            violations.append(f"import {args[0]}")
            raise ImportError(f"learner process may not import {args[0]}")

    sys.addaudithook(hook)
    _installed = True


def _forbidden_path(p: Any) -> bool:
    if isinstance(p, int) or p is None:
        return False
    try:
        path = PurePath(os.path.abspath(os.fsdecode(p)))
    except (TypeError, ValueError):
        return False
    return "benchmarks" in path.parts or path.name.endswith(".private.json")


def install_file_guard() -> None:
    """Learner processes: no file or directory under any `benchmarks/` folder, no `*.private.json`, and no child
    processes (the teacher arrives as inherited pipes). Each refusal is recorded in `violations`."""
    global _files_installed
    if _files_installed:
        return

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event in ("open", "os.listdir", "os.scandir") and args and _forbidden_path(args[0]):
            violations.append(f"{event} {args[0]}")
            raise PermissionError(f"learner process may not read {args[0]}")
        if event in SPAWN_EVENTS:
            violations.append(f"{event}")
            raise PermissionError("learner process may not start other processes")

    sys.addaudithook(hook)
    _files_installed = True
