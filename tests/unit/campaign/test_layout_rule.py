from fractions import Fraction

import pytest

from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.layout_rule import evaluate_layout, objects_for_rule, wrap_learned
from open_apprentice.concepts.rules import RuleError, validate_rule
from open_apprentice.concepts.symbolic import Unsupported, compile_rule, make_inputs

ROLE = lambda r: {"op": "eq", "args": [{"op": "get", "args": [{"ref": "locals.o"}, "role"]}, r]}
PLACE_HEAD = {
    "op": "emit_target",
    "kind": "place",
    "target": {"ref": "locals.o"},
    "x": 72,
    "y": 1080,
    "w": 936,
    "h": 160,
    "parent": "story-1",
    "z": 3,
}
STYLE_HEAD = {"op": "emit_target", "kind": "style", "target": {"ref": "locals.o"}, "fontSize": 72}
FIT_HERO = {
    "op": "emit_target",
    "kind": "fit_image",
    "target": {"ref": "locals.o"},
    "x": 180,
    "y": 320,
    "w": 720,
    "h": 720,
}
BODY = [
    {
        "op": "for_each",
        "over": {"ref": "objects"},
        "var": "o",
        "body": [
            {"op": "if", "cond": ROLE("headline"), "then": [PLACE_HEAD, STYLE_HEAD]},
            {"op": "if", "cond": ROLE("product_image"), "then": [FIT_HERO]},
        ],
    }
]
ASK = {"op": "ask", "options": ["builtin_shrink_hero", "builtin_split_two_cards"]}
FACTS = {"op": "if", "cond": {"ref": "facts.overflows"}, "then": [ASK]}


def _objs():
    return objects_for_rule(load_fixture("short_a")["scene"], "banner")


@pytest.mark.parametrize("stmt", [PLACE_HEAD, STYLE_HEAD, FIT_HERO, ASK, FACTS])
def test_campaign_constructs_need_the_campaign_dialect(stmt):
    body = [{"op": "for_each", "over": {"ref": "objects"}, "var": "o", "body": [stmt]}]
    validate_rule(body, campaign=True)
    with pytest.raises(RuleError):
        validate_rule(body)


@pytest.mark.parametrize(
    "extra", [{"text": "Hi"}, {"link": "https://x"}, {"asset": "h7-headphones"}, {"fill": "#fff"}]
)
def test_non_writable_fields_are_rejected(extra):
    with pytest.raises(RuleError):
        validate_rule(
            [
                {
                    "op": "for_each",
                    "over": {"ref": "objects"},
                    "var": "o",
                    "body": [dict(PLACE_HEAD, **extra)],
                }
            ],
            campaign=True,
        )


def test_old_emit_kinds_are_not_part_of_the_dialect():
    old = {
        "op": "emit_target",
        "kind": "move_existing",
        "target": {"ref": "objects.0"},
        "x": 1,
        "y": 1,
    }
    with pytest.raises(RuleError):
        validate_rule([old], campaign=True)


def test_ask_options_are_exactly_the_builtins():
    with pytest.raises(RuleError):
        validate_rule([{"op": "ask", "options": ["builtin_shrink_hero"]}], campaign=True)


def test_wrapped_rule_returns_targets_when_it_fits():
    out = evaluate_layout(
        wrap_learned(BODY), _objs(), {"output_format": "9:16", "overflows": False}
    )
    assert out.ask is None
    head = out.targets["sa-head"]
    assert (head.x, head.y, head.w, head.h, head.parent, head.z, head.font_size) == (
        72,
        1080,
        936,
        160,
        "story-1",
        3,
        72,
    )
    assert out.targets["sa-hero"].contain is True
    assert isinstance(head.x, Fraction)


def test_wrapped_rule_asks_on_overflow():
    out = evaluate_layout(wrap_learned(BODY), _objs(), {"output_format": "9:16", "overflows": True})
    assert out.ask == ("builtin_shrink_hero", "builtin_split_two_cards")
    assert out.targets == {}


def test_other_formats_emit_nothing():
    out = evaluate_layout(
        wrap_learned(BODY), _objs(), {"output_format": "16:9", "overflows": False}
    )
    assert out.ask is None and out.targets == {}


def test_symbolic_compiler_reports_campaign_rules_unsupported():
    objs, cv, _ = make_inputs(2)
    with pytest.raises(Unsupported):
        compile_rule(wrap_learned(BODY), objs, cv)


def test_objects_for_rule_has_roles_and_cta_children():
    roles = sorted(o["role"] for o in _objs())
    assert roles == sorted(
        [
            "background",
            "brand_mark",
            "product_image",
            "headline",
            "price",
            "cta",
            "legal",
            "cta/shape",
            "cta/text",
        ]
    )
