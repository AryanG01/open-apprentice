"""Teaching-only live trial (the first 72-hour-pilot question): does the model propose useful candidate rules,
and does a revealed disagreement lead to a rule that matches the PRIVATE latent on held-out scenes?

No engine needed. Evaluator-side tool: it knows the latent, the CLI user is the evaluator. The model never does.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from open_apprentice.agent.policies import CountingTeacher, drive_teaching
from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.hybrid import HybridSource
from open_apprentice.concepts.schemas import sha
from open_apprentice.concepts.teaching import State, TeachingSession
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.batteries import heldout_equal
from open_apprentice.evaluation.episodes import make_manifest
from open_apprentice.evaluation.teacher import BenchmarkTeacher
from open_apprentice.providers.base import Provider


async def run_learn_trial(
    provider: Provider,
    split: str,
    episode: int,
    concept: str,
    *,
    max_tokens_total: int,
    max_calls: int,
    reasoning_effort: str | None,
    completion_cap: int = 6000,
    audit: bool = False,
    hybrid: bool = False,
) -> dict:
    ep = make_manifest(split, 0, 12).episodes[episode]
    latent, demo, counts = (
        (ep.badge, ep.demos["badge"], [2])
        if concept == "badge"
        else (ep.spacing, ep.demos["spacing"], [3, 4, 5])
    )
    dom = DomainManifest()
    ledger = Ledger(Limits(tokens=max_tokens_total, calls=max_calls))
    teacher = CountingTeacher(BenchmarkTeacher(latent))
    t0 = time.perf_counter()
    with SolverPool() as pool:
        sess = TeachingSession(
            provider,
            ledger,
            dom,
            counts,
            pool=pool,
            teacher_source="benchmark_teacher",
            completion_cap=completion_cap,
            audit=audit,
        )
        source = None
        if (
            hybrid
        ):  # model proposals UNIONED with the bounded symbolic search; the teaching loop is unchanged
            source = HybridSource(provider, ledger, dom, counts, completion_cap=completion_cap)
            sess.candidate_source = source
        err = None
        try:
            await sess.start(demo)
            await drive_teaching(sess, teacher)
        except (
            Exception
        ) as e:  # report provider/format failures as outcomes, never as silent passes
            err = f"{type(e).__name__}: {str(e)[:200]}"
    snap = ledger.snapshot()
    recovered = None
    if sess.state == State.INTENT_READY:
        recovered = heldout_equal(sess.finalize().rule, latent, dom, counts)
    return {
        "label": "LIVE" if provider.label == "LIVE" else provider.label,
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": provider.requested_model,
        "completion_cap": completion_cap,
        "reasoning_effort": reasoning_effort or "provider default",
        "split": split,
        "episode": episode,
        "concept": concept,
        "audit": audit,
        "hybrid": hybrid,
        "hybrid_model_errors": list(source.model_errors) if source else None,
        "final_rule_origin": (
            source.origins.get(sess.candidates[0].hash)
            if source and sess.state == State.INTENT_READY and sess.candidates
            else None
        ),
        "evaluator_template": ep.templates[concept],
        "template_note": "evaluator-only; never sent to the model",
        "error": err,
        "final_state": sess.state.value,
        "intent_state": sess.intent_state.value,
        "unresolved_reason": sess.unresolved_reason,
        "rounds": sess.rounds,
        "queries": sess.queries_asked,
        "teacher_interactions": {"answers": teacher.answers, "corrections": teacher.corrections},
        "generation": [
            {
                "round": r.round,
                "accepted": [c.summary for c in r.accepted],
                "rejected": r.rejected,
                "usage": r.usage,
                "model_calls": r.model_calls,
            }
            for r in sess.reports
        ],
        "recovered_latent_on_heldout": recovered,
        "tokens": snap["consumed"]["tokens"],
        "calls": snap["consumed"]["calls"],
        "unknown_cost_calls": snap["unknown_cost_calls"],
        "wall_s": round(time.perf_counter() - t0, 2),
        "prompt_hashes": {"hypotheses": sha(open("prompts/hypotheses.md").read())[:16]},
    }


# ----------------------------------------------------------------------------- multi-method episode runs
def policy_registry() -> dict:
    from open_apprentice.agent.policies import (
        FullV12Policy,
        FullV12Ungrounded,
        ReferencePolicy,
        ReferenceUngrounded,
    )
    from open_apprentice.agent.synth import (
        FreshFullContextPolicy,
        StructuredProcedurePolicy,
        TextMemoryPolicy,
    )

    return {
        c.name: c
        for c in (
            ReferencePolicy,
            FullV12Policy,
            FreshFullContextPolicy,
            TextMemoryPolicy,
            StructuredProcedurePolicy,
            ReferenceUngrounded,
            FullV12Ungrounded,
        )
    }


async def run_compare(
    split: str,
    first: int,
    count: int,
    methods: list[str],
    provider,
    engine_url: str,
    token: str,
    *,
    rows_path: str,
    rep: int = 0,
    global_token_ceiling: int | None = None,
) -> dict:
    """Runs every (episode, method) sequentially through the SAME runner; rows are appended as they finish so a crash
    never loses completed work. A run that raises is recorded as an infrastructure failure, never silently dropped.
    """
    import json

    from open_apprentice.evaluation.harness import EvaluatorHarness
    from open_apprentice.evaluation.metrics import row_dicts
    from open_apprentice.evaluation.runner import run_episode

    reg = policy_registry()
    dom = DomainManifest()
    eps = make_manifest(split, 0, 12).episodes[first : first + count]
    harness = EvaluatorHarness(engine_url, token)
    rows, errors = [], []
    spent = 0
    with SolverPool() as pool:
        for ep in eps:
            for m in methods:
                if global_token_ceiling is not None and spent >= global_token_ceiling:
                    errors.append(
                        {
                            "episode": ep.episode_id,
                            "method": m,
                            "error": f"NOT RUN: global token ceiling {global_token_ceiling} reached",
                        }
                    )
                    continue
                pol = reg[m]()
                try:
                    r = await run_episode(
                        ep,
                        pol,
                        harness,
                        dom,
                        pool,
                        provider=provider,
                        rep=rep,
                        origin="live" if pol.uses_model else "reference",
                    )
                except Exception as e:  # infra failure: keep it visible
                    errors.append(
                        {
                            "episode": ep.episode_id,
                            "method": m,
                            "error": f"{type(e).__name__}: {str(e)[:200]}",
                        }
                    )
                    continue
                rows.extend(r)
                spent += sum(x.tokens for x in r)
                with open(rows_path, "a") as f:
                    for d in row_dicts(r):
                        f.write(json.dumps(d, default=str) + "\n")
    return {"rows": rows, "errors": errors, "episodes": [e.episode_id for e in eps]}
