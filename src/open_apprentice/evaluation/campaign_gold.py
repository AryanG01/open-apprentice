"""Authored gold outputs for the campaign development fixtures (spec 7.7). Evaluator-side: agent code never imports this."""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent / "campaign_gold_data"
GOLD_KEYS: tuple[tuple[str, str], ...] = (
    ("teach_before", "layout"),
    ("short_a", "layout"),
    ("short_b", "layout"),
    ("de_long_a", "shrink"),
    ("de_long_a", "split"),
    ("de_long_b", "shrink"),
    ("de_long_b", "split"),
    ("fr_long", "shrink"),
    ("fr_long", "split"),
)


@cache
def _read(fixture_id: str, outcome: str) -> dict:
    return json.loads((_DIR / f"{fixture_id}.{outcome}.json").read_text(encoding="utf-8"))


def load_gold(fixture_id: str, outcome: str) -> dict | None:
    """A fresh copy of {fixture, outcome, scene, ...}, or None when the outcome is not applicable to that fixture."""
    if (fixture_id, outcome) not in GOLD_KEYS:
        raise KeyError(f"no gold for {fixture_id}/{outcome}")
    body = _read(fixture_id, outcome)
    return copy.deepcopy(body) if body["applicable"] else None
