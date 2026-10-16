from fractions import Fraction as F

import pytest

import open_apprentice.providers.teaching_adapter as ta
from open_apprentice.providers.mock import MockProvider
from open_apprentice.providers.teaching_adapter import ProviderProposer, ProviderScopeProposer

GOOD = (
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n'
    "    move o to (a.x + a.w + 12, a.y)\n  }\n}"
)


def test_proposer_parses_rule_text_and_drops_malformed():
    reply = {
        "candidates": [
            {"summary": "right 12", "rule_text": GOOD},
            {"summary": "bad", "rule_text": "move ("},
        ]
    }
    p = MockProvider({"hypotheses": [reply]})
    cands, usage, cost = ProviderProposer(lambda: p).propose(
        {"teaching_evidence": []}, "initial", ()
    )
    assert [c["summary"] for c in cands] == ["right 12"] and isinstance(cands[0]["rule"], list)
    assert usage["malformed"] == 1 and usage["provider_label"] == "MOCK"
    assert cost == F(0)


def test_feedback_reaches_the_model_on_later_rounds():
    p = MockProvider({"hypotheses": [{"candidates": []}]})
    ProviderProposer(lambda: p).propose({"teaching_evidence": []}, "contrastive", ("too narrow",))
    _, messages = p.calls[0]
    assert "too narrow" in messages[-1].content and "contrastive" in messages[-1].content


def test_unknown_cost_raises_so_the_executor_keeps_worst_case(monkeypatch):
    p = MockProvider({"hypotheses": [{"candidates": []}]})
    monkeypatch.setattr(ta, "_usd", lambda completion: None)
    with pytest.raises(ValueError, match="cost unknown"):
        ProviderProposer(lambda: p).propose({"teaching_evidence": []}, "initial", ())


def test_scope_proposer_returns_rule_and_selector():
    reply = {"candidates": [{"summary": "w", "rule_text": GOOD, "selector": 'o.role == "warning"'}]}
    p = MockProvider({"correction_scope": [reply]})
    cands, _, _ = ProviderScopeProposer(lambda: p).propose_scope({"base_program": []}, "scope")
    assert cands[0]["selector"] == 'o.role == "warning"' and isinstance(cands[0]["rule"], list)
