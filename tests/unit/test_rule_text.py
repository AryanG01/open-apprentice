"""The text front-end compiles to the SAME restricted AST. Equivalence is judged by behaviour against the already
verified fixture ASTs on many in-domain scenes (exact rationals), not by text matching."""

from fractions import Fraction as F

import pytest

from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.query_selection import sample_scenes
from open_apprentice.concepts.rule_text import RuleSyntaxError, parse_rule_text
from open_apprentice.concepts.rules import RuleError, evaluate_rule, validate_rule
from open_apprentice.concepts.symbolic import Unsupported, compile_rule, make_inputs
from tests.fixtures_rules import (
    CLAMPED_MARGIN,
    CONST_MARGIN,
    PROP_MARGIN,
    center_spacing_rule,
    gap_rule,
)

DOM = DomainManifest()
BADGE = "clone objects[1] as badge at (objects[0].x + objects[0].w - m - objects[1].w, objects[0].y + m)"


def same(text, fixture, counts):
    ast = parse_rule_text(text)
    validate_rule(ast)
    for sc in sample_scenes(DOM, counts, 25, seed=3):
        assert evaluate_rule(ast, sc["objects"], sc["canvas"]) == evaluate_rule(
            fixture, sc["objects"], sc["canvas"]
        )


def test_badge_rules_match_the_verified_fixtures():
    same("let m = 12\n" + BADGE, CONST_MARGIN, [2])
    same("let m = 0.08 * objects[0].w\n" + BADGE, PROP_MARGIN(), [2])
    same("# clamp\nlet m = min(24, max(8, 0.08 * objects[0].w))\n" + BADGE, CLAMPED_MARGIN(), [2])


def test_spacing_rules_with_loops_and_index_vars_match_the_fixtures():
    same(
        "let cursor = 80\nfor o in objects { move o to (cursor, 120)\n let cursor = cursor + o.w + 24 }",
        gap_rule(24, 80, 120),
        [3, 4],
    )
    same(
        "let c = 80 + objects[0].w / 2\nfor o in objects {\n move o to (c - o.w / 2, 120)\n let c = c + 100\n}",
        center_spacing_rule(100, 80, 120),
        [3, 5],
    )


def test_precedence_unary_minus_decimals_comparisons_and_branches():
    t = (
        "let a = 2 + 3 * 4 - 10 / 4\nlet b = -a + 0.5\n"
        "if objects[0].w >= 100 and not objects[0].h < 30 { move objects[0] to (a, b) } else { move objects[0] to (0, 0) }"
    )
    sc = {
        "objects": [{"id": "o", "x": F(0), "y": F(0), "w": F(120), "h": F(50)}],
        "canvas": {"w": F(800), "h": F(600)},
    }
    out = evaluate_rule(parse_rule_text(t), sc["objects"], sc["canvas"])
    assert (out["o"]["x"], out["o"]["y"]) == (
        F(2 + 12 - 5, 2) * 1 + 0 if False else F(23, 2),
        F(-23, 2) + F(1, 2),
    )
    sc["objects"][0]["w"] = F(60)
    assert evaluate_rule(parse_rule_text(t), sc["objects"], sc["canvas"])["o"]["x"] == 0


def test_decimals_are_exact_rationals_not_floats():
    ast = parse_rule_text("let m = 0.1 * objects[0].w\nmove objects[0] to (m, 0)")
    assert ast[0]["value"]["args"][0] == {"rat": "1/10"}
    sc = [{"id": "o", "x": F(0), "y": F(0), "w": F(3), "h": F(5)}]
    assert evaluate_rule(ast, sc, {"w": 9, "h": 9})["o"]["x"] == F(3, 10)


def test_parsed_rules_go_through_the_z3_compiler_and_the_unsupported_cases_are_still_unsupported():
    o, c, _ = make_inputs(2)
    compile_rule(parse_rule_text("let m = 0.08 * objects[0].w\n" + BADGE), o, c)
    with pytest.raises(Unsupported):
        compile_rule(parse_rule_text("move objects[0] to (objects[0].w * objects[1].w, 0)"), o, c)


@pytest.mark.parametrize(
    "bad,frag",
    [
        ("let m = ", "expected a number"),
        ("let m = (1 + 2", "expected ')'"),
        ("move objects[0] (1, 2)", "expected 'to'"),
        ("let a = unknown + 1", "unknown name 'unknown'"),
        ("clone objects[1] badge at (0, 0)", "expected 'as'"),
        ("move objects[1.5] to (0, 0)", "whole number"),
        ("for o in canvas { }", "only 'objects' can be iterated"),
        ("let a = objects[0].z", "x, y, w, h"),
        ("let a = canvas.depth", "canvas has only"),
        ("let a = 1 $ 2", "unexpected character"),
        ("", "empty rule"),
        ("let a = 1\n}", "unexpected closing brace"),
    ],
)
def test_syntax_errors_are_specific_and_carry_a_line_number(bad, frag):
    with pytest.raises(RuleSyntaxError) as e:
        parse_rule_text(bad)
    assert frag in str(e.value) and (
        str(e.value).startswith("line ") or frag == "empty rule" or "too long" in frag
    )


