from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.concepts.rules import evaluate_rule, evaluate_rule_counted
from open_apprentice.teaching.step import run_output, run_output_counted

RIGHT = parse_rule_text(
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n'
    "    move o to (a.x + a.w + 12, a.y)\n  }\n}"
)
NESTED = parse_rule_text("for o in objects {\n  for p in objects {\n    let z = 0\n  }\n}")


def scene(n):
    objs = [
        {"id": "n0", "kind": "node", "role": "", "attached": "", "x": 0, "y": 0, "w": 50, "h": 20}
    ]
    for i in range(n - 1):
        objs.append(
            {
                "id": f"l{i}",
                "kind": "label",
                "role": "note",
                "attached": "n0",
                "x": 0,
                "y": 30 * i,
                "w": 20,
                "h": 10,
            }
        )
    return {"objects": objs, "canvas": {"w": 400, "h": 400}}


def test_counted_matches_plain_evaluation():
    sc = scene(2)
    out, n = evaluate_rule_counted(RIGHT, sc["objects"], sc["canvas"])
    assert out == evaluate_rule(RIGHT, sc["objects"], sc["canvas"]) and n > 0
    o2, n2 = run_output_counted(RIGHT, sc)
    assert o2 == run_output(RIGHT, sc) and n2 == n


def test_more_objects_cost_more_statements_in_nested_loops():
    assert (
        evaluate_rule_counted(NESTED, scene(3)["objects"], scene(3)["canvas"])[1]
        > evaluate_rule_counted(NESTED, scene(2)["objects"], scene(2)["canvas"])[1]
    )


def test_a_failing_rule_still_counts_the_statements_it_ran():
    bad = parse_rule_text(
        'for o in objects {\n  let a = object("missing")\n  move o to (a.x, a.y)\n}'
    )
    out, n = run_output_counted(bad, scene(2))
    assert out is None and n >= 1  # the budget pays for work done before the failure
