"""Interactive teaching API: a visitor teaches the badge rule, reuses it on Konva or Fabric, changes the tool underneath, and repairs.

Two modes, labelled in every response:

* ``reference`` (default): NO MODEL and NO PAID CALL. Candidate rules come from the non-model enumerative learner through the same
  TeachingSession the evaluation uses; native procedures are the SCRIPTED fixtures in api/fixtures.py.
* ``nemotron``: NVIDIA Nemotron (through Nebius Token Factory) proposes the rules, writes the native procedure and writes the repair. Every
  model output passes the same checks as in the evaluation (grammar validation, concrete replay, real-backend execution). If the model cannot
  produce a working procedure, a scripted fixture is used INSTEAD and the response says so. Spend is metered per session and capped globally
  (DEMO_MODEL_MAX_USD); when the cap is reached the mode is refused, never silently downgraded.

The verifier is the independent one used by the benchmark; here it judges execution against the rule the visitor just taught.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from open_apprentice.api import fixtures as fx
from open_apprentice.api.geometry import (
    CANVAS,
    boxes_of_outputs,
    boxes_of_scene,
    boxes_of_targets,
    card_scene,
    observed_boxes,
    view,
)
from open_apprentice.api.svg_export import build_svg
from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.bindings import (
    BindingRegistry,
    NativeBudget,
    backend_scene,
    expected_state,
    native_run,
    targets_from_rule,
)
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.enumerative import EnumerativeSource, _badge_rule, _lit
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.concepts.schemas import Concept
from open_apprentice.concepts.teaching import State, TeachingSession
from open_apprentice.concepts.transfer import repair_binding, transfer_concept
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.providers.base import Provider, ProviderError
from open_apprentice.providers.mock import MockProvider

router = APIRouter(prefix="/api/teach", tags=["teach"])
replay_router = APIRouter(prefix="/api", tags=["replay"])

MAX_SESSIONS = 20
TTL_SECONDS = 30 * 60
CONCEPT_ID = "badge"
VISIBLE_DIFF_PX = 6  # the evaluation uses 1 px; a human looking at a picture needs more
DRIFT = {
    "move_origin": "center"
}  # private tool change; only the Fabric backend supports it in this demo
DEFAULT_MODEL_CAP_USD = 4.0  # global ceiling for model-mode spend on one server process
SESSION_TOKEN_LIMIT = 250_000
SESSION_CALL_LIMIT = 40
CONSERVATIVE_USD_PER_MILLION = 3.0  # used only if the provider reported no cost for a call
RESERVE_USD = 0.25  # a model session is refused unless at least this much of the cap is left


def _label(mode: str, model_id: str = "") -> dict:
    if mode == "nemotron":
        return {
            "mode": "LIVE ENGINE + NVIDIA NEMOTRON",
            "candidate_rules": f"{model_id or 'Nemotron'} via Nebius Token Factory, checked by the same teaching loop as the evaluation",
            "native_procedures": "Nemotron-generated and accepted only after checks on the real backend; a scripted fixture is used instead, and labelled, if it fails",
            "verifier": "independent verifier, judging against the rule you taught",
        }
    return {
        "mode": "LIVE ENGINE, NO MODEL",
        "candidate_rules": "non-model enumerative learner (same teaching loop as the evaluation)",
        "native_procedures": "scripted fixtures, not model-generated",
        "verifier": "independent verifier, judging against the rule you taught",
    }


class StartIn(BaseModel):
    mode: str = Field(default="reference", pattern="^(reference|nemotron)$")


class AnswerIn(BaseModel):
    query_id: str
    answer: str = Field(pattern="^([A-D]|neither)$")
    candidate_set_hash: str


class RunIn(BaseModel):
    width: int = Field(ge=60, le=600)
    height: int = Field(default=80, ge=40, le=200)
    backend: str = Field(default="konva", pattern="^(konva|fabric)$")
    tool_change: bool = False


class BreakIn(BaseModel):
    backend: str = Field(default="konva", pattern="^(konva|fabric)$")
    tool_change: bool = False
    samples: int = Field(default=40, ge=1, le=80)
    seed: int = Field(default=0, ge=0, le=10_000)


@dataclass
class Live:
    id: str
    session: TeachingSession
    demo: dict
    ledger: Ledger
    mode: str = "reference"
    provider: Optional[Provider] = None
    model_id: str = ""
    registry: BindingRegistry = field(default_factory=BindingRegistry)
    concept: Optional[Concept] = None
    last_failure: Optional[dict] = None
    last_break: Optional[dict] = None  # the latest stress test, included in the evidence package
    last_run: Optional[dict] = (
        None  # what the export endpoints serialise: the latest executed layout and its evidence
    )
    fallbacks: list[str] = field(
        default_factory=list
    )  # every time a scripted fixture replaced a failed model output
    counted_usd: float = 0.0
    counted_tokens: int = 0
    touched: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _store(request: Request) -> dict[str, Live]:
    return request.app.state.live


def _get(request: Request, sid: str) -> Live:
    store = _store(request)
    now = time.time()
    for k in [k for k, v in store.items() if now - v.touched > TTL_SECONDS]:
        del store[k]
    live = store.get(sid)
    if live is None:
        raise HTTPException(404, "unknown or expired session")
    live.touched = now
    return live


def _engine(request: Request) -> tuple[str, str]:
    eng = getattr(request.app.state, "engine", None)
    if eng is None:
        raise HTTPException(503, "the graphics engine is not running on this server")
    return eng


def _opener(request: Request, backend: str, private: Optional[dict]):
    url, token = _engine(request)
    harness = EvaluatorHarness(url, token)

    def open_session(sc: dict) -> Any:
        try:
            s, initial = harness.open_session(
                backend_scene(sc), "api-demo", private, backend=backend
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                503, f"engine refused a session ({e.response.status_code}); try again shortly"
            ) from e
        open_session.initials.append(initial)  # type: ignore[attr-defined]
        return s

    open_session.initials = []  # type: ignore[attr-defined]
    return harness, open_session


# ---------------------------------------------------------------------------------------------------- model budget
def _cap_usd() -> float:
    try:
        return float(os.environ.get("DEMO_MODEL_MAX_USD", DEFAULT_MODEL_CAP_USD))
    except ValueError:
        return DEFAULT_MODEL_CAP_USD


def _spend(request: Request) -> dict:
    return request.app.state.spend


def _account(request: Request, live: Live) -> None:
    """Move this session's new consumption into the process-wide total. Unknown cost is charged at a conservative rate, never zero."""
    snap = live.ledger.snapshot()["consumed"]
    d_tokens = snap["tokens"] - live.counted_tokens
    usd = (
        snap["usd"]
        if snap["usd"] is not None
        else snap["tokens"] * CONSERVATIVE_USD_PER_MILLION / 1e6
    )
    d_usd = usd - live.counted_usd
    live.counted_tokens, live.counted_usd = snap["tokens"], usd
    sp = _spend(request)
    sp["usd"] += max(d_usd, 0.0)
    sp["tokens"] += max(d_tokens, 0)


