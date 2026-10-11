"""Bounded two-concept composition (spec 8.8). One fixed shipped workflow, not a general planner.

A plan is a small DAG (<=4 nodes, no recursion). The host runs nodes in topological order through the
existing restricted interpreter against ONE shared native budget (children cannot reset it). After each
node it compares expected vs actual affected-object sets: touching objects outside a node's declared
scope rejects the composition (never silently dropped). Per-node native success does NOT establish the
final task: interference between correct parts is exactly what the independent final check is for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from open_apprentice.budget import BudgetExhausted
from open_apprentice.concepts.bindings import (
    BindingRegistry,
    NativeBudget,
    keys_of,
    metered_tools,
    targets_from_rule,
    compare,
)
from open_apprentice.concepts.schemas import Concept
from open_apprentice.environments.client import EngineSession, EngineToolError
from open_apprentice.providers.base import StrictModel
from open_apprentice.skills.interpreter import ProgramError, run_program

MAX_NODES = 4
EPS = 0.25


class PlanError(Exception):
    pass


class ScopeViolation(Exception):
    pass


class PlanNode(StrictModel):
    id: str
    concept: str
    mode: str = (
        "selection"  # "selection": concept sees all selected objects | "each": once per selected card + proto
    )
    depends_on: list[str] = []


class CompositionPlan(StrictModel):
    nodes: list[PlanNode]


def validate_plan(plan: CompositionPlan, concepts: dict[str, Concept]) -> list[str]:
    """Returns topological order or raises PlanError. Rejects cycles, recursion, unresolved refs, big plans."""
    ids = [n.id for n in plan.nodes]
    if not 1 <= len(ids) <= MAX_NODES:
        raise PlanError(f"plan must have 1..{MAX_NODES} nodes")
    if len(set(ids)) != len(ids):
        raise PlanError("duplicate node ids")
    byid = {n.id: n for n in plan.nodes}
    for n in plan.nodes:
        if n.concept not in concepts:
            raise PlanError(f"unresolved concept {n.concept!r}")
        if n.mode not in ("selection", "each"):
            raise PlanError(f"unknown mode {n.mode!r}")
        for d in n.depends_on:
            if d == n.id:
                raise PlanError("a node cannot depend on itself (recursion)")
            if d not in byid:
                raise PlanError(f"unresolved dependency {d!r}")
    order, state = [], {}

    def visit(i: str) -> None:
        if state.get(i) == 2:
            return
        if state.get(i) == 1:
            raise PlanError("cycle detected")
        state[i] = 1
        for d in byid[i].depends_on:
            visit(d)
        state[i] = 2
        order.append(i)

    for i in ids:
        visit(i)
    return order


@dataclass
class CompositionRun:
    status: str  # completed | rejected_scope | budget_exhausted | error
    order: list[str] = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)
    detail: str = ""
    native_actions: int = 0


def _snapshot(session: EngineSession, budget: NativeBudget) -> dict[str, tuple]:
    budget.spend(1)
    ids = [n["id"] for n in session.call("inspect_scene")["nodes"]]
    budget.spend(1)
    return {
        b["id"]: (b["left"], b["top"], b["width"], b["height"])
        for b in session.call("observe_geometry", node_ids=ids)["bounds"]
    }


def _changed(before: dict, after: dict) -> set[str]:
    out = {k for k in after if k not in before}
    out |= {
        k
        for k in before
        if k in after and any(abs(a - b) > EPS for a, b in zip(before[k], after[k]))
    }
    return out


def _scene_from(snap: dict, ids: list[str], canvas: dict) -> dict:
    return {
        "objects": [
            {"id": i, "x": snap[i][0], "y": snap[i][1], "w": snap[i][2], "h": snap[i][3]}
            for i in ids
        ],
        "canvas": canvas,
    }


def run_composition(
    plan: CompositionPlan,
    concepts: dict[str, Concept],
    registry: BindingRegistry,
    backend: str,
    session: EngineSession,
    selected: list[str],
    proto: str,
    canvas: dict,
    budget: NativeBudget,
) -> CompositionRun:
    run = CompositionRun("completed")
    try:
        run.order = validate_plan(plan, concepts)
    except PlanError as e:
        run.status, run.detail = "error", f"invalid plan: {e}"
        return run
    byid = {n.id: n for n in plan.nodes}
    try:
        for nid in run.order:
            node, concept = byid[nid], concepts[byid[nid].concept]
            binding = registry.current(concept.concept_id, backend)
            if binding is None:
                run.status, run.detail = (
                    "error",
                    f"no active {backend} binding for concept {concept.concept_id!r} (not dropped silently)",
                )
                return run
            before = _snapshot(session, budget)
            units = [selected] if node.mode == "selection" else [[card, proto] for card in selected]
            expected_affected: set[str] = set()
            ok_all = True
            for unit in units:
                scene = _scene_from(
                    before if unit is units[0] else _snapshot(session, budget), unit, canvas
                )
                targets = targets_from_rule(concept.rule, scene)
                if node.mode == "each":  # unique symbol per card
                    for t in targets:
                        if "symbol" in t:
                            t["symbol"] = f"{t['symbol']}_{unit[0]}"
                expected_affected |= set(keys_of(targets))
                tools = metered_tools(session, budget)
                try:
                    run_program(binding.prog, {"targets": targets, "canvas": canvas}, tools)
                    budget.spend(1)
                    res = compare(
                        targets,
                        session.call("observe_geometry", node_ids=keys_of(targets))["bounds"],
                    )
                except (ProgramError, EngineToolError) as e:
                    run.status, run.detail = "error", f"node {nid}: {str(e)[:160]}"
                    return run
                ok_all = ok_all and res["passed"]
            after = _snapshot(session, budget)
            affected = _changed(before, after)
            run.nodes.append(
                {
                    "node": nid,
                    "concept": concept.concept_id,
                    "local_native_check_passed": ok_all,
                    "affected": sorted(affected),
                    "declared_scope": sorted(expected_affected),
                }
            )
            extra = affected - expected_affected
            if extra:
                run.status = "rejected_scope"
                run.detail = (
                    f"node {nid} changed objects outside its declared scope: {sorted(extra)}"
                )
                return run
    except BudgetExhausted as e:
        run.status, run.detail = "budget_exhausted", str(e)
    run.native_actions = budget.used
    return run
