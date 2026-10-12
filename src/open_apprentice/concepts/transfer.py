"""Checked transfer of a sealed concept to a backend, and binding repair (spec 8.7, 11, 12.5).

transfer_concept: model proposes <=3 binding programs; the host validates each statically, runs the
ABSTRACT check (documented-contract model) and then the REAL backend, comparing observed geometry with the
concept's targets. A binding that passes the abstract check but fails natively is reported as a
reproduced MISMATCH and the abstract model is marked untrusted for that context.

repair_binding: changes ONLY the binding. Candidates must pass (1) the failing witness in the current
environment, (2) retained earlier cases replayed under their ORIGINAL environment, (3) a fresh case in the
current environment. Promotion re-checks the sealed concept hash.
"""

from __future__ import annotations

import asyncio

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from open_apprentice.budget import BudgetExhausted, Ledger
from open_apprentice.concepts.bindings import (
    BINDING_TOOLS,
    Binding,
    BindingRegistry,
    NativeBudget,
    PromotionError,
    abstract_check,
    native_run,
    targets_from_rule,
)
from open_apprentice.concepts.hypotheses import neutral
from open_apprentice.concepts.schemas import Concept, NativeStatus, sha
from open_apprentice.environments.client import EngineSession
from open_apprentice.environments.docs import DOCS
from open_apprentice.providers.base import (
    TruncatedOutput,
    CallContext,
    Message,
    Provider,
    ProviderError,
    StrictModel,
)
from open_apprentice.skills.interpreter import ProgramError, validate_program

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "binding.md"
MAX_NATIVE_CANDIDATES = 3

SessionFactory = Callable[
    [dict], EngineSession
]  # opaque: builds a session for a scene (drift is the evaluator's business)
# Alternative proposer (e.g. a declared non-LLM template library). Same validation, same budgets.
BindingSource = Callable[[str, dict], Awaitable[list["BindingOut"]]]


class BindingOut(StrictModel):
    diagnosis: str = ""
    program: list[dict[str, Any]]


class BindingSet(StrictModel):
    candidates: list[BindingOut]


@dataclass
class TransferResult:
    status: str  # validated | failed | incomplete | provider_error
    binding: Optional[Binding] = None
    attempts: list[dict] = field(default_factory=list)
    native_status: NativeStatus = NativeStatus.UNTESTED
    mismatch: Optional[dict] = None  # reproduced abstract-vs-native disagreement (concrete witness)
    semantic_model_trusted: bool = True
    native_actions: int = 0
    model_calls: int = 0


def _scene_hash(scene: dict) -> str:
    return sha(neutral(scene))[:12]


def _run_on(  # blocking engine I/O: callers run it via asyncio.to_thread
    factory: SessionFactory, program: list, concept: Concept, scene: dict, budget: NativeBudget
) -> dict:
    targets = targets_from_rule(concept.rule, scene)
    session = factory(scene)
    try:
        res = native_run(
            program,
            targets,
            session,
            {"w": float(scene["canvas"]["w"]), "h": float(scene["canvas"]["h"])},
            budget,
        )
    finally:
        session.close()
    res.update(scene=_scene_hash(scene), targets=targets)
    return res


async def _propose(
    provider: Provider,
    ledger: Ledger,
    role: str,
    payload: dict,
    followup: Optional[tuple[str, dict]] = None,
) -> tuple[list[BindingOut], str]:
    msgs = [Message("system", PROMPT.read_text()), Message("user", json.dumps(payload))]
    if followup:  # (previous assistant reply, concrete failures)
        msgs += [Message("assistant", followup[0]), Message("user", json.dumps(followup[1]))]
    for attempt in (
        0,
        1,
    ):  # a reasoning model can spend its whole allowance thinking: ONE counted retry
        try:
            comp = await provider.complete_json(
                messages=msgs,
                output_schema=BindingSet,
                ctx=CallContext(role=role, category="binding"),
                ledger=ledger,
                max_tokens=3000,
            )
            break
        except TruncatedOutput:
            if attempt:
                raise
    return comp.parsed.candidates[:MAX_NATIVE_CANDIDATES], comp.parsed.model_dump_json()


def _problem(att: dict) -> str:
    """One plain-language reason a candidate failed, with the concrete numbers/errors, for the correction turn."""
    if att.get("rejected"):
        return att["rejected"]
    if att.get("abstract_check") is False:
        return (
            "the program fails even on the documented-contract simulator: "
            + str(att.get("abstract_error") or "targets not reached")[:200]
        )
    n = att.get("native") or {}
    if n.get("error"):
        return "runtime error on the real backend: " + str(n["error"])[:200]
    if n.get("diffs"):
        return (
            "it ran, but the observed geometry differs from the targets: "
            + json.dumps(n["diffs"][:2])[:300]
        )
    return "failed on the confirmation scene" if att.get("confirm") else "unknown failure"


