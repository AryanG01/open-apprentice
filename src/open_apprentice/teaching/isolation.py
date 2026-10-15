"""Runtime guard for learner processes: after installation, importing the evaluator raises. Complements the static
import-linter contract (which cannot stop a hidden oracle being passed in at runtime)."""

from __future__ import annotations

import sys
from typing import Any

_installed = False


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
            raise ImportError(f"learner process may not import {args[0]}")

    sys.addaudithook(hook)
    _installed = True
