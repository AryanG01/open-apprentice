"""The numbers the UI shows are regenerated from stored results; this fails if the committed UI data drifts from them or mislabels an arm."""

import json
import os

import pytest

from scripts.analyze_audit_experiment import summarise

DATA = "apps/web/public/data/evidence.json"


@pytest.mark.skipif(not os.path.exists(DATA), reason="UI data not generated")
def test_experiment_arms_are_labelled_by_variant_and_match_the_stored_trials():
    exps = {e["variant"]: e for e in json.load(open(DATA)).get("experiments", [])}
    assert set(exps) <= {"control", "audit", "hybrid"} and len(exps) == len(
        json.load(open(DATA)).get("experiments", [])
    )
    for variant, d in (
        ("control", "results/exp_audit_control"),
        ("audit", "results/exp_audit_on"),
        ("hybrid", "results/exp_hybrid"),
    ):
        if variant in exps and os.path.isdir(d):
            m = summarise(d)
            assert (
                exps[variant]["committed"],
                exps[variant]["wrong"],
                exps[variant]["abstained"],
            ) == (m["committed"], m["wrong"], m["abstained"]), variant


@pytest.mark.skipif(not os.path.exists(DATA), reason="UI data not generated")
def test_out_of_grammar_rows_match_the_stored_trials():
    import glob

    for row in json.load(open(DATA)).get("oog", []):
        ts = [json.load(open(f)) for f in glob.glob(f"results/exp_oog_{row['variant']}/oog-*.json")]
        ready = [t for t in ts if t["final_state"] == "INTENT_READY"]
        assert (row["trials"], row["committed"], row["wrong"]) == (
            len(ts),
            len(ready),
            sum(1 for t in ready if t["recovered_latent_on_heldout"] is False),
        ), row["variant"]