def _valid(program: list) -> Optional[str]:
    try:
        validate_program(program, frozenset(BINDING_TOOLS))
        return None
    except ProgramError as e:
        return str(e)[:120]


async def transfer_concept(
    concept: Concept,
    backend: str,
    provider: Optional[Provider],
    ledger: Ledger,
    budget: NativeBudget,
    factory: SessionFactory,
    scenes: list[dict],
    registry: BindingRegistry,
    schema_hash: str,
    origin: str = "model",
    source: Optional[BindingSource] = None,
    ground: bool = True,
) -> TransferResult:
    """scenes[0] calibrates candidates; scenes[1] confirms the first survivor on a different input."""
    res = TransferResult("failed")
    payload = {
        "backend": backend,
        "documentation": DOCS[backend],
        "example_target_sets": [targets_from_rule(concept.rule, s) for s in scenes[:2]],
    }
    try:
        if source is not None:
            cands = (await source("binding", payload))[:MAX_NATIVE_CANDIDATES]
        else:
            cands, assistant_json = await _propose(provider, ledger, "binding", payload)
            res.model_calls = 1
    except BudgetExhausted:
        res.status = "incomplete"
        return res
    except ProviderError as e:
        res.status = "provider_error"
        res.attempts.append({"error": e.code})
        return res

    batch, first_of_batch = 0, 0
    while True:
        for i, c in enumerate(cands):
            att: dict[str, Any] = {
                "batch": batch,
                "candidate": i,
                "diagnosis": c.diagnosis,
                "program_excerpt": json.dumps(c.program, separators=(",", ":"))[:1800],
            }
            res.attempts.append(att)
            bad = _valid(c.program)
            if bad:
                att["rejected"] = f"invalid program: {bad}"
                continue
            t0 = targets_from_rule(concept.rule, scenes[0])
            ab = abstract_check(
                c.program,
                t0,
                scenes[0],
                {"w": float(scenes[0]["canvas"]["w"]), "h": float(scenes[0]["canvas"]["h"])},
            )
            att["abstract_check"] = ab["passed"]
            if not ab["passed"]:
                att["abstract_error"] = ab.get("error") or ab.get("diffs")
            if not ground:
                # ABLATION ONLY (disposable scenes): accept on the abstract model alone - the failure mode spec 12.5 warns about.
                if not ab["passed"]:
                    continue
                v = registry.next_version(concept.concept_id, backend)
                res.binding = Binding.create(
                    concept,
                    backend,
                    v,
                    registry.active.get((concept.concept_id, backend)),
                    c.program,
                    schema_hash,
                    {
                        "passed": True,
                        "regression_passed": True,
                        "native_status": NativeStatus.UNTESTED.value,
                        "grounding": "ABSTRACT ONLY (ablation)",
                        "cases": [],
                    },
                    origin,
                )
                registry.promote(res.binding, concept, "ablation: abstract-only acceptance")
                res.status, res.native_status = "validated", NativeStatus.UNTESTED
                return res
            nat = await asyncio.to_thread(_run_on, factory, c.program, concept, scenes[0], budget)
            att["native"] = {k: nat.get(k) for k in ("passed", "diffs", "error", "native_actions")}
            res.native_actions = budget.used
            if nat.get("budget_exhausted"):
                res.status = "incomplete"
                return res
            if not nat["passed"]:
                if ab["passed"]:
                    res.native_status = NativeStatus.REPRODUCED_MISMATCH
                    res.semantic_model_trusted = False
                    res.mismatch = {
                        "scene": nat["scene"],
                        "program_hash": sha(c.program),
                        "expected_targets": nat["targets"],
                        "native_diffs": nat["diffs"],
                        "abstract_check_passed": True,
                    }
                continue
            conf = await asyncio.to_thread(_run_on, factory, c.program, concept, scenes[1], budget)
            att["confirm"] = {
                k: conf.get(k) for k in ("passed", "diffs", "error", "native_actions")
            }
            res.native_actions = budget.used
            if conf.get("budget_exhausted"):
                res.status = "incomplete"
                return res
            if not conf["passed"]:
                continue
            v = registry.next_version(concept.concept_id, backend)
            res.binding = Binding.create(
                concept,
                backend,
                v,
                registry.active.get((concept.concept_id, backend)),
                c.program,
                schema_hash,
                {
                    "passed": True,
                    "regression_passed": True,
                    "native_status": NativeStatus.CHECKED_ON_LISTED_CASES.value,
                    "cases": [
                        {"scene": nat["scene"], "native_actions": nat["native_actions"]},
                        {"scene": conf["scene"], "native_actions": conf["native_actions"]},
                    ],
                    "scope": "listed cases only; not a proof for other inputs",
                },
                origin,
            )
            registry.promote(res.binding, concept, "transfer validated on listed cases")
            res.status, res.native_status = "validated", NativeStatus.CHECKED_ON_LISTED_CASES
            return res
        # No candidate validated. A model-driven search gets ONE counted correction batch with the concrete failures.
        if batch == 1 or source is not None or provider is None:
            return res
        fb = {
            "your_candidates_were_run": [
                {"candidate": a["candidate"], "problem": _problem(a)}
                for a in res.attempts[first_of_batch:]
            ],
            "instruction": "None of your programs reached the targets. Fix the problems above and reply in the same JSON format with up to 3 corrected, "
            "different candidates. Remember the exact return shapes of the tools.",
        }
        first_of_batch = len(res.attempts)
        try:
            cands, assistant_json = await _propose(
                provider, ledger, "binding", payload, followup=(assistant_json, fb)
            )
            res.model_calls += 1
        except (BudgetExhausted, ProviderError):
            return res
        batch = 1


