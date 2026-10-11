"""Diagnostic: LIVE binding transfer on the original backend, then the evaluator switches on the private tool change and we see
whether the binding still passes or the model must repair it. The concept is the evaluator's latent rule (teaching is not under test).
Usage: PYTHONPATH=src python scripts/repair_trial.py --episode 2 --concept badge"""

import argparse
import asyncio
import json

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.bindings import (
    BindingRegistry,
    NativeBudget,
    backend_scene,
    native_run,
    targets_from_rule,
)
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.query_selection import sample_scenes
from open_apprentice.concepts.schemas import Concept, IntentState, TeachingLedger
from open_apprentice.concepts.transfer import repair_binding, transfer_concept
from open_apprentice.config import load_settings
from open_apprentice.evaluation.episodes import make_manifest
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.evaluation.local_engine import local_engine
from open_apprentice.providers.factory import make_provider


async def main(a):
    st = load_settings()
    prov = make_provider(st)
    dom = DomainManifest()
    ep = make_manifest("development", 0, 12).episodes[a.episode]
    assert ep.drift, "pick a drift episode"
    backend = ep.target_backend
    rule = ep.badge if a.concept == "badge" else ep.spacing
    led = TeachingLedger()
    led.append("demonstration", {"fixture": True}, "benchmark_teacher")
    concept = Concept.create(
        a.concept,
        1,
        "fixture concept",
        rule,
        dom.hash,
        led,
        IntentState.RESOLVED_WITHIN_CANDIDATE_SET,
    )
    n = 2 if a.concept == "badge" else 3
    scenes = sample_scenes(dom, [n], 4, 11)
    ledger = Ledger(Limits(tokens=400_000, calls=40))
    reg = BindingRegistry()
    with local_engine(".") as (url, token):
        h = EvaluatorHarness(url, token)
        opened = []

        def mk(priv):
            def f(sc):
                s, _ = h.open_session(backend_scene(sc), "repair-trial", priv, backend=backend)
                opened.append(s)
                return s

            return f

        orig, drift = mk(None), mk(ep.drift)
        r1 = await transfer_concept(
            concept, backend, prov, ledger, NativeBudget(48), orig, scenes[:2], reg, backend
        )
        print(
            f"[1] transfer on ORIGINAL {backend}: {r1.status} ({r1.native_actions} native actions, {r1.model_calls} model calls)"
        )
        if r1.status != "validated":
            print("   attempts:", json.dumps(r1.attempts, default=str)[:900])
            return
        b = reg.current(a.concept, backend)
        wit = scenes[2]
        tgt = targets_from_rule(concept.rule, wit)
        s = drift(wit)
        res = native_run(
            b.prog,
            tgt,
            s,
            {"w": float(wit["canvas"]["w"]), "h": float(wit["canvas"]["h"])},
            NativeBudget(48),
        )
        print(
            f"[2] SAME binding after the private tool change: passed={res['passed']} diffs={json.dumps(res['diffs'][:2])[:300]} error={str(res.get('error'))[:300]}"
        )
        if res["passed"]:
            print(
                "   -> binding is robust to the change (e.g. it calibrates from observe_geometry); no repair needed."
            )
            return
        witness = {"scene": wit, "targets": tgt, "observed": res["diffs"]}
        r3 = await repair_binding(
            concept,
            backend,
            b,
            witness,
            prov,
            ledger,
            NativeBudget(48),
            drift,
            orig,
            scenes[:2],
            scenes[3],
            reg,
            backend,
        )
        print(
            f"[3] repair: {r3.status} ({r3.native_actions} actions, {r3.model_calls} model calls); active version now v{reg.active.get((a.concept, backend))}"
        )
        print("   sealed concept hash unchanged:", concept.sealed_hash() == b.concept_sealed_hash)
        for t in r3.attempts:
            print(
                "   attempt:",
                json.dumps({k: v for k, v in t.items() if k != "program_excerpt"}, default=str)[
                    :1200
                ],
            )
        for s_ in opened:
            try:
                s_.close()
            except Exception:
                pass
    await prov.aclose()


ap = argparse.ArgumentParser()
ap.add_argument("--episode", type=int, default=2)
ap.add_argument("--concept", default="badge")
asyncio.run(main(ap.parse_args()))