def _meter(request: Request, live: Live) -> Optional[dict]:
    if live.mode != "nemotron":
        return None
    snap = live.ledger.snapshot()
    sp = _spend(request)
    return {
        "model": live.model_id,
        "label": "LIVE",
        "session_tokens": snap["consumed"]["tokens"],
        "session_calls": snap["consumed"]["calls"],
        "session_usd": round(live.counted_usd, 4),
        "unknown_cost_calls": snap["unknown_cost_calls"],
        "server_spend_usd": round(sp["usd"], 4),
        "server_cap_usd": _cap_usd(),
        "note": "dollars use the rates configured on the server; they are an estimate, not a bill",
    }


def _require_model_budget(request: Request) -> None:
    sp = _spend(request)
    if sp["usd"] + RESERVE_USD > _cap_usd():
        raise HTTPException(
            402,
            f"the model budget for this server is used up (${sp['usd']:.2f} of ${_cap_usd():.2f}); use the reference learner instead",
        )


def _provider_failure(e: ProviderError) -> HTTPException:
    return HTTPException(502, f"the model call failed ({e.code}): {str(e)[:160]}")


# ---------------------------------------------------------------------------------------------------- state view
def _state(request: Request, live: Live) -> dict:
    s = live.session
    out: dict[str, Any] = {
        "id": live.id,
        "mode": live.mode,
        "label": _label(live.mode, live.model_id),
        "meter": _meter(request, live),
        "fallbacks": list(live.fallbacks),
        "state": s.state.value,
        "intent_state": s.intent_state.value,
        "queries_asked": s.queries_asked,
        "rounds": s.rounds,
        "candidate_count": len(s.candidates),
        "note": s.unresolved_reason,
        "demonstration": live.demo,
    }
    if s.state == State.AWAITING_USER and s.pending_kind == "question":
        q = s.public_question()
        sc = q["input_scene"]
        out["question"] = {
            "source": s.pending.source if s.pending else "",
            "query_id": q["query_id"],
            "candidate_set_hash": q["candidate_set_hash"],
            "base": view("Question input", boxes_of_scene(sc)),
            "options": [
                {"id": k, "boxes": boxes_of_outputs(sc, o)} for k, o in sorted(q["options"].items())
            ],
        }
    elif s.state == State.AWAITING_USER and s.pending_kind == "correction":
        out["correction"] = {
            "supported": False,
            "message": "You chose Neither. Entering a corrected example is not built in this interface yet.",
        }
    if s.state == State.INTENT_READY:
        if live.concept is None:
            live.concept = s.finalize(CONCEPT_ID)
        c = live.concept
        out["concept"] = {
            "rule_text": c.summary,
            "sealed_hash": c.sealed_hash(),
            "ledger_entries": len(s.ledger.entries),
            "ledger_chain_verified": bool(s.ledger.verify_chain()),
            "answer_source": "you",
        }
    return jsonable_encoder(out)


