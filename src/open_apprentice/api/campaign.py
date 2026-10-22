"""Campaign lane API (spec 7.5-7.7; plan 9C): learn the taught banner->story layout, run it on development banners, ask on
overflow, save per-language preferences. Every engine session a request opens is snapshotted (PNG + native state) and closed
before the response, and every result offered as applied has passed the independent verifier against its authored gold."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from open_apprentice.api.teach import _account, _engine, _rate_limit, _require_model_budget
from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.explain import explain, overflow_facts
from open_apprentice.campaign.model_procedures import write_procedure
from open_apprentice.campaign.roles import (
    apply_roles,
    check_role_mapping,
    propose_roles,
    role_candidates,
)
from open_apprentice.campaign.fixtures import FIXTURE_IDS, load_fixture
from open_apprentice.campaign.learn import Learned, learn_layout
from open_apprentice.campaign.preferences import PreferenceConflict, PreferenceStore, scope_key
from open_apprentice.campaign.run import CampaignRun, _hash, answer, close_run, start_run
from open_apprentice.evaluation.campaign_gold import GOLD_KEYS, load_gold
from open_apprentice.evaluation.campaign_procedure_check import check_procedure
from open_apprentice.evaluation.campaign_verifier import verify_story
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.storage.factory import store_from_env

router = APIRouter(prefix="/api/campaign", tags=["campaign"])
TTL_SECONDS = 30 * 60
MAX_WORKSPACES = 20
OWNER = "campaign-demo"
LOCALES = ("de", "en", "fr")
BROKEN = {"missing_role", "duplicate_role"}
MAX_RUNS = 20  # per workspace; the oldest run records are dropped
CHOICES = ("builtin_shrink_hero", "builtin_split_two_cards", "neither")
GOLD_OUTCOME = {
    "builtin_shrink_hero": "shrink",
    "builtin_split_two_cards": "split",
}  # gold files name outcomes briefly
_PNG_CACHE: dict[str, str] = {}  # fixture id -> rendered thumbnail, once per process
WORKSPACE_MODEL_LIMITS = Limits(
    tokens=30_000, calls=8
)  # per workspace; the server-wide demo cap applies on top


@dataclass
class Workspace:
    id: str
    learned: Learned
    prefs: PreferenceStore
    runs: dict[str, Any] = field(default_factory=dict)
    touched: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Nemotron use, metered like a Try-it-live session (teach._account / _require_model_budget read these fields)
    ledger: Ledger = field(default_factory=lambda: Ledger(WORKSPACE_MODEL_LIMITS))
    replay: bool = False
    counted_tokens: int = 0
    counted_usd: float = 0.0
    procedures: dict[str, tuple[list, str]] = field(
        default_factory=dict
    )  # backend -> accepted model procedure


def _workspaces(request: Request) -> dict[str, Workspace]:
    return request.app.state.campaign


def _ws(request: Request, wid: str) -> Workspace:
    spaces, now = _workspaces(request), time.time()
    for k in [k for k, v in spaces.items() if now - v.touched > TTL_SECONDS]:
        del spaces[
            k
        ]  # nothing to close: a workspace never holds an engine session between requests
    ws = spaces.get(wid)
    if ws is None:
        raise HTTPException(404, "unknown or expired workspace")
    ws.touched = now
    return ws


def _store(request: Request):
    if request.app.state.campaign_store is None:
        request.app.state.campaign_store = store_from_env()
    return request.app.state.campaign_store


def _harness(request: Request) -> EvaluatorHarness:
    url, token = _engine(request)
    return EvaluatorHarness(url, token)


def _open(harness: EvaluatorHarness, scene: dict, backend: str = "konva"):
    try:
        return harness.open_session(scene, OWNER, backend=backend)[0]
    except httpx.HTTPError as e:
        raise HTTPException(
            503, "the graphics engine is busy or unavailable; try again shortly"
        ) from e


BUSY = "the graphics engine is busy or unavailable; try again shortly"


def _render(harness: EvaluatorHarness, scene: dict) -> str:
    s = _open(harness, scene)
    try:
        return s.call("export_scene", format="png")["data_url"]
    except httpx.HTTPError as e:
        raise HTTPException(503, BUSY) from e
    finally:
        try:
            s.close()
        except httpx.HTTPError:
            pass  # the session is reaped by the engine's idle timeout


def _thumb(harness: EvaluatorHarness, fid: str) -> str:
    if fid not in _PNG_CACHE:
        _PNG_CACHE[fid] = _render(harness, load_fixture(fid)["scene"])
    return _PNG_CACHE[fid]


def _kind(fid: str) -> str:
    if fid.startswith("untagged_"):
        return "untagged"
    return "teaching" if fid == "teach_before" else "broken" if fid in BROKEN else "banner"


@router.get("/fixtures")
async def fixtures(request: Request) -> dict:
    harness = _harness(request)
    ids = [f for f in FIXTURE_IDS if f != "teach_after"]
    pngs = await asyncio.to_thread(lambda: [_thumb(harness, f) for f in ids])
    return {
        "fixtures": [
            {"id": f, "locale": load_fixture(f)["locale"], "kind": _kind(f), "png": png}
            for f, png in zip(ids, pngs)
        ]
    }


@router.post("/workspaces")
async def create_workspace(request: Request) -> dict:
    _rate_limit(request, "campaign")
    harness = _harness(request)
    before, after = load_fixture("teach_before")["scene"], load_fixture("teach_after")["scene"]
    # search only: the model path stays off in this lane (plan 9C); the search is CPU work, kept off the event loop
    learned = await asyncio.to_thread(asyncio.run, learn_layout(before, after))
    before_png, after_png = await asyncio.to_thread(
        lambda: (_thumb(harness, "teach_before"), _render(harness, after))
    )
    wid = uuid.uuid4().hex
    spaces = _workspaces(request)
    while len(spaces) >= MAX_WORKSPACES:
        del spaces[min(spaces, key=lambda k: spaces[k].touched)]
    spaces[wid] = Workspace(wid, learned, PreferenceStore(_store(request), namespace=wid))
    return {
        "workspace_id": wid,
        "learned": {
            "origin": learned.origin,
            "candidates": [
                {"origin": c.origin, "reproduces": c.reproduces, "reason": c.reason}
                for c in learned.candidates
            ],
        },
        "teaching": {"before_png": before_png, "after_png": after_png},
    }


def _scope_out(prefs: PreferenceStore, locale: str) -> dict:
    scope = scope_key(locale)
    active = prefs.get(scope)
    return {
        "scope": scope,
        "locale": locale,
        "active": (
            None if active is None else {"outcome": active.outcome, "version": active.version}
        ),
        "history": [
            {"version": p.version, "outcome": p.outcome, "parent": p.parent}
            for p in prefs.history(scope)
        ],
    }


@router.get("/workspaces/{wid}/preferences")
async def preferences(request: Request, wid: str) -> dict:
    ws = _ws(request, wid)
    return {
        "scopes": await asyncio.to_thread(lambda: [_scope_out(ws.prefs, loc) for loc in LOCALES])
    }


class RunIn(BaseModel):
    fixture_id: str = Field(min_length=1, max_length=40)
    backend: Literal["konva", "fabric"] = "konva"
    roles: dict[str, str] | None = Field(
        default=None, max_length=20
    )  # owner-confirmed roles for an untagged banner


class FixtureIn(BaseModel):
    fixture_id: str = Field(min_length=1, max_length=40)


class BackendIn(BaseModel):
    backend: Literal["konva", "fabric"]


class AnswerIn(BaseModel):
    choice: str = Field(min_length=1, max_length=40)
    expected_version: int | None = Field(default=None, ge=1, le=10_000)


class RollbackIn(BaseModel):
    locale: str = Field(min_length=2, max_length=2)
    to_version: int = Field(ge=1, le=10_000)
    expected_version: int = Field(ge=1, le=10_000)


@dataclass
class RunRecord:
    run: CampaignRun
    fixture_id: str
    backend: str
    source: dict  # the scene the run used (an untagged banner with the owner's roles applied)
    snapshots: dict[
        str, dict
    ]  # session id -> {png, native}; the sessions themselves are already closed


def _gold(fid: str, outcome: str) -> dict | None:
    if (fid, outcome) not in GOLD_KEYS:
        return None
    gold = load_gold(fid, outcome)
    return None if gold is None else gold["scene"]


def _verify(fid: str, outcome: str, native: dict, source: dict) -> dict:
    """`outcome` is "layout" or a built-in name. An untagged banner is judged against the gold of the banner it was
    derived from (same layers, same ids)."""
    gold_fid = fid.removeprefix("untagged_")
    report = verify_story(source, native, _gold(gold_fid, GOLD_OUTCOME.get(outcome, outcome)))
    return {
        "passed": report.passed,
        "failed": report.failed(),
        "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in report.checks],
    }


def _banner(fid: str) -> dict:
    if fid not in FIXTURE_IDS or fid == "teach_after":
        raise HTTPException(404, "unknown banner")
    return load_fixture(fid)


def _run_out(rec: RunRecord, status: str | None = None, verification: dict | None = None) -> dict:
    run = rec.run
    snap = rec.snapshots.get(run.result_session or "")
    result = None
    if snap is not None and run.status in ("ready", "applied"):
        result = {"png": snap["png"], "verification": verification}
    return {
        "run_id": run.run_id,
        "fixture_id": rec.fixture_id,
        "backend": rec.backend,
        "locale": run.locale,
        "status": status or run.status,
        "problems": run.problems,
        "provenance": {k: v for k, v in run.provenance.items() if k != "previews"},
        "result": result,
        "previews": [
            {
                "outcome": p.outcome,
                "origin": p.origin,
                "fits": p.fits,
                "violations": p.violations,
                "png": rec.snapshots[p.session_id]["png"],
            }
            for p in (run.previews.values() if run.status == "question" else [])
        ],
        "preference": (
            None
            if run.preference is None
            else {"outcome": run.preference.outcome, "version": run.preference.version}
        ),
    }


def _gate(rec: RunRecord) -> dict:
    """Verifier gate for a committed run: a failure is reported as `blocked`, never as applied."""
    run = rec.run
    outcome = "layout" if run.status == "ready" else run.preference.outcome
    verification = _verify(
        rec.fixture_id, outcome, rec.snapshots[run.result_session]["native"], rec.source
    )
    return _run_out(rec, None if verification["passed"] else "blocked", verification)


@router.post("/workspaces/{wid}/runs")
async def start(request: Request, wid: str, body: RunIn) -> dict:
    _rate_limit(request, "campaign")
    ws = _ws(request, wid)
    fixture = _banner(body.fixture_id)
    source = fixture["scene"]
    roles_origin = "authored"
    if body.fixture_id.startswith("untagged_"):
        if not body.roles:
            raise HTTPException(
                422, "this banner has no roles yet: propose roles and confirm them first"
            )
        problems = check_role_mapping(source, "banner", body.roles)
        if problems:
            raise HTTPException(422, f"the confirmed roles are not usable: {'; '.join(problems)}")
        source, roles_origin = apply_roles(source, "banner", body.roles), "owner"
    harness = _harness(request)
    busy: list[str] = []
    keep: list[RunRecord] = []

    def open_session(scene: dict):
        try:
            return _open(harness, scene, body.backend)
        except HTTPException as e:
            busy.append(e.detail)
            raise

    def attempt(procedure) -> dict:
        run = start_run(source, fixture["locale"], ws.learned, open_session, ws.prefs, procedure)
        run.provenance["roles_origin"] = roles_origin
        try:
            snapshots = {
                sid: {
                    "png": sess.call("export_scene", format="png")["data_url"],
                    "native": harness.native(sid, OWNER),
                }
                for sid, sess in run.sessions.items()
            }
        except httpx.HTTPError:
            busy.append(BUSY)
            return {}
        finally:
            close_run(run)  # best effort: no session outlives the request
        if busy or run.engine_error:
            return {}
        rec = RunRecord(run, body.fixture_id, body.backend, source, snapshots)
        keep.append(rec)
        while len(ws.runs) >= MAX_RUNS:
            del ws.runs[next(iter(ws.runs))]
        ws.runs[run.run_id] = rec
        return _gate(rec) if run.status in ("ready", "applied") else _run_out(rec)

    def work() -> dict:
        procedure = ws.procedures.get(body.backend)
        out = attempt(procedure)
        if procedure and out and out["status"] in ("failed", "blocked"):
            # an accepted model procedure was checked on three banners only: on any other it must never cost the result
            status = out["status"]
            keep.clear()
            out = attempt(None)
            if out:
                out["provenance"][
                    "procedure_fallback"
                ] = f"Nemotron's procedure {status} on this banner; the reference procedure was used"
        return out

    async with ws.lock:
        out = await asyncio.to_thread(work)
        if not out:
            raise HTTPException(503, busy[0] if busy else BUSY)
        if out["status"] == "question":
            provider, note = _model(request, ws)
            try:
                e = await explain(provider, ws.ledger, overflow_facts(keep[-1].run, source))
            finally:
                _account(request, ws)
            out["explanation"] = {"text": e.text, "origin": e.origin, "problems": e.problems + note}
    return out


@router.post("/workspaces/{wid}/runs/{rid}/answer")
async def answer_run(request: Request, wid: str, rid: str, body: AnswerIn) -> dict:
    ws = _ws(request, wid)
    if body.choice not in CHOICES:
        raise HTTPException(422, f"choice must be one of {list(CHOICES)}")

    def work() -> dict:
        rec = ws.runs.get(rid)
        if rec is None:
            raise HTTPException(404, "unknown or expired run")
        run = rec.run
        if run.status != "question":
            raise HTTPException(409, f"this run is {run.status}, not waiting for an answer")
        preview = run.previews.get(body.choice)
        if preview is not None and preview.fits:  # verify before anything is applied or saved
            snap = rec.snapshots[preview.session_id]
            verification = _verify(rec.fixture_id, body.choice, snap["native"], rec.source)
            if not verification["passed"]:
                out = _run_out(rec, "blocked")
                out["result"] = {"png": snap["png"], "verification": verification}
                return out
        # A guard for when banners can change: today the fixture is fixed, so this always matches.
        current = _hash(rec.source)
        try:
            answer(run, body.choice, ws.prefs, body.expected_version, current_source_hash=current)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        except PreferenceConflict as e:
            raise HTTPException(409, f"the saved preference changed: {e}") from e
        return _run_out(rec) if run.status == "unchanged" else _gate(rec)

    async with ws.lock:
        return await asyncio.to_thread(work)


@router.post("/workspaces/{wid}/preferences/rollback")
async def rollback(request: Request, wid: str, body: RollbackIn) -> dict:
    ws = _ws(request, wid)
    if body.locale not in LOCALES:
        raise HTTPException(404, "unknown locale")

    def work() -> dict:
        try:
            ws.prefs.rollback(scope_key(body.locale), body.to_version, body.expected_version)
        except PreferenceConflict as e:
            raise HTTPException(409, str(e)) from e
        except KeyError as e:
            raise HTTPException(404, "no such version") from e
        return _scope_out(ws.prefs, body.locale)

    async with ws.lock:
        return await asyncio.to_thread(work)


MODEL_REQUESTS_PER_HOUR = (
    6  # per address: model use is scarce on the public demo (Try-it-live allows 3 sessions/hour)
)


def _model_quota(request: Request) -> bool:
    client = request.client.host if request.client else "unknown"
    now, hits = time.time(), request.app.state.rate.setdefault((client, "campaign_model"), [])
    hits[:] = [t for t in hits if now - t < 3600]
    if len(hits) >= MODEL_REQUESTS_PER_HOUR:
        return False
    hits.append(now)
    return True


def _model(request: Request, ws: Workspace):
    """(provider, notes): the server's Nemotron provider when model mode is on, this address has model requests left and
    the demo budget allows it; otherwise (None, why) and the caller uses its baseline."""
    provider = getattr(request.app.state, "provider", None)
    if provider is None:
        return None, []
    try:
        _require_model_budget(
            request, None if ws.counted_usd == 0 else ws
        )  # a workspace's first use needs a full reserve
    except HTTPException as e:
        return None, [str(e.detail)]
    if not _model_quota(request):
        return None, [
            f"Nemotron is limited to {MODEL_REQUESTS_PER_HOUR} requests per hour per address on this demo; the fallback is shown"
        ]
    return provider, []


@router.post("/workspaces/{wid}/roles")
async def roles(request: Request, wid: str, body: FixtureIn) -> dict:
    _rate_limit(request, "campaign")
    ws = _ws(request, wid)
    scene = _banner(body.fixture_id)["scene"]
    async with ws.lock:
        provider, note = _model(request, ws)
        try:
            p = await propose_roles(provider, ws.ledger, scene, "banner")
        finally:
            _account(request, ws)
    return {
        "mapping": p.mapping,
        "origin": p.origin,
        "problems": p.problems + note,
        "candidates": role_candidates(scene, "banner"),
        "model": "on" if getattr(request.app.state, "provider", None) is not None else "off",
    }


@router.post("/workspaces/{wid}/procedures")
async def procedures(request: Request, wid: str, body: BackendIn) -> dict:
    _rate_limit(request, "campaign")
    ws = _ws(request, wid)
    url, token = _engine(request)
    model_on = getattr(request.app.state, "provider", None) is not None
    cache = request.app.state.campaign_procedures
    async with ws.lock:
        if (
            body.backend in cache
        ):  # the task is the same for every visitor: an accepted procedure is reused, not re-bought
            ws.procedures[body.backend] = (cache[body.backend], "model")
            return {
                "backend": body.backend,
                "origin": "model",
                "accepted": True,
                "cached": True,
                "attempts": [],
                "notes": [],
                "model": "on" if model_on else "off",
            }
        provider, note = _model(request, ws)
        try:
            out = await write_procedure(
                provider,
                ws.ledger,
                body.backend,
                lambda prog: check_procedure(prog, body.backend, url, token),
            )
        finally:
            _account(request, ws)
        if out.origin == "model":
            ws.procedures[body.backend] = (out.program, "model")
            cache[body.backend] = out.program
    return {
        "backend": body.backend,
        "origin": out.origin,
        "accepted": out.origin == "model",
        "cached": False,
        "attempts": out.attempts,
        "notes": note,
        "model": "on" if model_on else "off",
    }
