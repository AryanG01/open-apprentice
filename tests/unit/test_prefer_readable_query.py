"""Human-facing sessions break ties toward readable sampled scenes; scores (and the default behaviour) are unchanged."""

from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.query_selection import select_query
from open_apprentice.concepts.witness import SolverBudget, SolverPool
from tests.fixtures_rules import CLAMPED_MARGIN, CONST_MARGIN, PROP_MARGIN


def _pick(prefer):
    with SolverPool() as pool:
        return select_query(
            [CONST_MARGIN, PROP_MARGIN(), CLAMPED_MARGIN()],
            DomainManifest(),
            [2],
            SolverBudget(),
            pool,
            seed=0,
            prefer_readable=prefer,
        )


def test_default_still_prefers_the_solver_witness_on_ties():
    assert _pick(False).source == "solver_witness"


def test_prefer_readable_picks_a_sampled_scene_with_the_same_disagreement():
    a, b = _pick(False), _pick(True)
    assert b.source == "sampled" and len(b.groups) == len(a.groups) and b.score >= a.score - 1e-9
    xs = [(o["x"], o["w"]) for o in b.scene["objects"]]
    assert all(
        w >= 30 for _, w in xs
    ), "sampled scenes are readable (no degenerate stacked tiny objects)"