# ---------------------------------------------------------------------------------------------------- endpoints
@router.post("")
async def start(request: Request, body: Optional[StartIn] = None) -> dict:
    mode = body.mode if body else "reference"
    provider: Optional[Provider] = None
    if mode == "nemotron":
        provider = getattr(request.app.state, "provider", None)
        if provider is None:
            raise HTTPException(
                503,
                "Nemotron mode is not available on this server (no model credentials configured)",
            )
        _require_model_budget(request)
    store = _store(request)
    if len(store) >= MAX_SESSIONS:
        oldest = min(store.values(), key=lambda v: v.touched)
        del store[oldest.id]
    dom = DomainManifest(
        query_visible_difference_px=Fraction(VISIBLE_DIFF_PX)
    )  # a person must be able to SEE the difference
    ledger = (
        Ledger(Limits(tokens=SESSION_TOKEN_LIMIT, calls=SESSION_CALL_LIMIT, actions=5000))
        if mode == "nemotron"
        else Ledger(Limits(tokens=10_000_000, calls=1000, actions=5000))
    )
    pool = getattr(request.app.state, "pool", None)
    if mode == "nemotron":
        sess = TeachingSession(
            provider, ledger, dom, [2], pool=pool, teacher_source="user", prefer_readable_queries=True,
            completion_cap=int(os.environ.get("NEBIUS_COMPLETION_CAP", "32000") or 32000),
        )  # fmt: skip
    else:
        sess = TeachingSession(
            None, ledger, dom, [2], pool=pool, teacher_source="user",
            candidate_source=EnumerativeSource(dom, [2]), prefer_readable_queries=True,
        )  # fmt: skip
    before = card_scene(150)
    after = evaluate_rule(
        _badge_rule("top-right", _lit(12)), before["objects"], before["canvas"]
    )  # all candidates coincide at width 150
    demo = {
        "canvases": [
            view("Before", boxes_of_scene(before)),
            view("Your demonstration", boxes_of_outputs(before, after)),
        ]
    }
    live = Live(uuid.uuid4().hex[:12], sess, jsonable_encoder(demo), ledger, mode=mode, provider=provider,
                model_id=getattr(provider, "requested_model", "") if provider else "")  # fmt: skip
    store[live.id] = live
    try:
        await sess.start({"scene": before, "after": after})
    except ProviderError as e:
        _account(request, live)
        store.pop(
            live.id, None
        )  # a session that never got its first candidates is not worth keeping
        raise _provider_failure(e) from e
    _account(request, live)
    return _state(request, live)


