"""Offline end-to-end: REAL Konva engine (node subprocess) + MOCK provider + fresh agent + independent verifier.

Mock replies are scripted fixtures (origin=fixture), not learned skills. Run with:
  OA_ENGINE_TESTS=1 pytest tests/integration/test_offline_e2e.py   (needs Chromium; unsandboxed shell)
"""

from open_apprentice.agent.fresh import run_fresh
from open_apprentice.budget import Ledger, Limits
from open_apprentice.environments.tasks import agent_view, make_gap_row_task
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.providers.mock import MockProvider

TOKEN = "e2e-token"


def program(task, *, frame_dx=0, frame_dy=0):
    """Fixture solver: measure each card, place at cursor (converted into the parent frame)."""
    p = task["parameters"]
    return [
        {"op": "let", "name": "cursor", "value": p["left_px"]},
        {
            "op": "for_each",
            "var": "id",
            "over": task["selected_ids"],
            "body": [
                {
                    "op": "call",
                    "tool": "measure_node",
                    "args": {"node_id": {"ref": "locals.id"}},
                    "bind": "m",
                },
                {
                    "op": "call",
                    "tool": "move_node",
                    "args": {
                        "node_id": {"ref": "locals.id"},
                        "x": {"op": "sub", "args": [{"ref": "locals.cursor"}, frame_dx]},
                        "y": p["top_px"] - frame_dy,
                    },
                },
                {
                    "op": "let",
                    "name": "cursor",
                    "value": {
                        "op": "add",
                        "args": [
                            {"ref": "locals.cursor"},
                            {"op": "add", "args": [{"ref": "locals.m.width"}, p["gap_px"]]},
                        ],
                    },
                },
            ],
        },
    ]


def run(engine_url, task, scene, script, private=None, owner="e2e"):
    import asyncio

    h = EvaluatorHarness(engine_url, TOKEN)
    sess, initial = h.open_session(scene, owner, private)
    led = Ledger(Limits(tokens=200_000, calls=20, actions=800))
    prov = MockProvider({"fresh": script})
    try:
        res = asyncio.run(run_fresh(agent_view(task), sess, prov, led))
        return res, h.judge_gap_row(sess, initial, task), led
    finally:
        sess.close()


def test_flat_task_solved_first_cycle_and_verified_independently(engine_url):
    task, scene = make_gap_row_task(1)
    res, rep, led = run(
        engine_url, task, scene, [{"diagnosis": "fixture", "program": program(task)}]
    )
    assert res.status == "operational_pass" and res.cycles == 1
    assert rep.passed, [(c.name, c.detail) for c in rep.checks if not c.passed]
    assert led.consumed_actions > 0 and res.trace[0]["provider"] == "MOCK"


def test_naive_program_fails_on_nested_scene_then_agent_corrects_with_feedback(engine_url):
    task, scene = make_gap_row_task(2, nested=True)  # parent frame offset (20, 10)
    naive = {"diagnosis": "assumes world frame", "program": program(task)}
    fixed = {
        "diagnosis": "parent is offset by (20,10)",
        "program": program(task, frame_dx=20, frame_dy=10),
    }
    res, rep, _ = run(engine_url, task, scene, [naive, fixed])
    assert res.cycles == 2 and res.status == "operational_pass"
    assert not res.trace[0]["feedback"]["passed"] and res.trace[1]["feedback"]["passed"]
    assert rep.passed, [(c.name, c.detail) for c in rep.checks if not c.passed]


def test_drift_makes_a_previously_correct_program_fail_all_cycles(engine_url):
    task, scene = make_gap_row_task(2, nested=True)
    fixed = {"diagnosis": "parent-local plan", "program": program(task, frame_dx=20, frame_dy=10)}
    res, rep, _ = run(
        engine_url, task, scene, [fixed, fixed, fixed], private={"move_frame": "world"}
    )
    assert (
        res.status == "operational_fail" and not rep.passed
    )  # same public schema, silently different semantics
