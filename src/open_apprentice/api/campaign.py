"""Campaign lane API (spec 7.5-7.7; plan 9C): learn the taught banner->story layout, run it on development banners, ask on
overflow, save per-language preferences. Every engine session a request opens is snapshotted (PNG + native state) and closed
before the response, and every result offered as applied has passed the independent verifier against its authored gold."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from open_apprentice.api.teach import _engine, _rate_limit
from open_apprentice.campaign.fixtures import FIXTURE_IDS, load_fixture
from open_apprentice.campaign.learn import Learned, learn_layout
from open_apprentice.campaign.preferences import PreferenceStore, scope_key
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.storage.factory import store_from_env

router = APIRouter(prefix="/api/campaign", tags=["campaign"])
TTL_SECONDS = 30 * 60
MAX_WORKSPACES = 20
OWNER = "campaign-demo"
LOCALES = ("de", "en", "fr")
BROKEN = {"missing_role", "duplicate_role"}
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


def _open(harness: EvaluatorHarness, scene: dict):
    try:
        return harness.open_session(scene, OWNER)[0]
    except httpx.HTTPError as e:
        raise HTTPException(
            503, "the graphics engine is busy or unavailable; try again shortly"
        ) from e


def _render(harness: EvaluatorHarness, scene: dict) -> str:
    s = _open(harness, scene)
    try:
        return s.call("export_scene", format="png")["data_url"]
    finally:
        s.close()


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
    learned = await learn_layout(
        before, after
    )  # search only: the model path stays off in this lane (plan 9C)
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
    return {"scopes": [_scope_out(ws.prefs, loc) for loc in LOCALES]}
