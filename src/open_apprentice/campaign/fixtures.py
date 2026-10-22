"""Public development fixtures (spec 7.8). Development tests only: never call them held out."""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent / "fixture_data"
FIXTURE_IDS: tuple[str, ...] = (
    "teach_before",
    "teach_after",
    "short_a",
    "short_b",
    "de_long_a",
    "de_long_b",
    "fr_long",
    "missing_role",
    "duplicate_role",
)


@cache
def _read(fid: str) -> dict:
    return json.loads((_DIR / f"{fid}.json").read_text(encoding="utf-8"))


def load_fixture(fid: str) -> dict:
    """A fresh deep copy: {id, locale, provenance, artboard, scene}."""
    if fid not in FIXTURE_IDS:
        raise KeyError(f"unknown campaign fixture {fid}")
    return copy.deepcopy(_read(fid))
