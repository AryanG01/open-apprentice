"""HTTP API (spec 16). Liveness, readiness and the interactive teaching demo (no model, no paid calls)."""

from __future__ import annotations

import datetime
import os
import pathlib
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from open_apprentice import __version__
from open_apprentice.api.svg import router as svg_router
from open_apprentice.api.teach import replay_router, router as teach_router
from open_apprentice.config import load_settings
from open_apprentice.providers.factory import MissingCredential, make_provider
from open_apprentice.providers.replay import RecordingProvider, load_tape
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.local_engine import local_engine

ROOT = pathlib.Path(__file__).resolve().parents[3]
TAPE_PATH = pathlib.Path(
    os.environ.get("DEMO_REPLAY_TAPE", ROOT / "docs" / "replay" / "nemotron_tape.json")
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Engine: ENGINE_URL + EVALUATOR_TOKEN when deployed (compose); otherwise start a local one for development."""
    app.state.live = {}
    app.state.engine = None
    app.state.engine_error = None
    app.state.spend = {"usd": 0.0, "tokens": 0}
    app.state.rate = {}
    app.state.provider = None
    app.state.model_error = None
    async with AsyncExitStack() as stack:
        # Model mode costs real money, so it is OFF unless the operator opts in with DEMO_MODEL_ENABLED=1 (and has credentials).
        if os.environ.get("DEMO_MODEL_ENABLED") == "1":
            try:
                app.state.provider = make_provider(load_settings())
                stack.push_async_callback(app.state.provider.aclose)
            except MissingCredential as e:
                app.state.model_error = str(e)[:160]
            record = os.environ.get("DEMO_RECORD_TAPE")
            if (
                record and app.state.provider is not None
            ):  # one-off: capture a real session for replay
                p = app.state.provider
                app.state.provider = RecordingProvider(
                    p,
                    pathlib.Path(record),
                    {"model": p.requested_model, "recorded_at": datetime.date.today().isoformat()},
                )
        app.state.tape = None
        if TAPE_PATH.is_file():
            app.state.tape = load_tape(TAPE_PATH)
        app.state.pool = stack.enter_context(SolverPool())
        app.state.pool.start()  # pay the solver start-up once, before any visitor is waiting
        url, token = os.environ.get("ENGINE_URL"), os.environ.get("EVALUATOR_TOKEN")
        if url and token:
            app.state.engine = (url, token)
        elif os.environ.get("OA_NO_LOCAL_ENGINE") != "1":
            try:
                app.state.engine = stack.enter_context(local_engine(str(ROOT)))
            except Exception as e:  # noqa: BLE001 - report, don't crash the API
                app.state.engine_error = str(e)[:200]
        yield


app = FastAPI(title="Open Apprentice", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def security_headers(request, call_next):
    """Basic hardening for a public deployment: no sniffing, no framing, no referrer leakage, same-origin resources only."""
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
    )
    return resp


app.include_router(teach_router)
app.include_router(replay_router)
app.include_router(svg_router)


@app.get("/health/live")
def live() -> dict[str, str]:
    """Process liveness. No secrets, no paid inference."""
    return {"status": "ok", "provider_mode": load_settings().provider_mode, "version": __version__}


@app.get("/health/ready")
def ready() -> dict:
    """Readiness: can this server actually run the interactive demo?"""
    from open_apprentice.api.teach import RESERVE_USD, _cap_usd

    p = app.state.provider
    engine_ok, engine_error = app.state.engine is not None, app.state.engine_error
    if app.state.engine is not None:
        try:  # a configured engine whose browser crashed must not be reported ready
            engine_ok = (
                httpx.get(f"{app.state.engine[0]}/health/live", timeout=2.0).status_code == 200
            )
        except httpx.HTTPError:
            engine_ok = False
        if not engine_ok:
            engine_error = "the graphics engine is not responding (its browser may have crashed); restart the server"
    return {
        "engine": engine_ok,
        "engine_error": engine_error,
        "live_sessions": len(app.state.live),
        "replay": {
            "available": app.state.tape is not None,
            "recorded_at": (app.state.tape or {}).get("recorded_at"),
            "id": (app.state.tape or {}).get("model", ""),
        },
        "model": {
            "available": p is not None,
            # would a NEW live model session be admitted right now (cap headroom for its worst case)?
            "can_start": p is not None and app.state.spend["usd"] + RESERVE_USD <= _cap_usd(),
            "id": getattr(p, "requested_model", "") if p else "",
            "spend_usd": round(app.state.spend["usd"], 4),
            "cap_usd": _cap_usd(),
            "error": app.state.model_error,
        },
    }


# One-process demo: if the web app has been built (npm run build -w apps/web) the API serves it at "/", after every API route.
_WEB = ROOT / "apps" / "web" / "dist"
if _WEB.is_dir():
    app.mount("/", StaticFiles(directory=_WEB, html=True), name="web")
