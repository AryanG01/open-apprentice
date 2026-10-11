"""The numbers the UI shows are regenerated from stored results; this fails if the committed UI data drifts from them or mislabels an arm."""

import json
import os

import pytest

from scripts.analyze_audit_experiment import summarise

DATA = "apps/web/public/data/evidence.json"


@pytest.mark.skipif(not os.path.exists(DATA), reason="UI data not generated")
def test_experiment_arms_are_labelled_by_variant_and_match_the_stored_trials():
    exps = {e["variant"]: e for e in json.load(open(DATA)).get("experiments", [])}
    assert set(exps) <= {"control", "audit"} and len(exps) == len(
        json.load(open(DATA)).get("experiments", [])
    )
    for variant, d in (("control", "results/exp_audit_control"), ("audit", "results/exp_audit_on")):
        if variant in exps and os.path.isdir(d):
            m = summarise(d)
            assert (
                exps[variant]["committed"],
                exps[variant]["wrong"],
                exps[variant]["abstained"],
            ) == (m["committed"], m["wrong"], m["abstained"]), variant
