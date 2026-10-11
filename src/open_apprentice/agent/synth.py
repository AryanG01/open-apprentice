"""Shared program-synthesis core for the three baselines (spec 21.11): fresh full-context, text memory,
structured procedure. They differ ONLY in what is persisted between tasks; the loop, tools, prompt, public
checker, budgets and correction allowance are identical.

The public checker sees only what any policy can see (geometry via a public tool + the task statement). It checks
constraints stated in the task - it cannot check whether positions express the taught intent. That is the
point of the benchmark: intent must be inferred from the evidence.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Optional

from open_apprentice.agent.policies import BADGE, BOTH, SPACING, Policy, PolicyContext, TaskResult
from open_apprentice.budget import BudgetExhausted
from open_apprentice.concepts.hypotheses import describe
from open_apprentice.environments.client import EngineSession, EngineToolError
from open_apprentice.environments.docs import DOCS
from open_apprentice.environments.tasks import PUBLIC_TOOLS
from open_apprentice.providers.base import CallContext, Message, ProviderError, StrictModel
from open_apprentice.skills.interpreter import ProgramError, run_program

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "synth_program.md"
EPS = 0.5


class Proposal(StrictModel):
    diagnosis: str = ""
    program: list[dict[str, Any]]


def public_check(view: dict, before: dict, after: dict) -> dict:
    """Task-stated constraints only. before/after: id -> (left, top, width, height) from observe_geometry."""
    sel = set(view["selected_ids"])
    kind = view["kind"]
    cw, ch = float(view["canvas"]["w"]), float(view["canvas"]["h"])
    failed = []
    moved_ok = set(sel) if kind in (SPACING, BOTH) else set()
    for k, v in before.items():
        a = after.get(k)
        if a is None:
            failed.append(f"{k} disappeared")
            continue
        same = all(abs(x - y) <= EPS for x, y in zip(v, a))
        if k in sel and kind != BADGE:
            if abs(v[2] - a[2]) > EPS or abs(v[3] - a[3]) > EPS:
                failed.append(f"{k} changed size")
        elif not same and k not in moved_ok:
            failed.append(f"{k} changed but was not part of the task")
    new = sorted(set(after) - set(before))
    if kind in (BADGE, BOTH):
        want = sorted(f"badge_{c}" for c in view["selected_ids"])
        if new != want:
            failed.append(f"expected new objects {want}, found {new}")
    elif new:
        failed.append(f"unexpected new objects {new}")
    for k in sel | set(new):
        a = after.get(k)
        if a and (a[0] < -EPS or a[1] < -EPS or a[0] + a[2] > cw + EPS or a[1] + a[3] > ch + EPS):
            failed.append(f"{k} is off the canvas")
    return {"passed": not failed, "failed": failed[:6]}


def _bounds(session: EngineSession) -> dict[str, tuple]:
    ids = [n["id"] for n in session.call("inspect_scene")["nodes"]]
    return {
        b["id"]: (b["left"], b["top"], b["width"], b["height"])
        for b in session.call("observe_geometry", node_ids=ids)["bounds"]
    }


@dataclass
class SynthResult:
    ok: bool
    program: Optional[list] = None
    cycles: int = 0
    model_calls: int = 0
    feedback: list[dict] = field(default_factory=list)
    failure: Optional[str] = None


async def synthesize_and_run(
    ctx: PolicyContext,
    view: dict,
    session: EngineSession,
    evidence: dict,
    summaries: Optional[dict],
    seed_program: Optional[list] = None,
    max_cycles: int = 3,
) -> SynthResult:
    out = SynthResult(False)
    inputs = {
        "selected_ids": view["selected_ids"],
        "prototype_id": view["prototype_id"],
        "canvas": {k: float(v) for k, v in view["canvas"].items()},
    }
    tools = session.tools(PUBLIC_TOOLS)
    before = _bounds(session)
    msgs = [
        Message("system", PROMPT.read_text()),
        Message(
            "user",
            json.dumps(
                {
                    "evidence": evidence,
                    "summaries": summaries,
                    "task": view,
                    "backend_documentation": DOCS[view["backend"]],
                }
            ),
        ),
    ]
    prog = seed_program
    for cycle in range(1, max_cycles + 1):
        out.cycles = cycle
        if prog is None:
            try:
                comp = await ctx.provider.complete_json(
                    messages=msgs,
                    output_schema=Proposal,
                    ctx=CallContext(role="synth", category="execution"),
                    ledger=ctx.ledger,
                    max_tokens=3000,
                )
            except BudgetExhausted as e:
                out.failure = f"budget_exhausted:{e.dimension}"
                return out
            except ProviderError as e:
                out.failure = e.code.lower()
                return out
            out.model_calls += 1 + comp.schema_corrections
            prog = comp.parsed.program
            msgs = msgs + [Message("assistant", comp.parsed.model_dump_json())]
        try:
            run_program(prog, inputs, tools)
            after = _bounds(session)
            chk = public_check(view, before, after)
        except (ProgramError, EngineToolError) as e:
            chk = {"passed": False, "failed": [f"execution error: {str(e)[:160]}"]}
        out.feedback.append({"cycle": cycle, **chk})
        out.program = prog
        if chk["passed"]:
            out.ok = True
            return out
        msgs = msgs + [
            Message(
                "user",
                json.dumps(
                    {
                        "operational_feedback": chk,
                        "note": "The scene reflects your last attempt; correct it.",
                    }
                ),
            )
        ]
        prog = None
    out.failure = "public_check_failed"
    return out


class SynthPolicy(Policy):
    """Common learning phase for the three baselines: the SAME teaching session (model-proposed candidates, same
    questions, same ledger checks) as full_v1_2. They keep different things afterwards."""

    uses_summaries = False
    persists_programs = False

    def __init__(self) -> None:
        self.evidence: dict[str, list[dict]] = {}
        self.summaries: dict[str, list[str]] = {}
        self.state: dict[str, str] = {}
        self.programs: dict[tuple[str, str], list] = {}
        self.cases: dict[tuple[str, str], list[dict]] = (
            {}
        )  # earlier successes (views) for replay gating
        self.model_calls = 0
        self.gate_log: list[dict] = []

    async def learn(self, ctx: PolicyContext, handle: str, demo: dict) -> None:
        from open_apprentice.agent.policies import drive_teaching
        from open_apprentice.concepts.teaching import TeachingSession

        n = len(demo["scene"]["objects"])
        counts = [3, 4, 5] if n >= 3 else [n]
        sess = TeachingSession(
            ctx.provider,
            ctx.ledger,
            ctx.dom,
            counts,
            pool=ctx.pool,
            teacher_source="benchmark_teacher",
        )
        await sess.start(demo)
        await drive_teaching(sess, ctx.teacher)
        ctx.solver_seconds += sess.solver_budget.elapsed_s
        self.evidence[handle] = describe(sess.constraints)
        self.summaries[handle] = [c.summary for c in sess.candidates]
        self.state[handle] = sess.state.value

    async def solve(self, ctx: PolicyContext, view: dict) -> TaskResult:
        kind, backend = view["kind"], view["backend"]
        need = [SPACING, BADGE] if kind == BOTH else [kind]
        if any(h not in self.evidence for h in need):
            return TaskResult("abstained", failure="no_evidence")
        ev = {h: self.evidence[h] for h in need}
        sm = {h: self.summaries[h] for h in need} if self.uses_summaries else None
        from open_apprentice.agent.policies import view_scene

        sess = ctx.env.open(backend, view_scene(view))
        seed = self.programs.get((kind, backend)) if self.persists_programs else None
        a0 = sess.actions_used
        try:
            r = await synthesize_and_run(ctx, view, sess, ev, sm, seed_program=seed)
        finally:
            ctx.native_actions += sess.actions_used - a0
        self.model_calls += r.model_calls
        if r.ok:
            if self.persists_programs:
                await self._store_if_gated(ctx, kind, backend, view, r.program, seed)
            return TaskResult("committed", sess, True, notes={"cycles": r.cycles})
        return TaskResult(
            "failed" if r.failure and r.failure.startswith(("budget", "provider")) else "abstained",
            sess,
            False,
            failure=r.failure,
            notes={"feedback": r.feedback[-1:] if r.feedback else []},
        )

    async def _store_if_gated(
        self,
        ctx: PolicyContext,
        kind: str,
        backend: str,
        view: dict,
        program: list,
        seed: Optional[list],
    ) -> None:
        """Replay gate (spec 11.3): a CHANGED program must also satisfy the public check on up to two stored earlier
        cases, replayed under the environment they were recorded in. Otherwise the old program stays.
        """
        key = (kind, backend)
        if seed is not None and program == seed:
            self.cases.setdefault(key, []).append(view)
            return
        ok = True
        for old in self.cases.get(key, [])[:2]:
            from open_apprentice.agent.policies import view_scene

            sess = ctx.env.replay(backend, view_scene(old))
            a0 = sess.actions_used
            try:
                before = _bounds(sess)
                run_program(
                    program,
                    {
                        "selected_ids": old["selected_ids"],
                        "prototype_id": old["prototype_id"],
                        "canvas": {k: float(v) for k, v in old["canvas"].items()},
                    },
                    sess.tools(PUBLIC_TOOLS),
                )
                ok = ok and public_check(old, before, _bounds(sess))["passed"]
            except (ProgramError, EngineToolError):
                ok = False
            finally:
                ctx.native_actions += sess.actions_used - a0
                sess.close()
        self.gate_log.append(
            {
                "kind": kind,
                "backend": backend,
                "stored": ok,
                "replayed": min(2, len(self.cases.get(key, []))),
            }
        )
        if ok:
            self.programs[key] = program
            self.cases.setdefault(key, []).append(view)


class FreshFullContextPolicy(SynthPolicy):
    name = "fresh_full_context"  # raw evidence only; nothing persisted


class TextMemoryPolicy(SynthPolicy):
    name = "text_memory"  # plain-language summaries + the same evidence; execution regenerated per task
    uses_summaries = True


class StructuredProcedurePolicy(SynthPolicy):
    """Persists a verified native procedure per (task kind, backend) with a public postcondition check; reuses it
    without calling the model; on postcondition failure the model repairs locally (replay-gated by re-running the
    check). No portable concept layer, no sealed rule: the rule lives inside the program."""

    name = "structured_procedure"
    uses_summaries = True
    persists_programs = True