@router.get("/{sid}")
async def get_state(request: Request, sid: str) -> dict:
    return _state(request, _get(request, sid))


@router.post("/{sid}/answer")
async def answer(request: Request, sid: str, body: AnswerIn) -> dict:
    live = _get(request, sid)
    if live.mode == "nemotron":
        _require_model_budget(request)
    async with live.lock:
        try:
            await live.session.answer(body.query_id, body.answer, body.candidate_set_hash)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        except ProviderError as e:
            _account(request, live)
            raise _provider_failure(e) from e
    _account(request, live)
    return _state(request, live)


def _why(result: Any) -> str:
    """One plain-language reason a model attempt failed, taken from the attempt log (never hidden, never raw reasoning)."""
    for a in reversed(result.attempts):
        for key in ("error", "rejected", "failed_stage"):
            if a.get(key):
                return str(a[key])[:120]
        nat = a.get("native") or {}
        if nat.get("error"):
            return "runtime error on the real backend: " + str(nat["error"])[:100]
        if a.get("abstract_check") is False:
            return "failed the documented-contract simulator"
    return result.status


def _fixture_provider(role: str, *programs: list) -> MockProvider:
    return MockProvider({role: [fx.cands(*programs)] * 2})


async def _ensure_binding(request: Request, live: Live, backend: str) -> Optional[str]:
    """Returns a fallback note if a scripted fixture had to replace a failed model procedure."""
    reg = live.registry
    if reg.current(CONCEPT_ID, backend) is not None:
        return None
    _, original = _opener(request, backend, None)
    scenes = [card_scene(150), card_scene(60)]
    note: Optional[str] = None
    if live.mode == "nemotron" and live.provider is not None:
        _require_model_budget(request)
        r = await transfer_concept(
            live.concept,
            backend,
            live.provider,
            live.ledger,
            NativeBudget(48),
            original,
            scenes,
            reg,
            backend,
            origin="model",
        )
        _account(request, live)
        if r.status == "validated":
            return None
        note = f"Nemotron could not produce a native procedure for {backend} that passed the checks ({r.status}: {_why(r)}); a scripted fixture was used instead."
        live.fallbacks.append(note)
    r = await transfer_concept(
        live.concept,
        backend,
        _fixture_provider("binding", fx.NAIVE),
        live.ledger,
        NativeBudget(),
        original,
        scenes,
        reg,
        backend,
        origin="fixture",
    )
    if r.status != "validated":
        raise HTTPException(
            422,
            f"the scripted native procedure could not realise your rule on {backend} ({r.status})",
        )
    return note


def _check_list(rep: Any) -> list[dict]:
    return [
        {"name": c.name, "passed": bool(c.passed), "detail": c.detail[:200]} for c in rep.checks
    ]


