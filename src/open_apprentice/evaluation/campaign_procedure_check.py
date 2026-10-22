"""Evaluator-side acceptance check for a native procedure (plan 9E): run it on a retained banner and two fresh ones on
one backend and judge each result with the independent verifier against the authored gold."""

from __future__ import annotations

import asyncio

from open_apprentice.campaign.builtins import split_two_cards
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.layout_rule import evaluate_layout, objects_for_rule, wrap_learned
from open_apprentice.campaign.learn import learn_layout
from open_apprentice.campaign.model_procedures import ProcedureCheck
from open_apprentice.campaign.plan import plan_from_layout
from open_apprentice.campaign.procedures import apply_plan
from open_apprentice.evaluation.campaign_gold import load_gold
from open_apprentice.evaluation.campaign_verifier import verify_story
from open_apprentice.evaluation.harness import EvaluatorHarness

CASES = (
    ("teach_before", "layout"),
    ("short_b", "layout"),
    ("de_long_a", "split"),
)  # retained, then fresh
OWNER = "procedure-check"


def check_procedure(program: list, backend: str, engine_url: str, token: str) -> ProcedureCheck:
    learned = asyncio.run(
        learn_layout(load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"])
    )
    harness = EvaluatorHarness(engine_url, token)
    cases = []
    for fid, outcome in CASES:
        src = load_fixture(fid)["scene"]
        res = evaluate_layout(
            wrap_learned(learned.rule),
            objects_for_rule(src, "banner"),
            {"output_format": "9:16", "overflows": False},
        )
        plan = plan_from_layout(res, src, "banner", learned.origin)
        if outcome == "split":
            plan = split_two_cards(plan)
        try:  # any failure (a broken candidate, the engine at its cap, a timeout) is a failed case, never a crash
            session, _ = harness.open_session(src, OWNER, backend=backend)
        except Exception as e:  # noqa: BLE001
            cases.append(
                {
                    "fixture": fid,
                    "outcome": outcome,
                    "passed": False,
                    "failed_checks": [],
                    "error": f"{type(e).__name__}: {str(e)[:160]}",
                }
            )
            continue
        try:
            apply_plan(session, plan, program, "model")
            report = verify_story(
                src, harness.native(session.session_id, OWNER), load_gold(fid, outcome)["scene"]
            )
            cases.append(
                {
                    "fixture": fid,
                    "outcome": outcome,
                    "passed": report.passed,
                    "failed_checks": report.failed(),
                }
            )
        except Exception as e:  # noqa: BLE001
            cases.append(
                {
                    "fixture": fid,
                    "outcome": outcome,
                    "passed": False,
                    "failed_checks": [],
                    "error": f"{type(e).__name__}: {str(e)[:160]}",
                }
            )
        finally:
            try:
                session.close()
            except Exception:  # noqa: BLE001 - the engine reaps an idle session
                pass
    return ProcedureCheck(all(c["passed"] for c in cases), cases)
