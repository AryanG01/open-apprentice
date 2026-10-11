"""Build apps/web/public/data/{demo,evidence}.json for the UI.

demo.json     RECORDED offline story run on the REAL Konva and Fabric engines with the REAL independent verifier.
              No language model is involved: the candidate rules and the two binding programs are scripted fixtures
              (labelled as such in the file). It shows the mechanism, it is not a model result.
evidence.json Stored LIVE-model pilot results, rebuilt from results/ (rows.jsonl, learn-*.json) by counting stored rows.
              Nothing is typed by hand; development-split numbers are labelled as such.

Run (needs Chromium, so unsandboxed):  PYTHONPATH=src:. python scripts/build_demo_bundle.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import glob
import json
import os
from datetime import datetime, timezone
from fractions import Fraction as F

from open_apprentice.budget import Ledger, Limits
from open_apprentice.api.geometry import (
    boxes_of_scene,
    boxes_of_targets,
    card_scene,
    fl,
    observed_boxes,
)
from open_apprentice.concepts.bindings import (
    BindingRegistry,
    NativeBudget,
    backend_scene,
    expected_state,
    native_run,
    targets_from_rule,
)
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.query_selection import (
    build_query,
    candidate_set_hash,
    public_view,
    score_scene,
)
from open_apprentice.concepts.schemas import Concept, IntentState, TeachingLedger
from open_apprentice.concepts.transfer import repair_binding, transfer_concept
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.evaluation.local_engine import local_engine
from open_apprentice.evaluation.metrics import Row
from open_apprentice.providers.mock import MockProvider
from tests.fixtures_rules import CLAMPED_MARGIN, CONST_MARGIN, PROP_MARGIN
from tests.integration.test_binding_transfer import HARDCODED_OFFSET, NAIVE, PROBING, cands

OUT = "apps/web/public/data"
MIN_RUN_STAMP = "20261010T132248"
DOM = DomainManifest()
CANVAS = {"w": 800, "h": 600}
CANDIDATES = [  # (label, rule) -- labels are descriptions of scripted fixture rules
    ("Fixed 12 px inset", CONST_MARGIN),
    ("Inset is 8% of the card width", PROP_MARGIN()),
    ("8% of the card width, but never below 8 px or above 24 px", CLAMPED_MARGIN()),
]
LATENT = CLAMPED_MARGIN()


scene = card_scene


def canvas_view(label, boxes, note=""):
    return {"label": label, "canvas": CANVAS, "boxes": boxes, "note": note}


class Env:
    def __init__(self, url, token, backend, private=None):
        self.h, self.backend, self.private, self.sessions = (
            EvaluatorHarness(url, token),
            backend,
            private,
            [],
        )

    def factory(self, sc):
        s, initial = self.h.open_session(
            backend_scene(sc), "ui-bundle", self.private, backend=self.backend
        )
        self.sessions.append((s, initial))
        return s

    def run_and_judge(self, program, concept, sc):
        s = self.factory(sc)
        initial = self.sessions[-1][1]
        targets = targets_from_rule(concept.rule, sc)
        res = native_run(program, targets, s, CANVAS, NativeBudget(60))
        rep = self.h.judge_expected(s, initial, expected_state(LATENT, sc), ["card"])
        observed = observed_boxes(s, targets)
        s.close()  # the engine allows only a few concurrent sessions
        return {
            "native_passed": bool(res["passed"]),
            "native_diffs": res.get("diffs", []),
            "observed": observed,
            "expected": boxes_of_targets(targets, sc),
            "verifier_passed": bool(rep.passed),
            "verifier_checks": [
                {"name": c.name, "passed": bool(c.passed), "detail": c.detail[:200]}
                for c in rep.checks
            ],
        }

    def close(self):
        for s, _ in self.sessions:
            try:
                s.close()
            except Exception:
                pass


def concept_from_teaching(chosen_label, answer):
    led = TeachingLedger()
    led.append(
        "demonstration",
        {"scene_w": 150, "note": "badge placed in the top-right corner of the card"},
        "benchmark_teacher",
    )
    led.append("query", {"candidate_set": candidate_set_hash([r for _, r in CANDIDATES])}, "agent")
    led.append("answer", {"option": answer, "meaning": chosen_label}, "benchmark_teacher")
    c = Concept.create(
        "badge", 1, "badge inset", LATENT, DOM.hash, led, IntentState.RESOLVED_WITHIN_CANDIDATE_SET
    )
    return c, led


def axes(intent, symbolic, native, held):
    return {"intent": intent, "symbolic": symbolic, "native": native, "held_out": held}


async def story(url, token):
    steps = []
    orig = Env(url, token, "konva")
    fab = Env(url, token, "fabric")
    fab_drift = Env(url, token, "fabric", {"move_origin": "center"})
    try:
        # ------------------------------------------------------------------ 1. learn
        demo = scene(150)
        rules = [r for _, r in CANDIDATES]
        demo_after = boxes_of_targets(targets_from_rule(LATENT, demo), demo)
        steps.append(
            {
                "id": "demonstrate",
                "mode": "Learn",
                "title": "You demonstrate: badge in the card's top-right corner",
                "summary": "One demonstration at card width 150. Three different rules produce exactly this result, so the demonstration alone cannot decide.",
                "canvases": [
                    canvas_view("Before", boxes_of_scene(demo)),
                    canvas_view("Your demonstration", demo_after),
                ],
                "axes": axes(
                    "Not yet resolved", "Not yet checked", "Not yet tested", "Not yet tested"
                ),
            }
        )
        # ------------------------------------------------------------------ 2. question
        qscene = scene(400)
        sc = score_scene(rules, qscene, "sampled", F(1, 2))
        q = build_query(rules, sc)
        pv = public_view(q)
        letters = sorted(q.options)
        option_views = []
        for L in letters:
            tg = [
                {
                    "kind": "clone_place",
                    "symbol": "badge",
                    "proto": "proto",
                    **{k: fl(v) for k, v in q.options[L]["badge"].items()},
                }
            ]
            members = q.option_members[L]
            option_views.append(
                {
                    "id": L,
                    "boxes": boxes_of_targets(tg, qscene),
                    "stands_for": [CANDIDATES[i][0] for i in members],
                }
            )
        steps.append(
            {
                "id": "question",
                "mode": "Learn",
                "title": "It asks one question, on the input where its candidates disagree most",
                "summary": "Each picture is what one rule would do at card width 400. Pick the one you meant, or say Neither.",
                "query": {
                    "query_id": pv["query_id"],
                    "candidate_set_hash": pv["candidate_set_hash"],
                    "source": q.source,
                    "groups": [[CANDIDATES[i][0] for i in g] for g in sc.groups],
                    "entropy": sc.entropy,
                },
                "options": option_views,
                "extra_options": ["Neither / correct this example"],
                "base": canvas_view("Question input (card width 400)", boxes_of_scene(qscene)),
                "axes": axes(
                    "Ambiguous: 3 candidates",
                    "Disagreement found and re-executed concretely",
                    "Not yet tested",
                    "Not yet tested",
                ),
            }
        )
        # pick the option that matches the latent (scripted benchmark teacher)
        want = expected_state(LATENT, qscene)["badge"]
        ans = next(
            L for L in letters if all(q.options[L]["badge"][k] == want[k] for k in ("x", "y"))
        )
        concept, ledger_ = concept_from_teaching(CANDIDATES[q.option_members[ans][0]][0], ans)
        sealed = concept.sealed_hash()
        steps.append(
            {
                "id": "learned",
                "mode": "Learn",
                "title": f"Answer {ans}: the rule is sealed",
                "summary": "The rule is fixed and hashed together with the domain and the teaching record. Every later native binding must carry this exact hash.",
                "rule_text": CANDIDATES[q.option_members[ans][0]][0],
                "sealed_hash": sealed,
                "ledger_entries": len(ledger_.entries),
                "ledger_chain_verified": bool(ledger_.verify_chain()),
                "note": "answer source: scripted benchmark teacher, not a user study",
                "axes": axes(
                    "Resolved within the candidate set",
                    "Disagreement removed",
                    "Not yet tested",
                    "Not yet tested",
                ),
            }
        )
        # ------------------------------------------------------------------ 3. reuse on Konva
        s300 = scene(300)
        r_konva = orig.run_and_judge(NAIVE, concept, s300)
        steps.append(
            {
                "id": "reuse",
                "mode": "Reuse",
                "title": "Reuse on a new card (Konva)",
                "summary": "The frozen rule is applied to a card of width 300 through a Konva binding. The independent verifier recomputes the result from raw engine state.",
                "canvases": [
                    canvas_view("Expected (rule)", r_konva["expected"]),
                    canvas_view("Konva result", r_konva["observed"]),
                ],
                "checks": r_konva["verifier_checks"],
                "verifier_passed": r_konva["verifier_passed"],
                "axes": axes(
                    "Resolved",
                    "Not applicable here",
                    "Checked on listed case",
                    "Not yet tested on unseen sizes",
                ),
            }
        )
        # ------------------------------------------------------------------ 4. transfer to Fabric
        reg = BindingRegistry()
        ledger = lambda: Ledger(Limits(tokens=500_000, calls=64, actions=800))
        t1 = await transfer_concept(
            concept,
            "fabric",
            MockProvider({"binding": [cands(NAIVE)]}),
            ledger(),
            NativeBudget(),
            fab.factory,
            [scene(150), scene(60)],
            reg,
            "fabric-schema",
            origin="fixture",
        )
        v1 = reg.current("badge", "fabric")
        r_fab = fab.run_and_judge(v1.prog, concept, s300)
        steps.append(
            {
                "id": "transfer",
                "mode": "Transfer",
                "title": "Transfer to a second backend (Fabric)",
                "summary": "The rule did not change. Only the native procedure was written for Fabric, then checked against Fabric's own geometry on two listed cases.",
                "canvases": [
                    canvas_view("Expected (rule)", r_fab["expected"]),
                    canvas_view("Fabric result", r_fab["observed"]),
                ],
                "binding": {
                    "version": v1.version,
                    "backend": "fabric",
                    "program_hash": v1.program_hash,
                    "concept_hash": v1.concept_sealed_hash,
                    "origin": v1.origin,
                    "scope": v1.validation["scope"],
                    "native_actions": t1.native_actions,
                },
                "program": v1.prog,
                "checks": r_fab["verifier_checks"],
                "verifier_passed": r_fab["verifier_passed"],
                "same_concept_hash": v1.concept_sealed_hash == sealed,
                "axes": axes(
                    "Unchanged",
                    "Not applicable here",
                    "Checked on listed cases only",
                    "Not yet tested",
                ),
            }
        )
        # ------------------------------------------------------------------ 5. drift => mismatch
        t2 = await transfer_concept(
            concept,
            "fabric",
            MockProvider({"binding": [cands(NAIVE), cands(NAIVE)]}),
            ledger(),
            NativeBudget(),
            fab_drift.factory,
            [scene(300), scene(80)],
            BindingRegistry(),
            "fabric-schema",
            origin="fixture",
        )
        r_bad = fab_drift.run_and_judge(v1.prog, concept, s300)
        steps.append(
            {
                "id": "mismatch",
                "mode": "Challenge",
                "title": "The tool changes underneath, with no announcement",
                "summary": "Fabric now positions objects from their centre. The documentation and tool schema are unchanged, so the abstract model still says the program is fine, but the real result is off.",
                "canvases": [
                    canvas_view("Expected (rule)", r_bad["expected"]),
                    canvas_view("Fabric after the change", r_bad["observed"]),
                ],
                "mismatch": {
                    "status": t2.status,
                    "native_status": t2.native_status.value,
                    "abstract_check_passed": bool((t2.mismatch or {}).get("abstract_check_passed")),
                    "semantic_model_trusted": t2.semantic_model_trusted,
                    "diffs": (t2.mismatch or {}).get("native_diffs", []),
                },
                "checks": r_bad["verifier_checks"],
                "verifier_passed": r_bad["verifier_passed"],
                "axes": axes(
                    "Unchanged (the rule is not blamed)",
                    "Abstract model agrees (and is now untrusted)",
                    "Reproduced mismatch",
                    "Not applicable",
                ),
            }
        )
        # ------------------------------------------------------------------ 6. repair
        witness = {
            "scene": scene(300),
            "targets": t2.mismatch["expected_targets"],
            "observed": [
                {"key": x["key"], "observed": x["observed"]} for x in t2.mismatch["native_diffs"]
            ],
        }
        r3 = await repair_binding(
            concept,
            "fabric",
            v1,
            witness,
            MockProvider({"binding_repair": [cands(HARDCODED_OFFSET, PROBING)]}),
            ledger(),
            NativeBudget(),
            fab_drift.factory,
            fab.factory,
            [scene(150)],
            scene(80),
            reg,
            "fabric-schema",
            origin="fixture",
        )
        v2 = reg.current("badge", "fabric")
        unseen = scene(220, y=150)
        fixed_drift = fab_drift.run_and_judge(v2.prog, concept, unseen)
        fixed_orig = fab.run_and_judge(v2.prog, concept, unseen)
        steps.append(
            {
                "id": "repair",
                "mode": "Challenge",
                "title": "Only the native procedure is repaired",
                "summary": "Two patches were proposed. The first hard-codes an offset: it fixes the failing case but breaks an earlier one, so it is rejected. The second measures and corrects, passes every retained case, and is promoted as version 2.",
                "attempts": [
                    {
                        "candidate": a["candidate"],
                        "diagnosis": a.get("diagnosis", ""),
                        "failed_stage": a.get("failed_stage"),
                        "cases": a.get("cases", []),
                    }
                    for a in r3.attempts
                ],
                "old_program": v1.prog,
                "new_program": v2.prog,
                "versions": [
                    {
                        "version": b.version,
                        "parent": b.parent_version,
                        "program_hash": b.program_hash,
                        "active": b.version == v2.version,
                    }
                    for b in reg.versions[("badge", "fabric")]
                ],
                "concept_hash_before": sealed,
                "concept_hash_after": concept.sealed_hash(),
                "binding_concept_hash": v2.concept_sealed_hash,
                "rule_unchanged": concept.sealed_hash() == sealed
                and v2.concept_sealed_hash == sealed,
                "canvases": [
                    canvas_view("Expected (rule), unseen card width 220", fixed_drift["expected"]),
                    canvas_view("Repaired binding, changed tool", fixed_drift["observed"]),
                    canvas_view("Repaired binding, original tool", fixed_orig["observed"]),
                ],
                "checks": fixed_drift["verifier_checks"],
                "verifier_passed": fixed_drift["verifier_passed"] and fixed_orig["verifier_passed"],
                "axes": axes(
                    "Unchanged: same sealed hash",
                    "Not applicable here",
                    "Checked on listed cases in both environments",
                    "Unseen card checked once; no held-out study here",
                ),
            }
        )
        return steps, {"sealed_hash": sealed}
    finally:
        for e in (orig, fab, fab_drift):
            e.close()


# --------------------------------------------------------------------------------------------- stored live evidence
def load_rows(path):
    fields = {f.name for f in dataclasses.fields(Row)}
    return [
        Row(**{k: v for k, v in json.loads(line).items() if k in fields})
        for line in open(path)
        if line.strip()
    ]


def stored_evidence():
    runs = []
    for d in sorted(glob.glob("results/runs/*")):
        p = os.path.join(d, "rows.jsonl")
        finished = os.path.exists(
            os.path.join(d, "report.json")
        )  # a run still in flight has no report yet
        post_fixes = (
            os.path.basename(d).rsplit("-", 1)[-1] >= MIN_RUN_STAMP
        )  # earlier runs predate decisions #34-#37
        if (
            not os.path.exists(p)
            or not finished
            or not post_fixes
            or os.path.exists(os.path.join(d, "README_INVALID_FULL_ROWS.txt"))
        ):
            continue
        rows = load_rows(p)
        methods = sorted({r.method for r in rows})
        if not rows:
            continue
        per = {}
        for m in methods:
            ts = [r for r in rows if r.method == m and r.stage != "learning"]
            per[m] = {
                "scheduled": len(ts),
                "correct": sum(1 for r in ts if r.correct),
                "committed_wrong": sum(1 for r in ts if r.committed and r.correct is False),
                "abstained": sum(1 for r in ts if r.abstained),
                "tokens": sum(r.tokens for r in rows if r.method == m),
                "failures": {},
            }
            for r in ts:
                if r.failure:
                    per[m]["failures"][r.failure.split(":")[0]] = (
                        per[m]["failures"].get(r.failure.split(":")[0], 0) + 1
                    )
        runs.append(
            {
                "run": os.path.basename(d),
                "label": "LIVE model rows + non-model reference (development split, not the locked study)",
                "episodes": len({r.episode for r in rows}),
                "methods": per,
                "origins": sorted({r.origin for r in rows}),
            }
        )
    trials = []
    for d in sorted(glob.glob("results/pilot_v10_ultra_low_bigcap_*")):
        fs = glob.glob(os.path.join(d, "learn-*.json"))
        if not fs:
            continue
        ds = [json.load(open(f)) for f in fs]
        trials.append(
            {
                "concept": ds[0]["concept"],
                "model": ds[0]["model"],
                "reasoning_effort": ds[0]["reasoning_effort"],
                "trials": len(ds),
                "recovered": sum(1 for x in ds if x.get("recovered_latent_on_heldout")),
                "ready_but_wrong": sum(
                    1
                    for x in ds
                    if x.get("final_state") == "INTENT_READY"
                    and x.get("recovered_latent_on_heldout") is False
                ),
                "unresolved": sum(1 for x in ds if x.get("final_state") == "UNRESOLVED"),
            }
        )
    from scripts.analyze_audit_experiment import summarise

    experiments = []
    for arm, label in (
        ("control", "Model alone (control)"),
        ("on", "Model + audit round"),
        ("hybrid", "Model + symbolic search (hybrid)"),
    ):
        d = "results/exp_hybrid" if arm == "hybrid" else f"results/exp_audit_{arm}"
        if glob.glob(f"{d}/learn-*.json"):
            m = summarise(d)
            experiments.append(
                {
                    "name": "audit",
                    "variant": {"control": "control", "on": "audit", "hybrid": "hybrid"}[arm],
                    "arm": label,
                    **{k: v for k, v in m.items() if k != "by_concept"},
                }
            )
    return {
        "experiments": experiments,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runs": runs,
        "teaching_trials": trials,
        "caveats": [
            "The teaching trials and the model runs used the candidate-generation prompt as it was before the wording change in decision #39 (live results after that change have not been collected yet).",
            "Runs from before the live binding fixes (decisions #34-#37) and runs still in progress are excluded.",
            "Development-split pilot runs; not the locked study and not evidence for the spec's quality gates.",
            "Dollar cost is not shown: it depends on rates entered locally and is not verified against billing.",
        ],
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    with local_engine(".") as (url, token):
        steps, extra = asyncio.run(story(url, token))
    demo = {
        "label": "RECORDED",
        "origin": "offline deterministic story on the real Konva and Fabric engines and the independent verifier; "
        "no language model is used: candidate rules and binding programs are scripted fixtures; the teacher is scripted",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "steps": steps,
        **extra,
    }
    json.dump(demo, open(f"{OUT}/demo.json", "w"), indent=1, default=str)
    json.dump(stored_evidence(), open(f"{OUT}/evidence.json", "w"), indent=1, default=str)
    print("wrote", f"{OUT}/demo.json", f"({len(steps)} steps)", "and", f"{OUT}/evidence.json")


if __name__ == "__main__":
    main()
