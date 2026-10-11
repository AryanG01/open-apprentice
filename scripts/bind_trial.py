"""Diagnostic: live binding generation for a KNOWN concept (the evaluator's latent rule is used as the concept so that
teaching is not what is being tested). Prints every attempt: diagnosis, validity, abstract check, native result.
Usage: PYTHONPATH=src python scripts/bind_trial.py --episode 1 --concept badge --backend fabric [--drift]"""

import argparse
import asyncio
import json

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.bindings import BindingRegistry, NativeBudget, backend_scene
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.query_selection import sample_scenes
from open_apprentice.concepts.schemas import Concept, IntentState, TeachingLedger
from open_apprentice.concepts.transfer import transfer_concept
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
    scenes = sample_scenes(dom, [n], 2, 11)
    with local_engine(".") as (url, token):
        h = EvaluatorHarness(url, token)
        priv = ep.drift if a.drift else None
        sessions = []

        def factory(sc):
            s, init = h.open_session(backend_scene(sc), "bind-trial", priv, backend=a.backend)
            sessions.append(s)
            return s

        reg = BindingRegistry()
        r = await transfer_concept(
            concept,
            a.backend,
            prov,
            Ledger(Limits(tokens=200_000, calls=20)),
            NativeBudget(a.budget),
            factory,
            scenes,
            reg,
            a.backend,
        )
        for s in sessions:
            try:
                s.close()
            except Exception:
                pass
    print(
        "STATUS:",
        r.status,
        "| native_actions:",
        r.native_actions,
        "| native_status:",
        r.native_status.value,
        "| model_calls:",
        r.model_calls,
    )
    for t in r.attempts:
        print(
            "\n-- attempt",
            json.dumps({k: v for k, v in t.items() if k != "program_excerpt"}, default=str)[:900],
        )
    await prov.aclose()


ap = argparse.ArgumentParser()
ap.add_argument("--episode", type=int, default=1)
ap.add_argument("--concept", default="badge")
ap.add_argument("--backend", default="fabric")
ap.add_argument("--drift", action="store_true")
ap.add_argument("--budget", type=int, default=24)
asyncio.run(main(ap.parse_args()))