def test_error_reports_the_right_line_number():
    with pytest.raises(RuleSyntaxError, match="^line 3:"):
        parse_rule_text("let a = 1\nlet b = 2\nlet c = (")


def test_no_code_execution_surface():
    for evil in (
        "let a = __import__('os')",
        "let a = open('x')",
        "let a = objects[0].__class__",
        "move objects[0] to (eval('1'), 0)",
    ):
        with pytest.raises(RuleError):
            parse_rule_text(evil)
    with pytest.raises(RuleSyntaxError, match="too long"):
        parse_rule_text("let a = 1\n" * 1000)


def test_wrapped_expressions_and_trailing_operators_still_parse_and_statements_split_on_newlines():
    t = "let m = min(24,\n   max(8,\n  0.08 * objects[0].w))\nlet n = 1 +\n 2\n" + BADGE
    ast = parse_rule_text(t)
    assert [x["op"] for x in ast] == ["let", "let", "emit_target"]
    same("let m = min(24,\n max(8, 0.08 * objects[0].w))\n" + BADGE, CLAMPED_MARGIN(), [2])
    with pytest.raises(RuleSyntaxError, match="^line 2:"):
        parse_rule_text(
            "let a = 1\nlet b = 2 3"
        )  # two statements cannot share a line without separation


def test_demonstration_ids_resolve_by_position_so_the_rule_stays_positional():
    ali = {"card0": 0, "proto": 1}
    a = parse_rule_text(
        "let m = 12\nclone proto as badge at (card0.x + card0.w - m - proto.w, card0.y + m)", ali
    )
    validate_rule(a)
    same_ast = parse_rule_text("let m = 12\n" + BADGE)
    for sc in sample_scenes(
        DOM, [2], 10, seed=5
    ):  # different ids in these scenes: still identical behaviour
        assert evaluate_rule(a, sc["objects"], sc["canvas"]) == evaluate_rule(
            same_ast, sc["objects"], sc["canvas"]
        )
    with pytest.raises(RuleSyntaxError, match="unknown name 'proto'"):
        parse_rule_text("clone proto as badge at (0, 0)")  # without aliases it is still an error
    # a let/loop variable shadows an alias
    b = parse_rule_text("let card0 = 5\nmove objects[0] to (card0, 0)", ali)
    assert b[1]["x"] == {"ref": "locals.card0"}


def test_label_rules_parse_strings_text_fields_and_object_lookup():
    from open_apprentice.concepts.rule_text import parse_rule_text
    from open_apprentice.concepts.rules import evaluate_rule, validate_rule

    src = (
        'for o in objects {\n  if o.kind == "label" and o.role != "warning" {\n'
        "    let a = object(o.attached)\n    move o to (a.x + a.w + 12, a.y)\n  }\n}"
    )
    rule = parse_rule_text(src)
    validate_rule(rule)
    scene = [
        {
            "id": "n",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": 10,
            "y": 20,
            "w": 100,
            "h": 40,
        },
        {
            "id": "l",
            "kind": "label",
            "role": "note",
            "attached": "n",
            "x": 0,
            "y": 0,
            "w": 30,
            "h": 10,
        },
        {
            "id": "m",
            "kind": "label",
            "role": "warning",
            "attached": "n",
            "x": 5,
            "y": 5,
            "w": 30,
            "h": 10,
        },
    ]
    out = evaluate_rule(rule, scene, {"w": 500, "h": 500})
    assert (out["l"]["x"], out["l"]["y"]) == (122, 20) and (out["m"]["x"], out["m"]["y"]) == (5, 5)


def test_the_symbolic_compiler_reports_text_fields_as_unsupported_not_as_a_crash():
    import pytest

    from open_apprentice.concepts.rule_text import parse_rule_text
    from open_apprentice.concepts.symbolic import Unsupported, compile_rule, make_inputs

    rule = parse_rule_text('for o in objects { if o.kind == "label" { move o to (0, 0) } }')
    o, cv, _ = make_inputs(2)
    with pytest.raises(Unsupported):
        compile_rule(rule, o, cv)


def test_single_quoted_strings_parse_like_double_quoted():
    from open_apprentice.concepts.rule_text import parse_rule_text

    assert parse_rule_text(
        "for o in objects { if o.kind == 'label' { move o to (0, 0) } }"
    ) == parse_rule_text('for o in objects { if o.kind == "label" { move o to (0, 0) } }')


def test_runaway_nested_loops_hit_the_step_budget_instead_of_hanging():
    import time

    from open_apprentice.concepts.rules import RuleError, evaluate_rule

    loops = "for a in objects {\n for b in objects {\n for c in objects {\n for d in objects {\n for e in objects {\n let z = 1\n}\n}\n}\n}\n}"
    rule = parse_rule_text(loops)
    objs = [{"id": f"o{i}", "x": i, "y": 0, "w": 5, "h": 5} for i in range(22)]
    t = time.time()
    with pytest.raises(RuleError, match="too many steps"):
        evaluate_rule(rule, objs, {"w": 1200, "h": 800})
    assert time.time() - t < 10
