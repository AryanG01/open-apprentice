"""The out-of-grammar battery really is outside the search grammar, and every rule is valid and evaluable."""

import asyncio

import pytest

from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.enumerative import EnumerativeSource
from open_apprentice.concepts.hypotheses import Constraint
from open_apprentice.concepts.query_selection import sample_scenes
from open_apprentice.concepts.rules import evaluate_rule, validate_rule
from open_apprentice.evaluation.oog import RULES, demonstration

DOM = DomainManifest()


@pytest.mark.parametrize("i", range(len(RULES)))
def test_rules_validate_and_the_demonstration_is_consistent(i):
    validate_rule(RULES[i][1])
    d = demonstration(i)
    got = evaluate_rule(RULES[i][1], d["scene"]["objects"], d["scene"]["canvas"])
    assert all(d["after"]["badge"][k] == got["badge"][k] for k in "xywh")


@pytest.mark.parametrize("i", range(len(RULES)))
def test_the_search_alone_cannot_express_the_rule(i):
    """No candidate the search proposes reproduces the latent rule on held-out scenes: any success on this battery would be the model's."""
    d = demonstration(i)
    rep = asyncio.run(
        EnumerativeSource(DOM, [2])(
            [Constraint("positive", d["scene"], d["after"], source="demonstration")], 1, []
        )
    )
    for c in rep.accepted:
        same = all(
            evaluate_rule(c.rule, sc["objects"], sc["canvas"])
            == evaluate_rule(RULES[i][1], sc["objects"], sc["canvas"])
            for sc in sample_scenes(DOM, [2], 24, 99)
        )
        assert not same, f"rule {i} is inside the search grammar: {c.summary}"
