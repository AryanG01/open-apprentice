import pytest

from open_apprentice.skills.interpreter import (
    AssertionRejected,
    ProgramError,
    run_program,
    validate_program,
)


def R(p):
    return {"ref": p}


def B(op, *a):
    return {"op": op, "args": list(a)}


def gap_row_program():
    return [
        {"op": "let", "name": "cursor", "value": R("inputs.left")},
        {
            "op": "for_each",
            "var": "n",
            "over": R("inputs.node_ids"),
            "body": [
                {
                    "op": "call",
                    "tool": "move_node",
                    "args": {
                        "node_id": R("locals.n"),
                        "x": R("locals.cursor"),
                        "y": R("inputs.top"),
                    },
                },
                {
                    "op": "let",
                    "name": "cursor",
                    "value": B("add", R("locals.cursor"), B("add", 50, R("inputs.gap"))),
                },
            ],
        },
        {"op": "return", "value": R("locals.cursor")},
    ]


def test_runs_loop_and_counts_expanded_actions():
    calls = []
    tools = {"move_node": lambda node_id, x, y: calls.append((node_id, x, y))}
    out, used = run_program(
        gap_row_program(), {"left": 80, "top": 120, "gap": 24, "node_ids": ["a", "b", "c"]}, tools
    )
    assert calls == [("a", 80, 120), ("b", 154, 120), ("c", 228, 120)]
    assert out == 302 and used["actions"] == 3


def test_unknown_tool_rejected_statically():
    with pytest.raises(ProgramError, match="allowlisted"):
        run_program([{"op": "call", "tool": "rm_rf", "args": {}}], {}, {"move_node": print})


def test_division_by_zero_and_nonfinite_rejected():
    with pytest.raises(ProgramError, match="zero"):
        run_program([{"op": "return", "value": B("div", 1, 0)}], {}, {})
    with pytest.raises(ProgramError, match="non-finite"):
        run_program([{"op": "return", "value": {"lit": float("inf")}}], {}, {})
    with pytest.raises(ProgramError):
        run_program([{"op": "return", "value": B("mul", 1e308, 1e308)}], {}, {})


@pytest.mark.parametrize(
    "path", ["inputs.__proto__", "inputs.constructor", "globals.x", "inputs.missing", "locals.nope"]
)
def test_bad_references_rejected(path):
    with pytest.raises(ProgramError):
        run_program([{"op": "return", "value": R(path)}], {"a": 1}, {})


def test_prototype_keys_in_statement_rejected():
    with pytest.raises(ProgramError):
        validate_program([{"op": "let", "name": "x", "value": 1, "__proto__": {}}], frozenset())


def test_limits():
    with pytest.raises(ProgramError, match="too many"):
        validate_program([{"op": "let", "name": "x", "value": 1}] * 65, frozenset())
    from open_apprentice.skills.interpreter import MAX_DEPTH

    deep = [{"op": "return", "value": 1}]
    for _ in range(MAX_DEPTH):
        deep = [{"op": "if", "cond": True, "then": deep}]
    with pytest.raises(ProgramError, match="deep"):
        validate_program(deep, frozenset())
    with pytest.raises(ProgramError, match="16"):
        run_program(
            [{"op": "for_each", "var": "i", "over": R("inputs.xs"), "body": []}],
            {"xs": list(range(17))},
            {},
        )


def test_action_budget_counts_expanded_loops():
    prog = [
        {
            "op": "for_each",
            "var": "i",
            "over": R("inputs.xs"),
            "body": [
                {
                    "op": "for_each",
                    "var": "j",
                    "over": R("inputs.xs"),
                    "body": [{"op": "call", "tool": "t", "args": {}}],
                }
            ],
        }
    ]
    with pytest.raises(ProgramError, match="action budget"):
        run_program(prog, {"xs": list(range(11))}, {"t": lambda: None})  # 121 > 100


def test_expression_budget():
    e = {"lit": 0}
    for _ in range(600):
        e = B("add", e, 1)
    with pytest.raises(ProgramError, match="expression budget"):
        run_program([{"op": "return", "value": e}], {}, {})


def test_assert_rejects_attempt():
    with pytest.raises(AssertionRejected, match="bad"):
        run_program([{"op": "assert", "cond": B("lt", 2, 1), "message": "bad"}], {}, {})


def test_list_op_builds_bounded_arrays_from_computed_values():
    out, _ = run_program(
        [
            {"op": "let", "name": "a", "value": 5},
            {"op": "return", "value": B("list", R("locals.a"), 7)},
        ],
        {},
        {},
    )
    assert out == [5, 7]
    with pytest.raises(ProgramError, match="16"):
        run_program([{"op": "return", "value": B("list", *range(17))}], {}, {})


def test_name_op_joins_two_strings_only():
    out, _ = run_program(
        [{"op": "return", "value": B("name", "badge_", R("inputs.id"))}], {"id": "c1"}, {}
    )
    assert out == "badge_c1"
    for bad in (B("name", "a"), B("name", "a", 3), B("name", "x" * 60, "y" * 60)):
        with pytest.raises(ProgramError):
            run_program([{"op": "return", "value": bad}], {}, {})


def test_huge_integers_are_a_program_error_not_a_crash():
    # math.isfinite(10**400) raises OverflowError; a model-written program must never turn that into a server error
    with pytest.raises(ProgramError):
        run_program([{"op": "return", "value": {"lit": 10**400}}], {}, {})