@router.post("/{sid}/run")
async def run(request: Request, sid: str, body: RunIn) -> dict:
    live = _get(request, sid)
    if live.concept is None:
        raise HTTPException(409, "teach the rule first (answer the question)")
    if body.tool_change and body.backend != "fabric":
        raise HTTPException(
            422, "the silent tool change is only available on the Fabric backend in this demo"
        )
    async with live.lock:
        try:
            await _ensure_binding(request, live, body.backend)
        except ProviderError as e:
            _account(request, live)
            raise _provider_failure(e) from e
        binding = live.registry.current(CONCEPT_ID, body.backend)
        sc = card_scene(body.width, body.height)
        rule = live.concept.rule
        targets = targets_from_rule(rule, sc)
        harness, opener = _opener(request, body.backend, DRIFT if body.tool_change else None)
        s = opener(sc)
        initial = opener.initials[-1]
        try:
            res = native_run(binding.prog, targets, s, CANVAS, NativeBudget(60))
            rep = harness.judge_expected(s, initial, expected_state(rule, sc), ["card"])
            observed = observed_boxes(s, targets)
        finally:
            s.close()
        passed = bool(rep.passed)
        if body.tool_change and not res["passed"]:
            live.last_failure = {
                "scene": sc,
                "targets": targets,
                "diffs": res.get("diffs", []),
                "width": body.width,
                "height": body.height,
            }
        out = {
            "label": _label(live.mode, live.model_id),
            "meter": _meter(request, live),
            "fallbacks": list(live.fallbacks),
            "backend": body.backend,
            "tool_change": body.tool_change,
            "width": body.width,
            "height": body.height,
            "canvases": [
                view("Expected (your rule)", boxes_of_targets(targets, sc)),
                view(
                    f"{body.backend.title()} result"
                    + (" after the tool change" if body.tool_change else ""),
                    observed,
                ),
            ],
            "native_passed": bool(res["passed"]),
            "native_diffs": res.get("diffs", []),
            "native_error": res.get("error"),
            "verifier_passed": passed,
            "checks": _check_list(rep),
            "binding": {
                "version": binding.version,
                "origin": binding.origin,
                "program_hash": binding.program_hash,
                "concept_hash": binding.concept_sealed_hash,
                "native_actions_used": res.get("native_actions"),
            },
            "can_repair": bool(body.tool_change and not res["passed"] and live.last_failure),
            "concept_hash": live.concept.sealed_hash(),
        }
        live.last_run = {
            "boxes": observed,
            "canvas": CANVAS,
            "request": body.model_dump(),
            "result": jsonable_encoder(
                {
                    k: out[k]
                    for k in (
                        "native_passed",
                        "verifier_passed",
                        "checks",
                        "binding",
                        "native_diffs",
                        "concept_hash",
                    )
                }
            ),
        }
        return jsonable_encoder(out)


def _break_cases(samples: int, seed: int) -> list[tuple[int, int, int, int]]:
    """(width, height, x, y): the supported-domain boundaries first, then seeded random cases. Deterministic for a given seed."""
    edges = [(w, h, 100, 100) for w in (60, 61, 150, 599, 600) for h in (40, 80, 200)]
    edges += [(300, 80, 0, 0), (300, 80, 200, 200), (600, 200, 0, 0), (60, 40, 300, 300)]
    rng = random.Random(seed)
    cases = edges[:samples]
    while len(cases) < samples:
        cases.append(
            (
                rng.randrange(60, 601),
                rng.randrange(40, 201),
                rng.randrange(0, 301, 10),
                rng.randrange(0, 201, 10),
            )
        )
    return cases


@router.post("/{sid}/break")
async def break_it(request: Request, sid: str, body: BreakIn) -> dict:
    """Stress test: run the active binding on many generated inputs on the REAL engine and judge each with the independent verifier.
    Reports exactly what was tested. It is bounded sampling, not a proof; the response says so."""
    live = _get(request, sid)
    if live.concept is None:
        raise HTTPException(409, "teach the rule first (answer the question)")
    if body.tool_change and body.backend != "fabric":
        raise HTTPException(
            422, "the silent tool change is only available on the Fabric backend in this demo"
        )
    async with live.lock:
        try:
            await _ensure_binding(request, live, body.backend)
        except ProviderError as e:
            _account(request, live)
            raise _provider_failure(e) from e
        binding = live.registry.current(CONCEPT_ID, body.backend)
        rule = live.concept.rule
        harness, opener = _opener(request, body.backend, DRIFT if body.tool_change else None)
        t0 = time.time()
        failures: list[dict] = []
        cases = _break_cases(body.samples, body.seed)
        for w, h, x, y in cases:
            sc = card_scene(w, h, x, y)
            targets = targets_from_rule(rule, sc)
            sess = opener(sc)
            initial = opener.initials[-1]
            try:
                res = native_run(binding.prog, targets, sess, CANVAS, NativeBudget(60))
                rep = harness.judge_expected(sess, initial, expected_state(rule, sc), ["card"])
            finally:
                sess.close()
            if not rep.passed or not res["passed"]:
                failures.append(
                    {
                        "width": w, "height": h, "x": x, "y": y, "native_passed": bool(res["passed"]),
                        "failed_checks": [c.name for c in rep.checks if not c.passed], "native_diffs": res.get("diffs", [])[:2],
                        "native_error": res.get("error"),
                    }
                )  # fmt: skip
        out = {
            "backend": body.backend,
            "tool_change": body.tool_change,
            "binding": {
                "version": binding.version,
                "origin": binding.origin,
                "program_hash": binding.program_hash,
            },
            "tested": len(cases),
            "passed": len(cases) - len(failures),
            "failed": len(failures),
            "failures": failures[:8],
            "seed": body.seed,
            "elapsed_s": round(time.time() - t0, 1),
            "coverage": f"{len(cases)} inputs: the supported-domain boundaries first (widths 60-600, heights 40-200), then seeded random card sizes and positions. Bounded sampling on the real engine, not a proof for other inputs.",
        }
        live.last_break = out
        return jsonable_encoder(out)


