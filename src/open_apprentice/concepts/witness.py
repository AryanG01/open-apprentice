"""Bounded witness-search service (spec 8.9).

find_disagreement / find_public_constraint_violation return a typed WitnessSearchResult, never a bool.
Statuses are distinct on purpose:
  witness_found        a concrete, re-executed witness exists
  no_witness_in_model  every relevant (pair, object-count) case was conclusively UNSAT in the stated domain
  incomplete           budget ended before all cases ran (checked subset is listed)
  timeout              some case returned unknown (timeout / memory); unknown is NOT a pass
  unsupported          outside the symbolic subset
No status here is a proof of user intent or of native tool behaviour.

Solving runs in a separate, killable process (z3 memory_max_size set there). The main process only
compiles (to detect unsupported rules without spending a solver call) and re-executes witnesses
concretely through rules.evaluate_rule.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import time
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import combinations
from typing import Any, Optional

from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.rules import FIELDS, RuleError, evaluate_rule
from open_apprentice.concepts.symbolic import (
    PUBLIC_CONSTRAINTS,
    Unsupported,
    compile_rule,
    disagreement_formula,
    domain_constraints,
    make_inputs,
    violation_formula,
)


class GroundingError(Exception):
    """A solver model failed concrete re-execution. Means the compiler and interpreter diverge: a bug,
    never something to display to a user."""


@dataclass
class SolverBudget:
    max_calls: int = 12
    per_call_ms: int = 500
    total_s: float = 6.0
    memory_mb: int = 512
    calls: int = 0
    elapsed_s: float = 0.0

    def can_run(self) -> bool:
        return self.calls < self.max_calls and self.elapsed_s < self.total_s


@dataclass
class CaseResult:
    subject: str  # "pair 0-1" | "constraints preserve_sizes,..."
    n: int
    status: str  # sat | unsat | timeout | unsupported | unchecked | memory
    elapsed_ms: float = 0.0
    detail: str = ""
    smtlib: Optional[str] = None


@dataclass
class Witness:
    objects: list[dict]
    canvas: dict
    predictions: list[dict]  # per rule: concrete re-executed output
    simplified: str  # "exact" | "rounded_to_integers" | "rounded_to_halves"
    kind: str  # "disagreement" | "constraint_violation"
    note: str = "simple witness; not claimed globally minimal"


@dataclass
class WitnessSearchResult:
    status: str
    witness: Optional[Witness]
    cases: list[CaseResult]
    solver_version: str
    domain_hash: str
    candidate_hashes: list[str]
    encoded_property: str
    elapsed_ms: float
    budget: dict = field(default_factory=dict)


def rule_hash(body: list) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


# ----------------------------------------------------------------------------- worker process
def _solve(payload: dict) -> dict:
    import gc
    import z3
    import z3.z3 as _z3mod
    from open_apprentice.concepts.domain import DomainManifest as DM

    # Reproducibility: drop Z3's global context so a query's model never depends on what this long-lived
    # worker solved earlier (hash-consing / ID history otherwise changes the witness chosen).
    _z3mod._main_ctx = None
    gc.collect()
    z3.set_param("memory_max_size", payload["memory_mb"])
    z3.set_param("smt.random_seed", 0)
    z3.set_param("sat.random_seed", 0)
    dom = DM.from_canonical(payload["domain"])
    n = payload["n"]
    objs, cv, vars_ = make_inputs(n)
    sa = compile_rule(payload["rules"][0], objs, cv)
    if payload["mode"] == "disagree":
        sb = compile_rule(payload["rules"][1], objs, cv)
        goal = disagreement_formula(sa, sb, Fraction(payload["threshold"]))
    else:
        goal = violation_formula(sa, objs, cv, tuple(payload["constraints"]))
    s = z3.Solver()
    s.set("timeout", payload["timeout_ms"])
    s.add(*domain_constraints(objs, cv, dom))
    if payload.get("integers"):
        s.add(*[z3.IsInt(v) for v in vars_])
    s.add(goal)
    r = s.check()
    out: dict[str, Any] = {"version": z3.get_version_string()}
    if r == z3.sat:
        m = s.model()
        vals = {}
        for v in vars_:
            val = m.eval(v, model_completion=True)
            vals[str(v)] = f"{val.numerator_as_long()}/{val.denominator_as_long()}"
        out.update(status="sat", model=vals)
    elif r == z3.unsat:
        out.update(status="unsat", smtlib=s.to_smt2())
    else:
        why = s.reason_unknown()
        out.update(
            status="timeout" if ("timeout" in why or "canceled" in why) else "unknown", detail=why
        )
    return out


def _worker(conn) -> None:
    while True:
        try:
            payload = conn.recv()
        except EOFError:
            return
        try:
            conn.send(_solve(payload))
        except Exception as e:  # compile errors etc. are reported, never swallowed silently
            conn.send({"status": "error", "detail": f"{type(e).__name__}: {e}"[:300]})


class SolverPool:
    """One reusable spawned process; killed on wall-clock overrun and respawned lazily."""

    def __init__(self) -> None:
        self._ctx = mp.get_context("spawn")
        self._proc = None
        self._conn = None

    def _ensure(self) -> None:
        if self._proc is None or not self._proc.is_alive():
            self._conn, child = self._ctx.Pipe()
            self._proc = self._ctx.Process(target=_worker, args=(child,), daemon=True)
            self._proc.start()

    def solve(self, payload: dict, wall_s: float) -> Optional[dict]:
        self._ensure()
        self._conn.send(payload)
        if self._conn.poll(wall_s):
            try:
                return self._conn.recv()
            except EOFError:
                self.kill()
                return {"status": "memory", "detail": "solver process died (likely memory ceiling)"}
        self.kill()
        return None  # wall-clock overrun

    def kill(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.is_alive():
                    self._proc.kill()
                self._proc.join(timeout=5)
            except (AttributeError, ValueError, AssertionError):
                pass  # never started / already reaped: nothing left to kill
        self._proc = self._conn = None

    def close(self) -> None:
        self.kill()

    def __enter__(self) -> "SolverPool":
        return self

    def __exit__(self, *a) -> None:
        self.close()


# ----------------------------------------------------------------------------- witness handling
def _objects_from_model(model: dict, n: int) -> tuple[list[dict], dict]:
    g = lambda k: Fraction(model[k])
    objs = [{"id": f"obj{i}", **{f: g(f"{f}{i}") for f in FIELDS}} for i in range(n)]
    return objs, {"w": g("cw"), "h": g("ch")}


def _differs(a: dict, b: dict, thr: Fraction) -> bool:
    for key in set(a) | set(b):
        if (key in a) != (key in b):
            return True
        if any(abs(a[key][f] - b[key][f]) > thr for f in FIELDS):
            return True
    return False


def _violates(out: dict, objs: list[dict], canvas: dict, names: tuple[str, ...]) -> bool:
    for name in names:
        if name == "preserve_sizes" and any(
            out[o["id"]][f] != o[f] for o in objs for f in ("w", "h")
        ):
            return True
        if name == "stay_on_canvas" and any(
            out[o["id"]]["x"] < 0
            or out[o["id"]]["y"] < 0
            or out[o["id"]]["x"] + out[o["id"]]["w"] > canvas["w"]
            or out[o["id"]]["y"] + out[o["id"]]["h"] > canvas["h"]
            for o in objs
        ):
            return True
        if name == "preserve_order" and any(
            out[b["id"]]["x"] < out[a["id"]]["x"] for a, b in zip(objs, objs[1:])
        ):
            return True
    return False


def _simplify(objs, canvas, ok, dom):
    """Round for readability while the witness still holds. Labelled 'simple', not minimal."""
    for label, step in (
        ("rounded_to_integers", Fraction(1)),
        ("rounded_to_halves", Fraction(1, 2)),
    ):
        r = lambda v: (v / step).__round__() * step
        o2 = [{"id": o["id"], **{f: r(o[f]) for f in FIELDS}} for o in objs]
        c2 = {k: r(v) for k, v in canvas.items()}
        if dom.contains(o2, c2) and ok(o2, c2):
            return o2, c2, label
    return objs, canvas, "exact"


def _run(
    cases, make_payload, concrete_ok, predictions, kind, rules, prop, dom, budget, pool, threshold
) -> WitnessSearchResult:
    t0 = time.perf_counter()
    own_pool = pool is None
    pool = pool or SolverPool()
    results: list[CaseResult] = []
    witness = None
    version = ""
    try:
        for subject, n, probe in cases:
            if witness is not None:
                break
            try:
                probe()  # compile in-process only to detect unsupported rules; no solver call spent
            except (Unsupported, RuleError) as e:
                results.append(CaseResult(subject, n, "unsupported", detail=str(e)[:200]))
                continue
            if not budget.can_run():
                results.append(
                    CaseResult(subject, n, "unchecked", detail="solver budget exhausted")
                )
                continue
            payload = make_payload(subject, n)
            payload.update(timeout_ms=budget.per_call_ms, memory_mb=budget.memory_mb)
            c0 = time.perf_counter()
            res = pool.solve(payload, wall_s=budget.per_call_ms / 1000 + 5.0)
            el = time.perf_counter() - c0
            budget.calls += 1
            budget.elapsed_s += el
            if res is None:
                results.append(
                    CaseResult(
                        subject, n, "timeout", el * 1000, "wall-clock overrun; solver killed"
                    )
                )
                continue
            version = res.get("version", version)
            st = res["status"]
            if st == "unsat":
                results.append(CaseResult(subject, n, "unsat", el * 1000, smtlib=res["smtlib"]))
            elif st == "sat":
                objs, canvas = _objects_from_model(res["model"], n)
                if not concrete_ok(objs, canvas):
                    raise GroundingError(
                        f"solver witness for {subject} (n={n}) failed concrete re-execution"
                    )
                objs, canvas, how = _simplify(objs, canvas, concrete_ok, dom)
                witness = Witness(objs, canvas, predictions(objs, canvas), how, kind)
                results.append(CaseResult(subject, n, "sat", el * 1000))
            elif st == "error":
                results.append(
                    CaseResult(subject, n, "unsupported", el * 1000, res.get("detail", ""))
                )
            else:
                results.append(
                    CaseResult(
                        subject,
                        n,
                        st if st in ("timeout", "memory") else "timeout",
                        el * 1000,
                        res.get("detail", ""),
                    )
                )
    finally:
        if own_pool:
            pool.close()

    sts = [c.status for c in results]
    if witness is not None:
        status = "witness_found"
    elif results and all(s == "unsat" for s in sts):
        status = "no_witness_in_model"
    elif any(s in ("timeout", "memory") for s in sts):
        status = "timeout"
    elif any(s == "unchecked" for s in sts):
        status = "incomplete"
    else:
        status = "unsupported"
    if not version:
        import z3

        version = z3.get_version_string()
    return WitnessSearchResult(
        status,
        witness,
        results,
        version,
        dom.hash,
        [rule_hash(r) for r in rules],
        prop,
        (time.perf_counter() - t0) * 1000,
        {
            "calls": budget.calls,
            "elapsed_s": round(budget.elapsed_s, 4),
            "max_calls": budget.max_calls,
            "total_s": budget.total_s,
        },
    )


def find_disagreement(
    rules: list[list],
    object_counts: list[int],
    dom: DomainManifest,
    budget: Optional[SolverBudget] = None,
    pool: Optional[SolverPool] = None,
) -> WitnessSearchResult:
    """Find an in-domain input where two candidate rules' outputs differ by more than the visible threshold."""
    budget = budget or SolverBudget()
    thr = dom.query_visible_difference_px
    cases = []
    for i, j in combinations(range(len(rules)), 2):
        for n in object_counts:

            def probe(i=i, j=j, n=n):
                o, c, _ = make_inputs(n)
                compile_rule(rules[i], o, c)
                compile_rule(rules[j], o, c)

            cases.append((f"pair {i}-{j}", n, probe))
    pairs = {f"pair {i}-{j}": (i, j) for i, j in combinations(range(len(rules)), 2)}

    last = {"pair": None}

    def concrete_ok(objs, canvas):
        i, j = pairs[last["pair"]]
        return _differs(
            evaluate_rule(rules[i], objs, canvas), evaluate_rule(rules[j], objs, canvas), thr
        )

    def preds(objs, canvas):
        return [evaluate_rule(r, objs, canvas) for r in rules]

    def make_payload(subject, n):
        last["pair"] = subject
        i, j = pairs[subject]
        return {
            "mode": "disagree",
            "rules": [rules[i], rules[j]],
            "n": n,
            "domain": dom.canonical(),
            "threshold": str(thr),
        }

    return _run(
        cases,
        make_payload,
        concrete_ok,
        preds,
        "disagreement",
        rules,
        f"exists in-domain input where candidate outputs differ by > {thr} px (or one defines a target the other does not)",
        dom,
        budget,
        pool,
        thr,
    )


