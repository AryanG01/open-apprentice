"""Episode runner (evaluator side). Owns the private latents, the drift schedule, sealing and scoring.

Per episode: teach both concepts (teacher answers only queries) -> eight scored tasks. After a policy returns,
the session it names is SEALED and judged by the independent verifier against the PRIVATE latent rules; the
verdict never flows back to the policy. Learning costs are logged as their own row so they cannot be hidden.
"""

from __future__ import annotations

import time
from typing import Optional

from open_apprentice.agent.policies import (
    BADGE,
    SPACING,
    CountingTeacher,
    Policy,
    PolicyContext,
    TaskResult,
)
from open_apprentice.budget import BudgetExhausted, Ledger, Limits
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.env_service import EnvService
from open_apprentice.evaluation.episodes import Episode, Task, agent_visible
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.evaluation.metrics import Row
from open_apprentice.evaluation.teacher import BenchmarkTeacher
from open_apprentice.providers.base import Provider, ProviderError

EPISODE_LIMITS = Limits(
    tokens=300_000, calls=120, actions=800
)  # raised from spec 19.2's 80k/64 for the larger model (decisions #33); identical for every method


def expected_for(ep: Episode, task: Task) -> dict:
    """Private ground truth for a task, from the latent rules (never exposed to a policy)."""
    by = {o["id"]: o for o in task.scene["objects"]}
    cards = [by[i] for i in task.selected]
    canvas = task.scene["canvas"]
    exp: dict = {}
    arranged = {c["id"]: c for c in cards}
    if task.kind in ("spacing", "composition"):
        out = evaluate_rule(ep.spacing, cards, canvas)
        arranged = {k: {"id": k, **v} for k, v in out.items()}
        exp.update({k: {f: float(v[f]) for f in "xywh"} for k, v in out.items()})
    if task.kind in ("badge", "composition"):
        for c in task.selected:
            out = evaluate_rule(ep.badge, [arranged[c], by[task.proto]], canvas)["badge"]
            exp[f"badge_{c}"] = {f: float(out[f]) for f in "xywh"}
    return exp


def _costs(
    ctx: PolicyContext, led: Ledger, solver0: float, native0: int, teach0: int, snap0: dict
) -> dict:
    snap = led.snapshot()
    return dict(
        tokens=snap["consumed"]["tokens"] - snap0["consumed"]["tokens"],
        calls=snap["consumed"]["calls"] - snap0["consumed"]["calls"],
        actions=ctx.native_actions - native0,
        solver_s=ctx.solver_seconds - solver0,
        teacher_interactions=ctx.teacher.interactions - teach0,
    )


async def run_episode(
    ep: Episode,
    policy: Policy,
    harness: EvaluatorHarness,
    dom: DomainManifest,
    pool: SolverPool,
    provider: Optional[Provider] = None,
    rep: int = 0,
    origin: str = "reference",
    seed: int = 0,
) -> list[Row]:
    env = EnvService(harness, ep, owner=f"{policy.name}-{ep.episode_id}-{rep}")
    ledger = Ledger(EPISODE_LIMITS)
    teacher = CountingTeacher(BenchmarkTeacher(ep.spacing))
    provider = (
        provider if policy.uses_model else None
    )  # a non-model method is given no provider at all
    ctx = PolicyContext(
        env=env, teacher=teacher, ledger=ledger, dom=dom, pool=pool, provider=provider, seed=seed
    )
    rows: list[Row] = []
    base = dict(episode=ep.episode_id, rep=rep, method=policy.name, origin=origin)
    try:
        # ---- learning (charged, never scored)
        t0, snap0 = time.perf_counter(), ledger.snapshot()
        learn_failure = None
        for handle, latent, demo in (
            (SPACING, ep.spacing, ep.demos["spacing"]),
            (BADGE, ep.badge, ep.demos["badge"]),
        ):
            teacher._inner = BenchmarkTeacher(latent)
            try:
                await policy.learn(ctx, handle, demo)
            except BudgetExhausted:
                learn_failure = learn_failure or "budget_exhausted"
            except (
                ProviderError
            ) as e:  # keep the spend and the reason; the concept simply isn't learned
                learn_failure = learn_failure or f"provider_error:{e.code}"
        rows.append(
            Row(
                task_id="learning",
                stage="learning",
                committed=False,
                claimed_success=False,
                correct=None,
                failure=learn_failure,
                wall_s=time.perf_counter() - t0,
                usd=(0.0 if provider is None else None),
                **_costs(ctx, ledger, 0.0, 0, 0, snap0),
                **base,
            )
        )

        # ---- scored tasks
        for task in ep.tasks:
            env.begin_stage(task.stage)
            view = agent_visible(task)
            t0, snap0, solver0, native0, teach0 = (
                time.perf_counter(),
                ledger.snapshot(),
                ctx.solver_seconds,
                ctx.native_actions,
                teacher.interactions,
            )
            try:
                res: TaskResult = await policy.solve(ctx, view)
            except BudgetExhausted as e:
                res = TaskResult("failed", failure=f"budget_exhausted:{e.dimension}")
            except ProviderError as e:
                res = TaskResult("failed", failure=f"provider_error:{e.code}")
            try:
                ledger.charge_actions("execution", ctx.native_actions - native0)
            except BudgetExhausted:
                res = TaskResult("failed", failure="budget_exhausted:actions")
            committed = res.status == "committed" and res.session is not None
            correct: Optional[bool] = None
            verdict = None
            if committed:  # SEAL, then score (verdict never returned to the policy)
                rep_ = harness.judge_expected(
                    res.session,
                    env.initial_of(res.session),
                    expected_for(ep, task),
                    list(task.selected),
                )
                correct = rep_.passed
                verdict = (
                    None
                    if correct
                    else [[c.name, c.detail[:300]] for c in rep_.checks if not c.passed]
                )
            if (
                res.session is not None
            ):  # free the browser context as soon as it is sealed and scored
                res.session.close()
            rows.append(
                Row(
                    task_id=task.task_id,
                    stage=task.stage,
                    committed=committed,
                    claimed_success=bool(res.claimed_success and committed),
                    correct=correct,
                    verdict=verdict,
                    abstained=(res.status == "abstained"),
                    failure=res.failure,
                    wall_s=time.perf_counter() - t0,
                    usd=(0.0 if provider is None else None),
                    **_costs(ctx, ledger, solver0, native0, teach0, snap0),
                    **base,
                )
            )
    finally:
        env.close_all()
    return rows