@router.get("/{sid}/export.svg")
async def export_svg(request: Request, sid: str) -> Response:
    live = _get(request, sid)
    if live.last_run is None or live.concept is None:
        raise HTTPException(409, "run the rule first; there is nothing to export yet")
    r, req = live.last_run["result"], live.last_run["request"]
    meta = {
        "rule": live.concept.summary,
        "concept_hash": r["concept_hash"],
        "backend": req["backend"],
        "card_width": req["width"],
        "tool_change": str(req["tool_change"]).lower(),
        "binding_version": r["binding"]["version"],
        "binding_origin": r["binding"]["origin"],
        "binding_program_hash": r["binding"]["program_hash"],
        "native_check": "pass" if r["native_passed"] else "FAIL",
        "independent_verifier": "pass" if r["verifier_passed"] else "FAIL",
        "model_used": live.model_id if live.mode == "nemotron" else "none",
    }
    svg = build_svg(live.last_run["boxes"], live.last_run["canvas"], meta)
    return Response(
        svg,
        media_type="image/svg+xml",
        headers={"Content-Disposition": f'attachment; filename="open-apprentice-{sid}.svg"'},
    )


@router.get("/{sid}/evidence.json")
async def export_evidence(request: Request, sid: str) -> JSONResponse:
    """The evidence package: everything needed to re-check this layout without trusting the interface."""
    live = _get(request, sid)
    if live.last_run is None or live.concept is None:
        raise HTTPException(409, "run the rule first; there is nothing to export yet")
    s = live.session
    c = live.concept
    cur = live.registry.current(CONCEPT_ID, live.last_run["request"]["backend"])
    pkg = {
        "label": _label(live.mode, live.model_id),
        "concept": {
            "rule_text": c.summary,
            "rule": c.rule,
            "input_schema": c.input_schema,
            "preservation": list(c.preservation_constraints),
            "domain_hash": c.domain_hash,
            "sealed_hash": c.sealed_hash(),
            "intent_state": s.intent_state.value,
            "queries_asked": s.queries_asked,
        },
        "domain": s.dom.canonical(),
        "ledger": [
            {
                "seq": e.seq,
                "kind": e.kind,
                "payload": e.payload,
                "source": e.source,
                "prev_hash": e.prev_hash,
                "hash": e.hash,
            }
            for e in s.ledger.entries
        ],
        "teaching_ledger": [{"kind": e.kind, "source": e.source} for e in s.ledger.entries],
        "teaching_ledger_chain_verified": bool(s.ledger.verify_chain()),
        "binding_program": cur.program_json if cur else None,
        "run": live.last_run["request"],
        "result": live.last_run["result"],
        "observed_geometry": live.last_run["boxes"],
        "binding_versions": [
            {
                "version": b.version,
                "parent": b.parent_version,
                "program_hash": b.program_hash,
                "origin": b.origin,
            }
            for _, v in live.registry.versions.items()
            for b in v
        ],
        "stress_test": live.last_break,
        "model_meter": _meter(request, live),
        "fallbacks": list(live.fallbacks),
        "notes": [
            "Binding origin says whether each native program was generated by the model or is a scripted fixture.",
            "The verifier judged against the rule the user taught.",
        ],
    }
    return JSONResponse(
        jsonable_encoder(pkg),
        headers={"Content-Disposition": f'attachment; filename="evidence-{sid}.json"'},
    )


