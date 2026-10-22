import asyncio
import copy

import pytest

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.learn import learn_layout
from open_apprentice.campaign.model_procedures import write_procedure
from open_apprentice.campaign.preferences import PreferenceStore
from open_apprentice.campaign.procedures import APPLY_PLAN
from open_apprentice.campaign.run import close_run, start_run
from open_apprentice.evaluation.campaign_procedure_check import check_procedure
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.providers.mock import MockProvider
from open_apprentice.storage.store import LocalStore

from .conftest import TOKEN

# teaching-banner ids baked in: works on the teaching banner only
HARD_CODED = [
    {"op": "call", "tool": "move_node", "args": {"node_id": "tb-head", "x": 72, "y": 1080}}
]


@pytest.mark.parametrize("backend", ["konva", "fabric"])
def test_the_reference_procedure_passes_the_check(engine_url, backend):
    r = check_procedure(APPLY_PLAN, backend, engine_url, TOKEN)
    assert r.passed, r.cases


@pytest.mark.parametrize("backend", ["konva", "fabric"])
def test_a_model_program_is_accepted_only_through_the_check(engine_url, backend):
    good = copy.deepcopy(APPLY_PLAN)
    provider = MockProvider(
        {
            "campaign_procedure": [
                {
                    "candidates": [
                        {"program": HARD_CODED, "summary": "x"},
                        {"program": good, "summary": "y"},
                    ]
                }
            ]
        }
    )
    out = asyncio.run(
        write_procedure(
            provider,
            Ledger(Limits(tokens=200_000, calls=4)),
            backend,
            lambda p: check_procedure(p, backend, engine_url, TOKEN),
        )
    )
    assert out.origin == "model" and out.program == good
    assert out.attempts[0]["passed"] is False and out.attempts[1]["passed"] is True


def test_a_hard_coded_program_never_replaces_the_reference(engine_url):
    provider = MockProvider(
        {"campaign_procedure": [{"candidates": [{"program": HARD_CODED, "summary": "x"}]}] * 3}
    )
    out = asyncio.run(
        write_procedure(
            provider,
            Ledger(Limits(tokens=200_000, calls=4)),
            "konva",
            lambda p: check_procedure(p, "konva", engine_url, TOKEN),
        )
    )
    assert out.origin == "reference" and out.program == APPLY_PLAN and len(out.attempts) == 3


def test_a_run_records_an_accepted_model_procedure(engine_url, tmp_path):
    harness = EvaluatorHarness(engine_url, TOKEN)
    learned = asyncio.run(
        learn_layout(load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"])
    )
    f = load_fixture("short_a")
    run = start_run(
        f["scene"],
        f["locale"],
        learned,
        lambda s: harness.open_session(s, "p", backend="fabric")[0],
        PreferenceStore(LocalStore(tmp_path)),
        procedure=(copy.deepcopy(APPLY_PLAN), "model"),
    )
    try:
        assert run.status == "ready" and run.provenance["procedure_origin"] == "model"
    finally:
        close_run(run)
