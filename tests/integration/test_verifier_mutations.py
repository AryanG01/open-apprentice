"""The independent verifier at its real boundary: native state that the REAL engine produced (Konva and Fabric), with one defect
injected into the native-state input `verify_story` inspects, and no gold output (`gold_applies=False`, as for an uploaded banner).
Opt-in: OA_ENGINE_TESTS=1. With OA_WRITE_MUTATION_TABLE=1 it also writes docs/evaluation/verifier_mutations.md and the valid
native states it started from. This checks the checker's structure and numbers, not pixels of an exported PNG."""

import copy
import json
import os
import pathlib

import pytest

from open_apprentice.evaluation.campaign_verifier import verify_story
from tests.integration.test_campaign_api import client  # noqa: F401  (fixture)

SHRINK, SPLIT = "builtin_shrink_hero", "builtin_split_two_cards"
CASES = [("short_a", None), ("de_long_a", SHRINK), ("de_long_a", SPLIT), ("fr_long", SPLIT)]
OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "evaluation"


def _by_role(native, role, board=None):
    return [
        n
        for n in native["nodes"]
        if n.get("role") == role and (board is None or n.get("parent") == board)
    ]


def _mut_delete(role):
    def m(s):
        s["nodes"] = [n for n in s["nodes"] if n.get("role") != role]

    return m


def _mut_duplicate(s):
    c = copy.deepcopy(_by_role(s, "product_image")[0])
    s["nodes"].append(c)


def _mut_orphan(s):
    _by_role(s, "headline")[0]["parent"] = "no-such-board"


def _mut_price(s):
    n = _by_role(s, "price")[0]
    n["text"] = n["text"].replace("179", "189").replace("159", "169")


def _mut_distort(s):
    _by_role(s, "product_image")[0]["width"] *= 1.3


def _mut_outside(s):
    n = _by_role(s, "headline")[0]
    n["x"] = 1075  # past the card's right safe area


def _mut_overflow(s):
    n = _by_role(s, "headline")[0]
    n["fontSize"] = n["fontSize"] * 3


MUTATIONS = [
    ("delete product image", _mut_delete("product_image"), {"source_complete"}),
    ("delete logo", _mut_delete("brand_mark"), {"source_complete"}),
    ("delete background", _mut_delete("background"), {"source_complete"}),
    ("delete headline", _mut_delete("headline"), {"source_complete"}),
    ("delete price", _mut_delete("price"), {"source_complete"}),
    ("delete button", _mut_delete("cta"), {"source_complete"}),
    ("duplicate product image", _mut_duplicate, {"source_complete"}),
    ("orphan the headline (missing parent)", _mut_orphan, {"source_complete"}),
    ("change a price digit", _mut_price, {"exact_copy"}),
    ("distort the product image width", _mut_distort, {"image_aspect"}),
    ("headline outside the safe area", _mut_outside, {"inside_safe"}),
    ("triple the headline font size", _mut_overflow, {"text_fits"}),
]


def _valid_results(client):
    """[(case label, engine, source, valid native)] from real runs."""
    out = []
    for engine in ("konva", "fabric"):
        for fid, choice in CASES:
            wid = client.post("/api/campaign/workspaces", json={"reading": "fixed"}).json()[
                "workspace_id"
            ]
            run = client.post(
                f"/api/campaign/workspaces/{wid}/runs", json={"fixture_id": fid, "backend": engine}
            ).json()
            if choice:
                assert run["status"] == "question", (fid, run["status"], run["problems"])
                run = client.post(
                    f"/api/campaign/workspaces/{wid}/runs/{run['run_id']}/answer",
                    json={"choice": choice},
                ).json()
            assert run["status"] in ("ready", "applied"), (fid, choice, run["status"])
            rec = client.app.state.campaign[wid].runs[run["run_id"]]
            snap = rec.snapshots[rec.run.result_session]
            out.append(
                (f"{fid}{'/' + choice[8:] if choice else ''}", engine, rec.source, snap["native"])
            )
    return out


def test_every_injected_defect_is_caught_and_valid_results_have_no_false_positive(client):
    rows, controls = [], []
    for label, engine, source, native in _valid_results(client):
        base = verify_story(source, native, None, gold_applies=False)
        controls.append((label, engine, sorted(base.failed()), len(base.checks)))
        assert base.passed, (label, engine, base.failed())
        if os.environ.get("OA_WRITE_MUTATION_TABLE") == "1":
            d = OUT / "verifier_mutation" / engine
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{label.replace('/', '_')}.native.json").write_text(
                json.dumps(native, indent=1, sort_keys=True)
            )
        for name, mutate, expected in MUTATIONS:
            bad = copy.deepcopy(native)
            try:
                mutate(bad)
            except (IndexError, KeyError):
                rows.append((label, engine, name, "n/a: the case has no such element", "", ""))
                continue
            rep = verify_story(source, bad, None, gold_applies=False)
            failed = set(rep.failed())
            assert not rep.passed and expected <= failed, (label, engine, name, sorted(failed))
            rows.append((label, engine, name, ", ".join(sorted(expected)), ", ".join(sorted(failed)), "caught"))
    if os.environ.get("OA_WRITE_MUTATION_TABLE") == "1":
        lines = [
            "# Verifier mutation table (real engine states, no gold)",
            "",
            "Generated by `tests/integration/test_verifier_mutations.py` (`OA_ENGINE_TESTS=1 OA_WRITE_MUTATION_TABLE=1`). Valid native",
            "states came from real Konva and Fabric runs; one defect was injected into the native state that `verify_story` inspects",
            "(mutation point: the final native scene's node list/attributes), and the verifier ran with `gold_applies=False`.",
            "This tests the checker's structure and numbers, **not** the pixels of an exported PNG, aesthetics or intent.",
            "Valid starting states: `docs/evaluation/verifier_mutation/<engine>/*.native.json`.",
            "",
            "## Valid controls (no injected defect)",
            "",
            "| Source case | Engine | Failed checks | Checks run | False positive |",
            "|---|---|---|---|---|",
        ]
        lines += [f"| {l} | {e} | {', '.join(f) or 'none'} | {n} | {'yes' if f else 'no'} |" for l, e, f, n in controls]
        lines += ["", "## Injected defects", "", "| Source case | Engine | Mutation | Expected failed check | Actual failed checks | Result |", "|---|---|---|---|---|---|"]
        lines += [f"| {' | '.join(r)} |" for r in rows]
        (OUT / "verifier_mutations.md").write_text("\n".join(lines) + "\n")
    caught = [r for r in rows if r[-1] == "caught"]
    assert len(caught) >= len(MUTATIONS) * len(controls) * 0.8  # most mutations apply to every case