@router.post("/{sid}/repair")
async def repair(request: Request, sid: str) -> dict:
    live = _get(request, sid)
    if live.concept is None or live.last_failure is None:
        raise HTTPException(
            409, "nothing to repair: run the Fabric tool change first and let it fail"
        )
    async with live.lock:
        reg, concept = live.registry, live.concept
        old = reg.current(CONCEPT_ID, "fabric")
        if old is None:
            raise HTTPException(409, "no Fabric binding to repair")
        f = live.last_failure
        sealed = concept.sealed_hash()
        _, drifted = _opener(request, "fabric", DRIFT)
        _, original = _opener(request, "fabric", None)
        witness = {
            "scene": f["scene"],
            "targets": f["targets"],
            "observed": [{"key": d["key"], "observed": d["observed"]} for d in f["diffs"]],
        }
        retained, fresh = [card_scene(150)], card_scene(80)
        attempts: list[dict] = []
        status = "failed"
        if live.mode == "nemotron" and live.provider is not None:
            _require_model_budget(request)
            try:
                r = await repair_binding(
                    concept,
                    "fabric",
                    old,
                    witness,
                    live.provider,
                    live.ledger,
                    NativeBudget(48),
                    drifted,
                    original,
                    retained,
                    fresh,
                    reg,
                    "fabric",
                    origin="model",
                )
            except ProviderError as e:
                _account(request, live)
                raise _provider_failure(e) from e
            _account(request, live)
            attempts += [dict(a, source="model") for a in r.attempts]
            status = r.status
            if status != "validated":
                live.fallbacks.append(
                    "Nemotron's repair did not pass the retained-case checks; a scripted fixture repair was tried instead."
                )
        if status != "validated":
            r = await repair_binding(
                concept, "fabric", reg.current(CONCEPT_ID, "fabric") or old, witness,
                _fixture_provider("binding_repair", fx.HARDCODED_OFFSET, fx.PROBING), live.ledger, NativeBudget(),
                drifted, original, retained, fresh, reg, "fabric", origin="fixture",
            )  # fmt: skip
            attempts += [dict(a, source="fixture") for a in r.attempts]
            status = r.status
        new = reg.current(CONCEPT_ID, "fabric")
        live.last_failure = None if status == "validated" else live.last_failure
        out = {
            "label": _label(live.mode, live.model_id),
            "meter": _meter(request, live),
            "fallbacks": list(live.fallbacks),
            "status": status,
            "attempts": [
                {
                    "candidate": i,
                    "source": a.get("source", "fixture"),
                    "diagnosis": a.get("diagnosis", ""),
                    "failed_stage": a.get("failed_stage"),
                    "cases": a.get("cases", []),
                }
                for i, a in enumerate(attempts)
            ],
            "old_program": old.prog,
            "new_program": new.prog if new else None,
            "versions": [
                {
                    "version": b.version,
                    "parent": b.parent_version,
                    "program_hash": b.program_hash,
                    "origin": b.origin,
                    "active": new is not None and b.version == new.version,
                }
                for b in reg.versions.get((CONCEPT_ID, "fabric"), [])
            ],
            "concept_hash_before": sealed,
            "concept_hash_after": concept.sealed_hash(),
            "rule_unchanged": concept.sealed_hash() == sealed
            and (new is None or new.concept_sealed_hash == sealed),
        }
        return jsonable_encoder(out)


class ReplayIn(BaseModel):
    package: dict


@replay_router.post("/replay")
async def replay_endpoint(body: ReplayIn) -> dict:
    """Re-check an evidence package OFFLINE (no engine, no model). Accepts any package, so a reader can edit one and watch it fail."""
    from open_apprentice.evaluation.replay import replay_package

    raw = len(str(body.package))
    if raw > 500_000:
        raise HTTPException(413, "package too large")
    try:
        return replay_package(body.package)
    except (KeyError, TypeError, ValueError, IndexError) as e:
        raise HTTPException(
            422, f"this does not look like an evidence package ({type(e).__name__})"
        ) from e
