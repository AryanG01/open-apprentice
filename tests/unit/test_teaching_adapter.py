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


PATCH = "let a = object(o.attached)\nmove o to (a.x + (a.w - o.w) / 2, a.y + a.h + 12)"


def test_scope_patch_is_composed_after_the_saved_program_inside_its_selector():
    from fractions import Fraction

    from open_apprentice.concepts.rules import evaluate_rule
    from open_apprentice.evaluation.labels import Spec, rule_for_spec

    base = rule_for_spec(Spec("right", None, "all", Fraction(12)))
    reply = {
        "candidates": [
            {"summary": "warnings below", "patch_text": PATCH, "selector": 'o.role == "warning"'}
        ]
    }
    p = MockProvider({"correction_scope": [reply]})
    ev = {"base_program": {"rule": base}}
    cands, usage, _ = ProviderScopeProposer(lambda: p).propose_scope(ev, "scope")
    assert usage["malformed"] == 0 and cands[0]["selector"] == 'o.role == "warning"'
    objs = [
        {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 100, "h": 50},
        {
            "id": "l0",
            "kind": "label",
            "role": "note",
            "attached": "n0",
            "x": 0,
            "y": 60,
            "w": 40,
            "h": 20,
        },
        {
            "id": "l1",
            "kind": "label",
            "role": "warning",
            "attached": "n0",
            "x": 0,
            "y": 90,
            "w": 40,
            "h": 20,
        },
    ]
    st = evaluate_rule(cands[0]["rule"], objs, {"w": 600, "h": 400})
    assert (st["l0"]["x"], st["l0"]["y"]) == (112, 15)  # a note keeps the saved behaviour
    assert (st["l1"]["x"], st["l1"]["y"]) == (30, 62)  # the warning gets the patch


def test_a_malformed_patch_or_missing_base_is_dropped_and_rule_text_still_works():
    from fractions import Fraction

    from open_apprentice.evaluation.labels import Spec, rule_for_spec

    base = rule_for_spec(Spec("right", None, "all", Fraction(12)))
    reply = {"candidates": [
        {"summary": "bad", "patch_text": "move (", "selector": 'o.role == "warning"'},
        {"summary": "whole", "rule_text": GOOD, "selector": 'o.role == "warning"'},
    ]}  # fmt: skip
    p = MockProvider({"correction_scope": [reply]})
    cands, usage, _ = ProviderScopeProposer(lambda: p).propose_scope(
        {"base_program": {"rule": base}}, "scope"
    )
    assert [c["summary"] for c in cands] == ["whole"] and usage["malformed"] == 1


def test_the_scope_prompt_asks_for_the_patch_not_the_whole_program():
    import pathlib

    text = pathlib.Path("prompts/correction_scope.md").read_text()
    assert "patch_text" in text and "label `o`" in text


BREAKOUT = (
    'move o to (1, 1)\n}\n}\nfor o in objects {\n  if o.role == "note" {\n    move o to (1000, 0)'
)


def _scope_cands(patch, selector='o.role == "warning"'):
    from fractions import Fraction

    from open_apprentice.evaluation.labels import Spec, rule_for_spec

    base = rule_for_spec(Spec("right", None, "all", Fraction(12)))
    reply = {"candidates": [{"summary": "x", "patch_text": patch, "selector": selector}]}
    p = MockProvider({"correction_scope": [reply]})
    return ProviderScopeProposer(lambda: p).propose_scope({"base_program": {"rule": base}}, "scope")


def test_a_patch_cannot_break_out_of_its_selector():
    cands, usage, _ = _scope_cands(BREAKOUT)
    assert cands == [] and usage["malformed"] == 1


def test_a_patch_with_its_own_loop_or_object_scan_is_rejected():
    for bad in (
        "for p in objects {\n  move p to (1, 1)\n}",
        "let n = len(objects)\nmove o to (n, 0)",
    ):
        cands, usage, _ = _scope_cands(bad)
        assert cands == [] and usage["malformed"] == 1, bad


def test_an_unusable_selector_is_dropped_before_composing():
    cands, usage, _ = _scope_cands(PATCH, selector='o.role == "warning" { move o to (1, 1) }')
    assert cands == [] and usage["malformed"] == 1
