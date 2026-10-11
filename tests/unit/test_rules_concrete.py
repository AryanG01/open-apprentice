from fractions import Fraction as F

import pytest

from open_apprentice.concepts.rules import RuleError, evaluate_rule, validate_rule
from tests.fixtures_rules import (
    CLAMPED_MARGIN,
    CONST_MARGIN,
    PROP_MARGIN,
    badge_rule,
    center_spacing_rule,
    gap_rule,
)

CANVAS = {"w": 800, "h": 500}


def card(w, x=100, y=100, h=80):
    return {"id": "card", "x": x, "y": y, "w": w, "h": h}


BADGE = {"id": "proto", "x": 0, "y": 0, "w": 20, "h": 20}


def badge_x_y(rule, w):
    out = evaluate_rule(rule, [card(w), BADGE], CANVAS)["badge"]
    return out["x"], out["y"]


def test_three_margin_rules_coincide_at_w150_and_diverge_elsewhere():
    """The spec's ambiguity example: 12px at width 150 under all three, different at other widths."""
    at150 = {badge_x_y(r, 150) for r in (CONST_MARGIN, PROP_MARGIN(), CLAMPED_MARGIN())}
    assert at150 == {(F(100 + 150 - 12 - 20), F(112))}
    assert (
        badge_x_y(PROP_MARGIN(), 400)[1] != badge_x_y(CLAMPED_MARGIN(), 400)[1]
    )  # 32 vs clamped 24
    assert badge_x_y(CONST_MARGIN, 400)[1] != badge_x_y(CLAMPED_MARGIN(), 400)[1]
    assert badge_x_y(PROP_MARGIN(), 50)[1] != badge_x_y(CLAMPED_MARGIN(), 50)[1]  # 4 vs clamped 8


def test_clone_keeps_prototype_size_and_card_unchanged():
    out = evaluate_rule(CONST_MARGIN, [card(150), BADGE], CANVAS)
    assert (out["badge"]["w"], out["badge"]["h"]) == (20, 20)
    assert out["card"] == {"x": 100, "y": 100, "w": 150, "h": 80}  # unemitted props preserved


def test_edge_gap_and_center_spacing_coincide_only_for_equal_widths():
    eq = [{"id": f"c{i}", "x": 0, "y": 0, "w": 100, "h": 50} for i in range(3)]
    uneq = [{"id": f"c{i}", "x": 0, "y": 0, "w": w, "h": 50} for i, w in enumerate((100, 60, 140))]
    a, b = gap_rule(gap=24), center_spacing_rule(pitch=124)
    assert evaluate_rule(a, eq, CANVAS) == evaluate_rule(b, eq, CANVAS)
    assert evaluate_rule(a, uneq, CANVAS) != evaluate_rule(b, uneq, CANVAS)


def test_exact_rationals_no_float_drift():
    out = evaluate_rule(
        badge_rule(
            {
                "op": "mul",
                "args": [{"op": "get", "args": [{"ref": "objects.0"}, "w"]}, {"rat": "1/3"}],
            }
        ),
        [card(1), BADGE],
        CANVAS,
    )
    assert out["badge"]["y"] == F(100) + F(1, 3)


@pytest.mark.parametrize(
    "bad",
    [
        [{"op": "let", "name": "a", "value": 1.5}],  # float
        [
            {"op": "emit_target", "kind": "move_existing", "target": {"ref": "objects.0"}, "x": 1}
        ],  # missing y
        [
            {
                "op": "emit_target",
                "kind": "move_existing",
                "target": {"ref": "objects.0"},
                "x": 1,
                "y": 1,
                "w": 5,
            }
        ],  # extra prop
        [
            {"op": "emit_target", "kind": "delete_all", "target": {"ref": "objects.0"}}
        ],  # unknown kind
        [{"op": "let", "name": "a", "value": {"op": "eval", "args": [1]}}],  # unknown op
        [{"op": "let", "name": "a", "value": {"ref": "__proto__.x"}}],  # proto key
        [{"op": "let", "name": "a", "value": {"ref": "env.HOME"}}],  # bad root
        [
            {"op": "for_each", "var": "o", "over": {"ref": "locals.x"}, "body": []}
        ],  # can only iterate objects
        [{"op": "tool_call", "tool": "move_node"}],  # no tools in rules
    ],
)
def test_invalid_rules_rejected(bad):
    with pytest.raises(RuleError):
        validate_rule(bad)


def test_runtime_errors_are_errors_not_nan():
    with pytest.raises(RuleError, match="division by zero"):
        evaluate_rule(
            [{"op": "let", "name": "a", "value": {"op": "div", "args": [1, 0]}}], [card(10)], CANVAS
        )
    with pytest.raises(RuleError, match="unbound"):
        evaluate_rule(
            [{"op": "let", "name": "a", "value": {"ref": "locals.nope"}}], [card(10)], CANVAS
        )
    with pytest.raises(RuleError):
        evaluate_rule(
            [{"op": "emit_target", "kind": "move_existing", "target": "card", "x": 1, "y": 1}],
            [card(10)],
            CANVAS,
        )


def test_missing_key_messages_are_specific_so_model_retries_can_use_them():
    with pytest.raises(RuleError, match="clone_place needs a 'proto' key \\(not 'target'\\)"):
        validate_rule(
            [
                {
                    "op": "emit_target",
                    "kind": "clone_place",
                    "target": {"ref": "objects.1"},
                    "symbol": "s",
                    "x": 1,
                    "y": 1,
                }
            ]
        )
    with pytest.raises(RuleError, match="move_existing needs a 'target' key"):
        validate_rule(
            [
                {
                    "op": "emit_target",
                    "kind": "move_existing",
                    "proto": {"ref": "objects.1"},
                    "x": 1,
                    "y": 1,
                }
            ]
        )
