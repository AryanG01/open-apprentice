"""The runner + non-LLM reference on REAL engines, DEVELOPMENT split only. These assert the harness's structural
properties (sealing, cost rows, leakage, labels). The reference's measured numbers are logged, not asserted."""

import json

import pytest

from open_apprentice.agent.policies import ReferencePolicy
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.episodes import make_manifest
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.evaluation.metrics import method_summary
from open_apprentice.evaluation.report import build_report
from open_apprentice.evaluation.runner import run_episode

TOKEN = "e2e-token"
DOM = DomainManifest()


@pytest.fixture(scope="module")
def dev_rows(engine_url):
    import asyncio

    m = make_manifest("development", 0, 12)
    eps = [
        m.episodes[0],
        m.episodes[2],
    ]  # indices 0 and 2: drift schedule includes a no-change control and a drift episode
    rows = []
    global POLICIES
    POLICIES = []

    async def go():
        with SolverPool() as pool:
            for e in eps:
                pol = ReferencePolicy()
                POLICIES.append(pol)
                rows.extend(
                    await run_episode(
                        e, pol, EvaluatorHarness(engine_url, TOKEN), DOM, pool, origin="reference"
                    )
                )

    asyncio.run(go())
    return eps, rows


def test_every_episode_has_one_learning_row_and_eight_scored_rows(dev_rows):
    eps, rows = dev_rows
    for e in eps:
        er = [r for r in rows if r.episode == e.episode_id]
        assert [r.stage for r in er].count("learning") == 1 and len(
            [r for r in er if r.stage != "learning"]
        ) == 8


def test_learning_costs_include_teacher_interactions_and_solver_time_and_are_not_scored(dev_rows):
    _, rows = dev_rows
    learn = [r for r in rows if r.stage == "learning"]
    assert all(
        r.teacher_interactions >= 0 and r.committed is False and r.correct is None for r in learn
    )
    s = method_summary(rows, "enumerative_reference")
    assert s["success"]["scheduled"] == 16 and s["costs"]["teacher_interactions"] == sum(
        r.teacher_interactions for r in rows
    )


def test_rows_never_contain_private_labels_and_origin_is_reference(dev_rows):
    _, rows = dev_rows
    blob = json.dumps([r.__dict__ for r in rows]).lower()
    assert all(r.origin == "reference" for r in rows)
    for secret in ("move_origin", "move_anchor", "drift", "latent", "clamp", "template"):
        assert secret not in blob


def test_scores_come_only_from_the_independent_verifier_after_commitment(dev_rows):
    _, rows = dev_rows
    for r in rows:
        if r.stage == "learning":
            continue
        assert (r.correct is None) == (not r.committed)  # unscored unless committed
        assert not (r.claimed_success and not r.committed)


def test_report_for_reference_rows_is_labelled_and_log_real_numbers(dev_rows, capsys):
    _, rows = dev_rows
    rep = build_report(
        rows,
        ["enumerative_reference"],
        ("enumerative_reference", "enumerative_reference"),
        "dev-reference",
        allow_mock=True,
    )
    s = rep["methods_all_stages"]["enumerative_reference"]
    with capsys.disabled():
        print("\nREFERENCE (non-LLM) on 2 DEVELOPMENT episodes - harness check, not a study:")
        print(
            " success",
            s["success"],
            "| conditional",
            s["conditional"],
            "| false_success",
            s["false_success"],
        )
        for r in rows:
            if r.stage != "learning" and not (r.committed and r.correct):
                print(
                    f" NOT CORRECT: ep={r.episode} stage={r.stage} committed={r.committed} abstained={r.abstained} failure={r.failure} correct={r.correct}"
                )
        for pol in POLICIES:
            for st in pol.stats:
                if "repair" in st:
                    print(" REPAIR:", st)
        print(
            " failures",
            s["failures"],
            "| costs",
            {k: v for k, v in s["costs"].items() if k != "usd_known_total"},
        )
