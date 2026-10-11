"""Identical solver queries must give identical witnesses regardless of what the long-lived solver process
solved before (research reproducibility). Z3's global context otherwise carries history between queries."""

from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.witness import SolverPool
from tests.fixtures_rules import (
    CLAMPED_MARGIN,
    CONST_MARGIN,
    PROP_MARGIN,
    center_spacing_rule,
    gap_rule,
)

DOM = DomainManifest()


def payload(a, b, n=2):
    return {
        "mode": "disagree",
        "rules": [a, b],
        "n": n,
        "domain": DOM.canonical(),
        "threshold": "1",
        "timeout_ms": 2000,
        "memory_mb": 512,
    }


def test_same_query_same_model_after_unrelated_history():
    p = payload(CONST_MARGIN, PROP_MARGIN())
    with SolverPool() as fresh:
        a = fresh.solve(p, 30)
    with SolverPool() as busy:
        for other in (
            payload(gap_rule(), center_spacing_rule(), 3),
            payload(CLAMPED_MARGIN(), PROP_MARGIN()),
            payload(gap_rule(), gap_rule()),
            payload(CONST_MARGIN, CLAMPED_MARGIN()),
        ):
            busy.solve(other, 30)
        b = busy.solve(p, 30)
    assert a["status"] == b["status"] == "sat" and a["model"] == b["model"]
