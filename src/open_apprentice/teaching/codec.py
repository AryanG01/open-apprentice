"""Canonical JSON for event payloads: sorted keys, no spaces, exact Fractions as "n/d" (int when whole)."""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from typing import Any


def _enc(o: Any) -> Any:
    if isinstance(o, Fraction):
        return int(o) if o.denominator == 1 else f"{o.numerator}/{o.denominator}"
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(f"not serialisable: {type(o).__name__}")


def _norm(o: Any) -> Any:
    if isinstance(o, Fraction):
        return _enc(o)
    if isinstance(o, dict):
        return {str(k): _norm(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_norm(v) for v in o]
    return o


def dumps(obj: Any) -> bytes:
    return json.dumps(_norm(obj), sort_keys=True, separators=(",", ":"), default=_enc).encode(
        "utf-8"
    )


def loads(b: bytes) -> Any:
    return json.loads(b.decode("utf-8"))


def digest(obj: Any) -> str:
    return hashlib.sha256(dumps(obj)).hexdigest()


def frac(v: Any) -> Fraction:
    if isinstance(v, Fraction):
        return v
    if isinstance(v, bool):
        raise TypeError(f"not a rational: {v!r}")
    if isinstance(v, int):
        return Fraction(v)
    if isinstance(v, str):
        return Fraction(v)
    raise TypeError(f"not a rational: {v!r}")
