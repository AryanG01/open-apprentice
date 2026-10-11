"""Policy interface + the non-LLM enumerative REFERENCE policy (spec 21.11).

Every policy sees exactly the same things: an agent-visible task view, an EnvPort (current environment +
opaque replay), a TeacherPort wrapped by a counter, one shared budget ledger, and the same solver pool.
Policies differ only in what they PERSIST and how they EXECUTE. The runner judges the session a policy
returns with the private evaluator after commitment; a policy never sees that verdict.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Optional

from open_apprentice.agent.binding_templates import template_source
from open_apprentice.agent.ports import EnvPort, TeacherPort
from open_apprentice.budget import BudgetExhausted, Ledger
from open_apprentice.concepts.bindings import (
    BindingRegistry,
    NativeBudget,
    native_run,
    targets_from_rule,
)
from open_apprentice.concepts.composition import CompositionPlan, PlanNode, run_composition
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.enumerative import EnumerativeSource
from open_apprentice.concepts.query_selection import sample_scenes
from open_apprentice.concepts.schemas import Concept
from open_apprentice.concepts.teaching import State, TeachingSession
from open_apprentice.concepts.transfer import repair_binding, transfer_concept
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.environments.client import EngineSession
from open_apprentice.providers.base import Provider

SPACING, BADGE, BOTH = "concept_1", "concept_2", "concept_1_then_concept_2"
FIXED_PLAN = CompositionPlan(
    nodes=[
        PlanNode(id="arrange", concept=SPACING),
        PlanNode(id="badges", concept=BADGE, mode="each", depends_on=["arrange"]),
    ]
)


class CountingTeacher:
    """Counts every teacher interaction a method uses (same cap and same accounting for all methods)."""

    def __init__(self, inner: TeacherPort) -> None:
        self._inner, self.answers, self.corrections = inner, 0, 0

    def answer(self, view: dict) -> str:
        self.answers += 1
        return self._inner.answer(view)

    def corrected_example(self, scene: dict) -> dict:
        self.corrections += 1
        return self._inner.corrected_example(scene)

    @property
    def interactions(self) -> int:
        return self.answers + self.corrections


@dataclass
class PolicyContext:
    env: EnvPort
    teacher: CountingTeacher
    ledger: Ledger
    dom: DomainManifest
    pool: SolverPool
    provider: Optional[Provider] = None
    exec_actions_per_task: int = 150
    seed: int = 0
    solver_seconds: float = 0.0
    native_actions: int = 0


@dataclass
class TaskResult:
    status: str  # committed | abstained | failed
    session: Optional[EngineSession] = None
    claimed_success: bool = False
    failure: Optional[str] = None
    notes: dict = field(default_factory=dict)


class Policy(ABC):
    name = "policy"
    uses_model = True  # False => the runner hands it NO provider and reports $0 model cost

    @abstractmethod
    async def learn(self, ctx: PolicyContext, handle: str, demo: dict) -> None: ...

    @abstractmethod
    async def solve(self, ctx: PolicyContext, view: dict) -> TaskResult: ...


# ----------------------------------------------------------------------------- shared helpers
def view_scene(view: dict) -> dict:
    objs = [
        {k: (Fraction(v) if k in ("x", "y", "w", "h") else v) for k, v in o.items()}
        for o in view["scene_objects"]
    ]
    return {"objects": objs, "canvas": {k: Fraction(v) for k, v in view["canvas"].items()}}


def task_targets(concepts: dict[str, Concept], view: dict, which: str) -> list[dict]:
    """Targets for a single-concept task on THIS scene. Spacing sees the selected row; badge runs once per card."""
    scene = view_scene(view)
    by = {o["id"]: o for o in scene["objects"]}
    sel = view["selected_ids"]
    if which == SPACING:
        return targets_from_rule(
            concepts[SPACING].rule, {"objects": [by[i] for i in sel], "canvas": scene["canvas"]}
        )
    out: list[dict] = []
    for card in sel:
        for t in targets_from_rule(
            concepts[BADGE].rule,
            {"objects": [by[card], by[view["prototype_id"]]], "canvas": scene["canvas"]},
        ):
            if "symbol" in t:
                t["symbol"] = f"{t['symbol']}_{card}"
            out.append(t)
    return out


async def drive_teaching(sess: TeachingSession, teacher: CountingTeacher) -> None:
    guard = 0
    while sess.state == State.AWAITING_USER and guard < 8:
        guard += 1
        if sess.pending_kind == "question":
            v = sess.public_question()
            await sess.answer(v["query_id"], teacher.answer(v), v["candidate_set_hash"])
        else:
            await sess.submit_correction(teacher.corrected_example(sess.pending_scene))


# ----------------------------------------------------------------------------- the reference
class ReferencePolicy(Policy):
    """No model anywhere: enumerative rule learning + a declared 2-template binding library + the same
    transfer/repair/composition machinery. Reports its own coverage; it is a reference, not a contender.
    """

    name = "enumerative_reference"
    origin = "reference"
    uses_model = False

    # ---- hooks (the full v1.2 policy overrides these to use the model; everything else is shared)
    def candidate_source(self, ctx: PolicyContext, counts: list[int]):
        return EnumerativeSource(ctx.dom, counts)

    binding_source = staticmethod(template_source)
    uses_provider = False
    grounded = True  # False only for the disposable-scene grounding ablation (spec 21.11)

    def __init__(self) -> None:
        self.concepts: dict[str, Concept] = {}
        self.unresolved: dict[str, str] = {}
        self.registry = BindingRegistry()
        self.calib: dict[tuple[str, str], list[dict]] = {}
        self.stats: list[dict] = []
        self.teach: dict[str, TeachingSession] = {}

    async def learn(self, ctx: PolicyContext, handle: str, demo: dict) -> None:
        n = len(demo["scene"]["objects"])
        counts = [3, 4, 5] if n >= 3 else [n]
        src = self.candidate_source(ctx, counts)
        sess = TeachingSession(
            ctx.provider if self.uses_provider else None,
            ctx.ledger,
            ctx.dom,
            counts,
            pool=ctx.pool,
            teacher_source="benchmark_teacher",
            candidate_source=src if not self.uses_provider else None,
        )
        await sess.start(demo)
        await drive_teaching(sess, ctx.teacher)
        ctx.solver_seconds += sess.solver_budget.elapsed_s
        self.stats.append(
            {
                "handle": handle,
                "state": sess.state.value,
                "intent": sess.intent_state.value,
                "reports": [r.usage for r in sess.reports],
            }
        )
        self.teach[handle] = sess
        if sess.state == State.INTENT_READY:
            self.concepts[handle] = sess.finalize(handle)
        else:
            self.unresolved[handle] = sess.unresolved_reason

    # -- bindings
    def _calibration(self, ctx: PolicyContext, handle: str, n: int, salt: int) -> list[dict]:
        return sample_scenes(ctx.dom, [n], 2, ctx.seed + salt)

    async def _ensure(self, ctx: PolicyContext, handle: str, backend: str) -> Optional[Any]:
        cur = self.registry.current(handle, backend)
        if cur is not None:
            return cur
        n = 3 if handle == SPACING else 2
        scenes = self._calibration(ctx, handle, n, 11)
        r = await transfer_concept(
            self.concepts[handle],
            backend,
            ctx.provider if self.uses_provider else None,
            ctx.ledger,
            NativeBudget(),
            lambda sc: ctx.env.open(backend, sc),
            scenes,
            self.registry,
            backend,
            origin=self.origin,
            source=None if self.uses_provider else self.binding_source,
            ground=self.grounded,
        )
        ctx.native_actions += r.native_actions
        if r.status == "validated":
            self.calib[(handle, backend)] = scenes
            return r.binding
        return None

    async def _repair(self, ctx: PolicyContext, handle: str, backend: str) -> bool:
        """Reproduce a failure on a calibration-shaped scene in the CURRENT environment, then repair the binding only."""
        old = self.registry.current(handle, backend)
        n = 3 if handle == SPACING else 2
        wit_scene = self._calibration(ctx, handle, n, 23)[0]
        c = self.concepts[handle]
        sess = ctx.env.open(backend, wit_scene)
        tgt = targets_from_rule(c.rule, wit_scene)
        probe = native_run(
            old.prog,
            tgt,
            sess,
            {"w": float(wit_scene["canvas"]["w"]), "h": float(wit_scene["canvas"]["h"])},
            NativeBudget(),
        )
        sess.close()
        ctx.native_actions += probe["native_actions"]
        if probe["passed"]:
            return False  # not reproducible on a fresh scene: do not "repair" what cannot be shown broken
        witness = {"scene": wit_scene, "targets": tgt, "observed": probe["diffs"]}
        fresh = self._calibration(ctx, handle, n, 37)[0]
        r = await repair_binding(
            c,
            backend,
            old,
            witness,
            ctx.provider if self.uses_provider else None,
            ctx.ledger,
            NativeBudget(),
            lambda sc: ctx.env.open(backend, sc),
            lambda sc: ctx.env.replay(backend, sc),
            self.calib.get((handle, backend), []),
            fresh,
            self.registry,
            backend,
            origin=self.origin,
            source=None if self.uses_provider else self.binding_source,
        )
        ctx.native_actions += r.native_actions
        self.stats.append(
            {
                "repair": handle,
                "backend": backend,
                "status": r.status,
                "native_actions": r.native_actions,
                "attempt_stages": [
                    [c["stage"] for c in a.get("cases", [])] + [a.get("failed_stage")]
                    for a in r.attempts
                ],
            }
        )
        return r.status == "validated"

    # -- tasks
    async def solve(self, ctx: PolicyContext, view: dict) -> TaskResult:
        kind = view["kind"]
        need = [SPACING, BADGE] if kind == BOTH else [kind]
        if any(h not in self.concepts for h in need):
            return TaskResult("abstained", failure="unresolved_teaching")
        try:
            if kind == BOTH:
                return await self._composition(ctx, view)
            return await self._single(ctx, view, kind)
        except BudgetExhausted as e:
            return TaskResult("failed", failure=f"budget_exhausted:{e.dimension}")

    async def _single(self, ctx: PolicyContext, view: dict, handle: str) -> TaskResult:
        backend, scene = view["backend"], view_scene(view)
        canvas = {k: float(v) for k, v in scene["canvas"].items()}
        for attempt in (1, 2):
            b = await self._ensure(ctx, handle, backend)
            if b is None:
                return TaskResult("abstained", failure="binding_unavailable")
            targets = task_targets(self.concepts, view, handle)
            sess = ctx.env.open(backend, scene)
            res = native_run(b.prog, targets, sess, canvas, NativeBudget(ctx.exec_actions_per_task))
            ctx.native_actions += res["native_actions"]
            if res["passed"] or (
                not self.grounded and "error" not in res
            ):  # ablation ignores the native comparison
                return TaskResult(
                    "committed",
                    sess,
                    True,
                    notes={"attempt": attempt, "binding_version": b.version},
                )
            sess.close()
            if attempt == 2 or not await self._repair(ctx, handle, backend):
                return TaskResult(
                    "abstained",
                    failure="native_check_failed_unrepaired",
                    notes={"diffs": res["diffs"][:2]},
                )
        return TaskResult("abstained", failure="unreachable")

    async def _composition(self, ctx: PolicyContext, view: dict) -> TaskResult:
        backend, scene = view["backend"], view_scene(view)
        canvas = {k: float(v) for k, v in scene["canvas"].items()}
        for attempt in (1, 2):
            for h in (SPACING, BADGE):
                if await self._ensure(ctx, h, backend) is None:
                    return TaskResult("abstained", failure="binding_unavailable")
            sess = ctx.env.open(backend, scene)
            run = run_composition(
                FIXED_PLAN,
                self.concepts,
                self.registry,
                backend,
                sess,
                view["selected_ids"],
                view["prototype_id"],
                canvas,
                NativeBudget(ctx.exec_actions_per_task * 3),
            )
            ctx.native_actions += run.native_actions
            bad = [n["concept"] for n in run.nodes if not n["local_native_check_passed"]]
            if run.status == "completed" and (not bad or not self.grounded):
                return TaskResult(
                    "committed",
                    sess,
                    True,
                    notes={"attempt": attempt, "nodes": [n["node"] for n in run.nodes]},
                )
            sess.close()
            if run.status in ("rejected_scope", "error", "budget_exhausted") or attempt == 2:
                return TaskResult(
                    "abstained", failure=f"composition_{run.status}", notes={"detail": run.detail}
                )
            repaired = [await self._repair(ctx, h, backend) for h in bad]
            if not all(repaired):
                return TaskResult("abstained", failure="composition_repair_failed")
        return TaskResult("abstained", failure="unreachable")


class FullV12Policy(ReferencePolicy):
    """full_v1_2: model proposes candidate rules and binding programs; everything else (questions, ledger checks,
    sealed concept, checked bindings, replay-gated repair, fixed composition) is the same code the reference uses.
    """

    name = "full_v1_2"
    origin = "model"
    uses_provider = True
    uses_model = True


class ReferenceUngrounded(ReferencePolicy):
    """ABLATION (disposable scenes only): the reference with native confirmation removed. Not deployment behaviour."""

    name = "enumerative_reference_ungrounded"
    grounded = False


class FullV12Ungrounded(FullV12Policy):
    name = "full_v1_2_ungrounded"
    grounded = False
