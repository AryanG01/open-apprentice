"""HTTP API (spec 16). Liveness, readiness and the interactive teaching demo (no model, no paid calls)."""

from __future__ import annotations

import os
import pathlib
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from open_apprentice import __version__
from open_apprentice.api.teach import router as teach_router
from open_apprentice.config import load_settings
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.local_engine import local_engine

ROOT = pathlib.Path(__file__).resolve().parents[3]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Engine: ENGINE_URL + EVALUATOR_TOKEN when deployed (compose); otherwise start a local one for development."""
    app.state.live = {}
    app.state.engine = None
    app.state.engine_error = None
    async with AsyncExitStack() as stack:
        app.state.pool = stack.enter_context(SolverPool())
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
app.include_router(teach_router)


@app.get("/health/live")
def live() -> dict[str, str]:
    """Process liveness. No secrets, no paid inference."""
    return {"status": "ok", "provider_mode": load_settings().provider_mode, "version": __version__}


@app.get("/health/ready")
def ready() -> dict:
    """Readiness: can this server actually run the interactive demo?"""
    return {
        "engine": app.state.engine is not None,
        "engine_error": app.state.engine_error,
        "live_sessions": len(app.state.live),
    }


# One-process demo: if the web app has been built (npm run build -w apps/web) the API serves it at "/", after every API route.
_WEB = ROOT / "apps" / "web" / "dist"
if _WEB.is_dir():
    app.mount("/", StaticFiles(directory=_WEB, html=True), name="web")
