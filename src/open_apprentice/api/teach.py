"""Interactive teaching API: a visitor teaches the badge rule, reuses it on Konva or Fabric, changes the tool underneath, and repairs.

NO MODEL and NO PAID CALL anywhere in this module. Candidate rules come from the non-model enumerative learner through the same
TeachingSession used by the evaluation (same questions, same ledger, same Neither handling). Native procedures are the SCRIPTED
fixtures in api/fixtures.py and are labelled as such in every response. The verifier is the independent one used by the benchmark;
here it judges execution against the rule the visitor just taught (intent is the visitor's, not the system's).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from open_apprentice.api import fixtures as fx
from open_apprentice.api.svg_export import build_svg
from open_apprentice.api.geometry import (
    CANVAS,
    boxes_of_outputs,
    boxes_of_scene,
    boxes_of_targets,
    card_scene,
    observed_boxes,
    view,
)
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
from open_apprentice.providers.mock import MockProvider

router = APIRouter(prefix="/api/teach", tags=["teach"])

MAX_SESSIONS = 20
TTL_SECONDS = 30 * 60
CONCEPT_ID = "badge"
VISIBLE_DIFF_PX = 6  # the evaluation uses 1 px; a human looking at a picture needs more
DRIFT = {
    "move_origin": "center"
}  # private tool change; only the Fabric backend supports it in this demo
LABEL = {
    "mode": "LIVE ENGINE, NO MODEL",
    "candidate_rules": "non-model enumerative learner (same teaching loop as the evaluation)",
    "native_procedures": "scripted fixtures, not model-generated",
    "verifier": "independent verifier, judging against the rule you taught",
}


class AnswerIn(BaseModel):
    query_id: str
    answer: str = Field(pattern="^([A-D]|neither)$")
    candidate_set_hash: str


class RunIn(BaseModel):
    width: int = Field(ge=60, le=600)
    height: int = Field(default=80, ge=40, le=200)
    backend: str = Field(default="konva", pattern="^(konva|fabric)$")
    tool_change: bool = False


@dataclass
class Live:
    id: str
    session: TeachingSession
    demo: dict
    registry: BindingRegistry = field(default_factory=BindingRegistry)
    concept: Optional[Concept] = None
    last_failure: Optional[dict] = None
    last_run: Optional[dict] = (
        None  # what the export endpoints serialise: the latest executed layout and its evidence
    )
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


def _ledger() -> Ledger:
    return Ledger(Limits(tokens=10_000_000, calls=1000, actions=5000))


# ---------------------------------------------------------------------------------------------------- state view
def _state(live: Live) -> dict:
    s = live.session
    out: dict[str, Any] = {
        "id": live.id,
        "label": LABEL,
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
async def start(request: Request) -> dict:
    store = _store(request)
    if len(store) >= MAX_SESSIONS:
        oldest = min(store.values(), key=lambda v: v.touched)
        del store[oldest.id]
    dom = DomainManifest(
        query_visible_difference_px=Fraction(VISIBLE_DIFF_PX)
    )  # a person must be able to SEE the difference
    sess = TeachingSession(
        None,
        _ledger(),
        dom,
        [2],
        pool=getattr(request.app.state, "pool", None),
        teacher_source="user",
        candidate_source=EnumerativeSource(dom, [2]),
        prefer_readable_queries=True,
    )
    before = card_scene(150)
    after = evaluate_rule(
        _badge_rule("top-right", _lit(12)), before["objects"], before["canvas"]
    )  # all candidate rules coincide at width 150
    demo = {
        "canvases": [
            view("Before", boxes_of_scene(before)),
            view("Your demonstration", boxes_of_outputs(before, after)),
        ]
    }
    await sess.start({"scene": before, "after": after})
    live = Live(uuid.uuid4().hex[:12], sess, jsonable_encoder(demo))
    store[live.id] = live
    return _state(live)


@router.get("/{sid}")
async def get_state(request: Request, sid: str) -> dict:
    return _state(_get(request, sid))


@router.post("/{sid}/answer")
async def answer(request: Request, sid: str, body: AnswerIn) -> dict:
    live = _get(request, sid)
    async with live.lock:
        try:
            await live.session.answer(body.query_id, body.answer, body.candidate_set_hash)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
    return _state(live)


async def _ensure_binding(request: Request, live: Live, backend: str) -> None:
    reg = live.registry
    if reg.current(CONCEPT_ID, backend) is not None:
        return
    _, original = _opener(request, backend, None)
    mock = MockProvider({"binding": [fx.cands(fx.NAIVE), fx.cands(fx.NAIVE)]})
    r = await transfer_concept(
        live.concept,
        backend,
        mock,
        _ledger(),
        NativeBudget(),
        original,
        [card_scene(150), card_scene(60)],
        reg,
        backend,
        origin="fixture",
    )
    if r.status != "validated":
        raise HTTPException(
            422,
            f"the scripted native procedure could not realise your rule on {backend} ({r.status})",
        )


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
        await _ensure_binding(request, live, body.backend)
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
            "label": LABEL,
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
        "model_used": "none",
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
    pkg = {
        "label": LABEL,
        "concept": {
            "rule_text": live.concept.summary,
            "sealed_hash": live.concept.sealed_hash(),
            "intent_state": s.intent_state.value,
            "queries_asked": s.queries_asked,
        },
        "teaching_ledger": jsonable_encoder(
            [{"kind": e.kind, "source": e.source} for e in s.ledger.entries]
        ),
        "teaching_ledger_chain_verified": bool(s.ledger.verify_chain()),
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
            for k, v in live.registry.versions.items()
            for b in v
        ],
        "notes": [
            "Binding programs are scripted fixtures, not model-generated.",
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
        mock = MockProvider({"binding_repair": [fx.cands(fx.HARDCODED_OFFSET, fx.PROBING)]})
        r = await repair_binding(
            concept,
            "fabric",
            old,
            witness,
            mock,
            _ledger(),
            NativeBudget(),
            drifted,
            original,
            [card_scene(150)],
            card_scene(80),
            reg,
            "fabric",
            origin="fixture",
        )
        new = reg.current(CONCEPT_ID, "fabric")
        live.last_failure = None if r.status == "validated" else live.last_failure
        out = {
            "label": LABEL,
            "status": r.status,
            "attempts": [
                {
                    "candidate": a["candidate"],
                    "diagnosis": a.get("diagnosis", ""),
                    "failed_stage": a.get("failed_stage"),
                    "cases": a.get("cases", []),
                }
                for a in r.attempts
            ],
            "old_program": old.prog,
            "new_program": new.prog if new else None,
            "versions": [
                {
                    "version": b.version,
                    "parent": b.parent_version,
                    "program_hash": b.program_hash,
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
