"""Native bindings: executable programs that realise a concept's TARGETS through a backend's tools.

Intent vs execution are kept apart (spec 7.4, 8.7):
  concept (sealed)  --rule-->  targets (desired world geometry)  --binding program-->  native tool calls
A tool failure can only ever change a BINDING version. Promotion verifies the sealed concept hash is
byte-identical, so a repair cannot edit the rule, the domain, or the teaching evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable, Optional

from open_apprentice.budget import BudgetExhausted
from open_apprentice.concepts.rules import FIELDS, evaluate_rule
from open_apprentice.concepts.schemas import Concept, sha
from open_apprentice.environments.client import EngineSession, EngineToolError
from open_apprentice.skills.interpreter import ProgramError, run_program

BINDING_TOOLS = (
    "inspect_scene",
    "inspect_node",
    "observe_geometry",
    "measure_node",
    "move_node",
    "resize_node",
    "clone_node",
)
NATIVE_TOL = 0.5  # px; same as the frozen verifier tolerance
EXTRA_NATIVE_ACTIONS = 48  # spec 8.7 says 24; raised for every method (decisions #35), still inside the 800-action episode cap


class PromotionError(Exception):
    pass


# --------------------------------------------------------------------------- scenes & targets
def _f(v: Any) -> float:
    return float(v)


def backend_scene(scene: dict) -> dict:
    """Canonical rational scene -> engine scene data (flat rects)."""
    return {
        "canvas": {"width": _f(scene["canvas"]["w"]), "height": _f(scene["canvas"]["h"])},
        "nodes": [
            {
                "id": o["id"],
                "type": "rect",
                "x": _f(o["x"]),
                "y": _f(o["y"]),
                "width": _f(o["w"]),
                "height": _f(o["h"]),
                "fill": "#888",
            }
            for o in scene["objects"]
        ],
    }


def targets_from_rule(rule: list, scene: dict) -> list[dict]:
    """Desired WORLD top-left geometry the binding must realise. Pure; derived from the sealed rule."""
    out = evaluate_rule(rule, scene["objects"], scene["canvas"])
    ids = {o["id"]: o for o in scene["objects"]}
    protos = _clone_protos(rule, scene)
    targets: list[dict] = []
    for key, st in out.items():
        if key in ids:
            o = ids[key]
            if any(st[f] != Fraction(o[f]) for f in ("x", "y")):
                targets.append(
                    {
                        "kind": "move_existing",
                        "id": key,
                        "x": _f(st["x"]),
                        "y": _f(st["y"]),
                        "w": _f(st["w"]),
                        "h": _f(st["h"]),
                    }
                )
            if any(st[f] != Fraction(o[f]) for f in ("w", "h")):
                targets.append(
                    {
                        "kind": "resize_existing",
                        "id": key,
                        "x": _f(st["x"]),
                        "y": _f(st["y"]),
                        "w": _f(st["w"]),
                        "h": _f(st["h"]),
                    }
                )
        else:
            targets.append(
                {
                    "kind": "clone_place",
                    "symbol": key,
                    "proto": protos[key],
                    "x": _f(st["x"]),
                    "y": _f(st["y"]),
                    "w": _f(st["w"]),
                    "h": _f(st["h"]),
                }
            )
    return targets


def _clone_protos(rule: list, scene: dict) -> dict[str, str]:
    """Which existing object each clone symbol is a copy of (needed to call clone_node). Evaluated by
    re-running the rule with a recording evaluator so symbol->proto is exact, not guessed."""
    from open_apprentice.concepts import rules as R

    class Rec(R._Run):
        def __init__(self, *a):
            super().__init__(*a)
            self.protos: dict[str, str] = {}

        def emit(self, s):
            if s["kind"] == "clone_place":
                self.protos[s["symbol"]] = self.ev(s["proto"]).id
            super().emit(s)

    run = Rec([R.to_obj(o) for o in scene["objects"]], scene["canvas"])
    run.block(rule)
    return run.protos


def expected_state(rule: list, scene: dict) -> dict:
    """Expected world geometry per key as plain floats (for the verifier)."""
    return {
        k: {f: _f(v[f]) for f in FIELDS}
        for k, v in evaluate_rule(rule, scene["objects"], scene["canvas"]).items()
    }


# --------------------------------------------------------------------------- budgets & tools
@dataclass
class NativeBudget:
    allowance: int = EXTRA_NATIVE_ACTIONS
    used: int = 0

    def spend(self, n: int = 1) -> None:
        if self.used + n > self.allowance:
            raise BudgetExhausted("native_actions", f"{self.used}+{n}>{self.allowance}")
        self.used += n


def metered_tools(
    session: EngineSession, budget: NativeBudget, names=BINDING_TOOLS
) -> dict[str, Callable]:
    def make(n):
        def call(**kw):
            budget.spend(1)
            return session.call(n, **kw)

        return call

    return {n: make(n) for n in names}


class AbstractToolbox:
    """The learner's ABSTRACT action model: the documented contract, simulated purely in Python.
    Positions are world top-left; groups do not exist. It is a hypothesis about the tools - a pass here
    never overrides an observed native failure (spec 12.5)."""

    def __init__(self, scene: dict) -> None:
        self.n = {
            o["id"]: {"x": _f(o["x"]), "y": _f(o["y"]), "w": _f(o["w"]), "h": _f(o["h"])}
            for o in scene["objects"]
        }

    def tools(self) -> dict[str, Callable]:
        def meas(node_id):
            s = self.n[node_id]
            return {
                "id": node_id,
                "x": s["x"],
                "y": s["y"],
                "width": s["w"],
                "height": s["h"],
                "frame": "world",
            }

        def move(node_id, x, y):
            self.n[node_id].update(x=x, y=y)
            return {}

        def resize(node_id, width, height):
            self.n[node_id].update(w=width, h=height)
            return {}

        def clone(node_id, new_id):
            self.n[new_id] = dict(self.n[node_id])
            return {}

        def obs(node_ids):
            return {
                "bounds": [
                    {
                        "id": i,
                        "left": self.n[i]["x"],
                        "top": self.n[i]["y"],
                        "width": self.n[i]["w"],
                        "height": self.n[i]["h"],
                    }
                    for i in node_ids
                ]
            }

        def scene_():
            return {"nodes": [{"id": i, **s} for i, s in self.n.items()]}

        return {
            "measure_node": meas,
            "move_node": move,
            "resize_node": resize,
            "clone_node": clone,
            "observe_geometry": obs,
            "inspect_node": lambda node_id: meas(node_id),
            "inspect_scene": scene_,
        }


def keys_of(targets: list[dict]) -> list[str]:
    return [t.get("id") or t["symbol"] for t in targets]


def compare(targets: list[dict], bounds: list[dict], tol: float = NATIVE_TOL) -> dict:
    b = {x["id"]: x for x in bounds}
    diffs = []
    for t in targets:
        k = t.get("id") or t["symbol"]
        if k not in b:
            diffs.append({"key": k, "problem": "missing"})
            continue
        got = (b[k]["left"], b[k]["top"], b[k]["width"], b[k]["height"])
        want = (t["x"], t["y"], t["w"], t["h"])
        if any(abs(g - w) > tol for g, w in zip(got, want)):
            diffs.append({"key": k, "expected": want, "observed": got})
    return {"passed": not diffs, "diffs": diffs}


def abstract_check(program: list, targets: list[dict], scene: dict, canvas: dict) -> dict:
    tb = AbstractToolbox(scene)
    try:
        run_program(program, {"targets": targets, "canvas": canvas}, tb.tools())
        return compare(targets, tb.tools()["observe_geometry"](node_ids=keys_of(targets))["bounds"])
    except (ProgramError, KeyError, TypeError) as e:
        return {"passed": False, "diffs": [], "error": f"{type(e).__name__}: {str(e)[:150]}"}


def native_run(
    program: list, targets: list[dict], session: EngineSession, canvas: dict, budget: NativeBudget
) -> dict:
    """Execute on the REAL backend, then compare observed geometry with the targets."""
    used0 = budget.used
    tools = metered_tools(session, budget)
    try:
        run_program(program, {"targets": targets, "canvas": canvas}, tools)
        budget.spend(1)
        bounds = session.call("observe_geometry", node_ids=keys_of(targets))["bounds"]
        res = compare(targets, bounds)
    except (ProgramError, EngineToolError) as e:
        res = {"passed": False, "diffs": [], "error": str(e)[:200]}
    except BudgetExhausted as e:
        res = {"passed": False, "diffs": [], "error": str(e), "budget_exhausted": True}
    res["native_actions"] = budget.used - used0
    return res


# --------------------------------------------------------------------------- binding objects
@dataclass(frozen=True)
class Binding:
    concept_id: str
    concept_sealed_hash: str
    backend: str
    version: int
    parent_version: Optional[int]
    program_json: str  # canonical JSON string => immutable copy of the program
    program_hash: str
    public_schema_hash: str
    validation: dict
    origin: str = "model"  # model | fixture (fixtures never count as learned, spec 8.2)

    @staticmethod
    def create(
        concept: Concept,
        backend: str,
        version: int,
        parent: Optional[int],
        program: list,
        schema_hash: str,
        validation: dict,
        origin: str = "model",
    ) -> "Binding":
        from open_apprentice.concepts.schemas import canonical

        return Binding(
            concept.concept_id,
            concept.sealed_hash(),
            backend,
            version,
            parent,
            canonical(program),
            sha(program),
            schema_hash,
            validation,
            origin,
        )

    @property
    def prog(self) -> list:
        import json

        return json.loads(self.program_json)


@dataclass
class BindingRegistry:
    """Immutable versions + an active pointer per (concept, backend). History is never erased."""

    versions: dict[tuple, list[Binding]] = field(default_factory=dict)
    active: dict[tuple, int] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    def promote(self, b: Binding, concept: Concept, reason: str) -> None:
        key = (b.concept_id, b.backend)
        if b.concept_sealed_hash != concept.sealed_hash():
            self.events.append(
                {
                    "event": "promotion_rejected",
                    "why": "sealed concept hash changed",
                    "version": b.version,
                }
            )
            raise PromotionError(
                "binding was built against a different concept (rule/domain/teaching ledger changed)"
            )
        v = b.validation
        if not (v.get("passed") and v.get("regression_passed", True)):
            self.events.append(
                {
                    "event": "promotion_rejected",
                    "why": "validation or regression failed",
                    "version": b.version,
                }
            )
            raise PromotionError("validation or regression replay did not pass")
        if self.active.get(key) != b.parent_version:
            self.events.append(
                {
                    "event": "promotion_deferred",
                    "why": "parent changed since search began",
                    "version": b.version,
                }
            )
            self.versions.setdefault(key, []).append(b)  # retained, unpromoted, needs revalidation
            raise PromotionError(
                "active version changed since the search began; candidate retained unpromoted"
            )
        self.versions.setdefault(key, []).append(b)
        self.active[key] = b.version
        self.events.append(
            {
                "event": "promoted",
                "version": b.version,
                "parent": b.parent_version,
                "reason": reason,
            }
        )

    def rollback(self, concept_id: str, backend: str, to_version: int, reason: str) -> None:
        key = (concept_id, backend)
        if not any(x.version == to_version for x in self.versions.get(key, [])):
            raise PromotionError("no such version")
        self.events.append(
            {"event": "rollback", "from": self.active.get(key), "to": to_version, "reason": reason}
        )
        self.active[key] = to_version  # pointer move only; nothing is erased

    def current(self, concept_id: str, backend: str) -> Optional[Binding]:
        key = (concept_id, backend)
        return next(
            (x for x in self.versions.get(key, []) if x.version == self.active.get(key)), None
        )

    def next_version(self, concept_id: str, backend: str) -> int:
        return len(self.versions.get((concept_id, backend), [])) + 1
