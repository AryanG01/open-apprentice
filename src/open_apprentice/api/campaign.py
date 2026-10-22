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

from open_apprentice.api.teach import _engine, _rate_limit
from open_apprentice.campaign.fixtures import FIXTURE_IDS, load_fixture
from open_apprentice.campaign.learn import Learned, learn_layout
from open_apprentice.campaign.preferences import PreferenceConflict, PreferenceStore, scope_key
from open_apprentice.campaign.run import CampaignRun, _hash, answer, close_run, start_run
from open_apprentice.evaluation.campaign_gold import GOLD_KEYS, load_gold
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


@dataclass
class Workspace:
    id: str
    learned: Learned
    prefs: PreferenceStore
    runs: dict[str, Any] = field(default_factory=dict)
    touched: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


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
    snapshots: dict[
        str, dict
    ]  # session id -> {png, native}; the sessions themselves are already closed


def _gold(fid: str, outcome: str) -> dict | None:
    if (fid, outcome) not in GOLD_KEYS:
        return None
    gold = load_gold(fid, outcome)
    return None if gold is None else gold["scene"]


def _verify(fid: str, outcome: str, native: dict) -> dict:
    """`outcome` is "layout" or a built-in name."""
    report = verify_story(
        load_fixture(fid)["scene"], native, _gold(fid, GOLD_OUTCOME.get(outcome, outcome))
    )
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
    verification = _verify(rec.fixture_id, outcome, rec.snapshots[run.result_session]["native"])
    return _run_out(rec, None if verification["passed"] else "blocked", verification)


@router.post("/workspaces/{wid}/runs")
async def start(request: Request, wid: str, body: RunIn) -> dict:
    _rate_limit(request, "campaign")
    ws = _ws(request, wid)
    fixture = _banner(body.fixture_id)
    harness = _harness(request)
    busy: list[str] = []

    def open_session(scene: dict):
        try:
            return _open(harness, scene, body.backend)
        except HTTPException as e:
            busy.append(e.detail)
            raise

    def work() -> dict:
        run = start_run(fixture["scene"], fixture["locale"], ws.learned, open_session, ws.prefs)
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
        rec = RunRecord(run, body.fixture_id, body.backend, snapshots)
        while len(ws.runs) >= MAX_RUNS:
            del ws.runs[next(iter(ws.runs))]
        ws.runs[run.run_id] = rec
        return _gate(rec) if run.status in ("ready", "applied") else _run_out(rec)

    async with ws.lock:
        out = await asyncio.to_thread(work)
    if not out:
        raise HTTPException(503, busy[0] if busy else BUSY)
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
            verification = _verify(rec.fixture_id, body.choice, snap["native"])
            if not verification["passed"]:
                out = _run_out(rec, "blocked")
                out["result"] = {"png": snap["png"], "verification": verification}
                return out
        # A guard for when banners can change: today the fixture is fixed, so this always matches.
        current = _hash(load_fixture(rec.fixture_id)["scene"])
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