def find_public_constraint_violation(
    rule: list,
    constraints: list[str],
    object_counts: list[int],
    dom: DomainManifest,
    budget: Optional[SolverBudget] = None,
    pool: Optional[SolverPool] = None,
) -> WitnessSearchResult:
    """Find an in-domain input where `rule` violates an explicit PUBLIC requirement (never the private teacher rule)."""
    names = tuple(constraints)
    bad = [c for c in names if c not in PUBLIC_CONSTRAINTS]
    if bad:
        raise ValueError(f"not an encodable public constraint: {bad}")
    budget = budget or SolverBudget()
    cases = []
    for n in object_counts:

        def probe(n=n):
            o, c, _ = make_inputs(n)
            violation_formula(compile_rule(rule, o, c), o, c, names)

        cases.append((f"constraints {','.join(names)}", n, probe))

    def make_payload(subject, n):
        return {
            "mode": "violation",
            "rules": [rule],
            "n": n,
            "domain": dom.canonical(),
            "constraints": list(names),
        }

    def concrete_ok(objs, canvas):
        return _violates(evaluate_rule(rule, objs, canvas), objs, canvas, names)

    return _run(
        cases,
        make_payload,
        concrete_ok,
        lambda o, c: [evaluate_rule(rule, o, c)],
        "constraint_violation",
        [rule],
        f"exists in-domain input where the rule violates {list(names)}",
        dom,
        budget,
        pool,
        Fraction(0),
    )