async def repair_binding(
    concept: Concept,
    backend: str,
    old: Binding,
    witness: dict,
    provider: Optional[Provider],
    ledger: Ledger,
    budget: NativeBudget,
    current_factory: SessionFactory,
    original_factory: SessionFactory,
    retained_scenes: list[dict],
    fresh_scene: dict,
    registry: BindingRegistry,
    schema_hash: str,
    origin: str = "model",
    source: Optional[BindingSource] = None,
) -> TransferResult:
    """Repair the BINDING only. `witness` = {scene, targets, observed} from a reproduced native mismatch."""
    res = TransferResult(
        "failed", native_status=NativeStatus.REPRODUCED_MISMATCH, semantic_model_trusted=False
    )
    payload = {
        "backend": backend,
        "documentation": DOCS[backend],
        "failing_program": old.prog,
        "reproduced_failure": {
            "expected_targets": witness["targets"],
            "observed": witness["observed"],
        },
        "forbidden": [
            "changing the targets",
            "changing the rule",
            "narrowing which inputs are handled",
        ],
    }
    try:
        if source is not None:
            cands = (await source("binding_repair", payload))[:MAX_NATIVE_CANDIDATES]
        else:
            cands, _ = await _propose(provider, ledger, "binding_repair", payload)
            res.model_calls = 1
    except BudgetExhausted:
        res.status = "incomplete"
        return res
    except ProviderError as e:
        res.status = "provider_error"
        res.attempts.append({"error": e.code})
        return res

    for i, c in enumerate(cands):
        att: dict[str, Any] = {"candidate": i, "diagnosis": c.diagnosis}
        res.attempts.append(att)
        bad = _valid(c.program)
        if bad:
            att["rejected"] = f"invalid program: {bad}"
            continue
        stages = (
            [("witness_in_current_env", current_factory, witness["scene"])]
            + [("retained_in_original_env", original_factory, s) for s in retained_scenes]
            + [("fresh_in_current_env", current_factory, fresh_scene)]
        )
        cases, ok = [], True
        for name, fac, scene in stages:
            r = await asyncio.to_thread(_run_on, fac, c.program, concept, scene, budget)
            res.native_actions = budget.used
            cases.append(
                {
                    "stage": name,
                    "passed": r["passed"],
                    "scene": r["scene"],
                    "native_actions": r.get("native_actions"),
                }
            )
            if r.get("budget_exhausted"):
                att["cases"] = cases
                res.status = "incomplete"
                return res
            if not r["passed"]:
                ok = False
                att["failed_stage"] = name
                att["diffs"] = r.get("diffs")
                break
        att["cases"] = cases
        if not ok:
            continue
        nb = Binding.create(
            concept,
            backend,
            registry.next_version(concept.concept_id, backend),
            old.version,
            c.program,
            schema_hash,
            {
                "passed": True,
                "regression_passed": True,
                "cases": cases,
                "repaired_from": old.version,
                "native_status": NativeStatus.CHECKED_ON_LISTED_CASES.value,
            },
            origin,
        )
        try:
            registry.promote(nb, concept, "binding repair: witness + retained + fresh cases pass")
        except PromotionError as e:
            att["promotion"] = str(e)
            res.status = "failed"
            return res
        res.binding, res.status, res.native_status = (
            nb,
            "validated",
            NativeStatus.CHECKED_ON_LISTED_CASES,
        )
        return res
    registry.events.append(
        {
            "event": "quarantined",
            "backend": backend,
            "version": old.version,
            "why": "no repair candidate passed witness + retained + fresh cases",
        }
    )
    return res
