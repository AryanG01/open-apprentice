"""/api/v2 routes (spec 8). Thin: identify the owner, call the service layer, map its exceptions to HTTP."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

import threading

from open_apprentice.api.v2 import identity, records, service, tasks
from open_apprentice.api.v2.context import V2
from open_apprentice.drawio.parse import MAX_UPLOAD, DrawioRefused

router = APIRouter(prefix="/api/v2")
router_internal = APIRouter()


class V2Unavailable(Exception):
    pass


class RateLimited(Exception):
    pass


JSON_LIMIT = 256 * 1024


class BodyLimit:
    """ASGI middleware: /api/v2 request bodies are capped (2 MB uploads, 256 KB JSON) without ever buffering more than the
    cap, whether or not the client sends Content-Length."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if (
            scope["type"] != "http"
            or not scope["path"].startswith("/api/v2/")
            or scope["method"] != "POST"
        ):
            return await self.app(scope, receive, send)
        limit = MAX_UPLOAD if scope["path"] == "/api/v2/documents" else JSON_LIMIT
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            return await _too_large(send, limit)
        body, more = b"", True
        while more:
            msg = await receive()
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
            if len(body) > limit:
                return await _too_large(send, limit)
        sent = False

        async def replay() -> dict:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


async def _too_large(send: Any, limit: int) -> None:
    import json

    payload = json.dumps(
        {"error": {"code": "TOO_LARGE", "message": f"the request body exceeds {limit} bytes"}}
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": payload})


def _v2(request: Request) -> V2:
    v = getattr(request.app.state, "v2", None)
    if v is None:
        raise V2Unavailable(
            getattr(request.app.state, "v2_error", None) or "the v2 service is not configured"
        )
    return v


def owner(request: Request, response: Response) -> str:
    v = _v2(request)
    who = identity.verify(request.cookies.get(identity.COOKIE), v.secret)
    if who is None:
        who = identity.new_owner()
        response.set_cookie(
            identity.COOKIE,
            identity.sign(who, v.secret),
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
            max_age=30 * 24 * 3600,
        )
    return who


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message[:300]}}, status_code=status)


def install(app: FastAPI) -> None:
    """Add the router and its error mapping to an app (the real app, or a bare one in tests)."""
    app.include_router(router)
    app.include_router(router_internal)
    app.add_middleware(BodyLimit)

    @app.exception_handler(RateLimited)
    async def _rate(_: Request, e: RateLimited) -> JSONResponse:
        return _error(429, "RATE_LIMITED", str(e))

    @app.exception_handler(V2Unavailable)
    async def _unavail(_: Request, e: V2Unavailable) -> JSONResponse:
        return _error(503, "V2_UNAVAILABLE", f"this part of the service is unavailable: {e}")

    @app.exception_handler(records.NotFound)
    async def _nf(_: Request, e: records.NotFound) -> JSONResponse:
        return _error(404, "NOT_FOUND", "not found")

    @app.exception_handler(DrawioRefused)
    async def _ref(_: Request, e: DrawioRefused) -> JSONResponse:
        return _error(422, "REFUSED", str(e))

    @app.exception_handler(service.Conflict)
    async def _conf(_: Request, e: service.Conflict) -> JSONResponse:
        return _error(409, e.code, str(e))

    @app.exception_handler(records.IdempotencyConflict)
    async def _idem(_: Request, e: records.IdempotencyConflict) -> JSONResponse:
        return _error(409, "IDEMPOTENCY_CONFLICT", str(e))


# ---- documents ---------------------------------------------------------------------------------------------------------


@router.post("/documents", status_code=201)
async def post_document(
    request: Request, name: str = "document.drawio", who: str = Depends(owner)
) -> dict:
    raw = await request.body()
    if len(raw) > MAX_UPLOAD:
        raise DrawioRefused(f"the file is {len(raw)} bytes; the limit is 2 MB")
    return service.import_document(_v2(request), who, name, raw)


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, request: Request, who: str = Depends(owner)) -> dict:
    return service.get_document(_v2(request), who, doc_id)


@router.get("/documents/{doc_id}/pages/{page_id}/preview.png")
def get_preview(doc_id: str, page_id: str, request: Request, who: str = Depends(owner)) -> Response:
    return Response(service.preview_png(_v2(request), who, doc_id, page_id), media_type="image/png")


@router.get("/documents/{doc_id}/pages/{page_id}/scene")
def get_scene(
    doc_id: str, page_id: str, request: Request, mapping_hash: str = "", who: str = Depends(owner)
) -> dict:
    return service.page_scene_view(_v2(request), who, doc_id, page_id, mapping_hash)


def _field(body: dict, key: str, kind: type, default: Any = None) -> Any:
    v = body.get(key, default)
    if not isinstance(v, kind):
        raise service.Conflict("BAD_REQUEST", f"'{key}' must be a {kind.__name__}")
    return v


@router.post("/documents/{doc_id}/mapping")
def post_mapping(
    doc_id: str, request: Request, body: dict = Body(default={}), who: str = Depends(owner)
) -> dict:
    v = _v2(request)
    service.get_document(v, who, doc_id)  # ownership before body validation
    return service.save_mapping(
        v,
        who,
        doc_id,
        _field(body, "page_id", str),
        _field(body, "labels", dict, {}),
        bool(body.get("confirm", False)),
    )


@router.post("/documents/{doc_id}/draft")
def post_draft(
    doc_id: str, request: Request, body: dict = Body(default={}), who: str = Depends(owner)
) -> dict:
    v = _v2(request)
    service.get_document(v, who, doc_id)
    return service.draft_render(
        v,
        who,
        doc_id,
        _field(body, "page_id", str),
        _field(body, "mapping_hash", str),
        _field(body, "boxes", dict, {}),
    )


# ---- sessions ------------------------------------------------------------------------------------------------------------


@router.post("/sessions", status_code=202)
def post_session(
    request: Request, body: dict = Body(default={}), who: str = Depends(owner)
) -> dict:
    v = _v2(request)
    if body.get("live") and not v.live_limiter.allow(
        request.client.host if request.client else "?"
    ):
        raise RateLimited(
            "too many live sessions from this address; try again later or use the offline learner"
        )
    return service.create_session(
        _v2(request),
        who,
        _field(body, "documents", list),
        _field(body, "demonstrations", list),
        bool(body.get("live", False)),
        _field(body, "idempotency_key", str),
    )


@router.get("/sessions/{sid}")
def get_session(sid: str, request: Request, who: str = Depends(owner)) -> dict:
    return service.session_state(_v2(request), who, sid)


@router.post("/sessions/{sid}/responses")
def post_response(
    sid: str, request: Request, body: dict = Body(default={}), who: str = Depends(owner)
) -> dict:
    return service.submit_answer(_v2(request), who, sid, body)


@router.post("/sessions/{sid}/cancel")
def post_cancel(sid: str, request: Request, who: str = Depends(owner)) -> dict:
    return service.cancel_session(_v2(request), who, sid)


# ---- runs and export -----------------------------------------------------------------------------------------------------


@router.post("/skills/{skill_id}/versions/{version}/apply", status_code=202)
def post_apply(
    skill_id: str,
    version: int,
    request: Request,
    body: dict = Body(default={}),
    who: str = Depends(owner),
) -> dict:
    v = _v2(request)
    service._skill_owner(v, who, skill_id)
    return service.apply_version(
        v,
        who,
        skill_id,
        version,
        _field(body, "documents", list),
        _field(body, "idempotency_key", str),
    )


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request, who: str = Depends(owner)) -> dict:
    return service.get_run(_v2(request), who, run_id)


@router.post("/runs/{run_id}/cancel")
def post_run_cancel(run_id: str, request: Request, who: str = Depends(owner)) -> dict:
    return service.cancel_run(_v2(request), who, run_id)


@router.get("/runs/{run_id}/export")
def get_export(
    run_id: str, request: Request, doc_id: str = "", page_id: str = "", format: str = "drawio",
    who: str = Depends(owner),
) -> Response:  # fmt: skip
    data, media = service.export(_v2(request), who, run_id, doc_id, page_id, format)
    name = f"{doc_id[:8]}-{page_id}.{ {'drawio': 'drawio', 'svg': 'svg', 'receipt': 'json'}.get(format, 'bin') }"
    return Response(
        data, media_type=media, headers={"content-disposition": f'attachment; filename="{name}"'}
    )


# ---- skills, corrections, activation -------------------------------------------------------------------------------------


@router.get("/skills/{skill_id}")
def get_skill(skill_id: str, request: Request, who: str = Depends(owner)) -> dict:
    return service.skill_status(_v2(request), who, skill_id)


@router.post("/skills/{skill_id}/corrections", status_code=202)
def post_correction(
    skill_id: str, request: Request, body: dict = Body(default={}), who: str = Depends(owner)
) -> dict:
    v = _v2(request)
    service._skill_owner(v, who, skill_id)
    _field(body, "idempotency_key", str)
    return service.start_correction_session(v, who, skill_id, body)


@router.post("/skills/{skill_id}/activate")
def post_activate(
    skill_id: str, request: Request, body: dict = Body(default={}), who: str = Depends(owner)
) -> dict:
    v = _v2(request)
    service._skill_owner(v, who, skill_id)
    gen = body.get("expected_generation")
    if gen is not None and not isinstance(gen, int):
        raise service.Conflict("BAD_REQUEST", "'expected_generation' must be an integer or null")
    return service.activate(
        v, who, skill_id, _field(body, "version", int), gen, _field(body, "idempotency_key", str)
    )


# ---- question items and config -------------------------------------------------------------------------------------------


@router.get("/sessions/{sid}/requests/{request_id}/items/{item_id}.png")
def get_item_png(
    sid: str, request_id: str, item_id: str, request: Request, who: str = Depends(owner)
) -> Response:
    return Response(
        service.item_png(_v2(request), who, sid, request_id, item_id), media_type="image/png"
    )


@router.get("/config")
def get_config(request: Request) -> dict:
    return service.config(_v2(request))


# ---- Cloud Tasks delivery -----------------------------------------------------------------------------------------------

_task_locks: dict[str, threading.Lock] = {}
_task_locks_guard = threading.Lock()


def _key_lock(key: str) -> threading.Lock:
    with _task_locks_guard:
        return _task_locks.setdefault(key, threading.Lock())


@router_internal.post("/internal/tasks/{task_id}")
def post_internal_task(
    task_id: str, request: Request, body: dict = Body(default={})
) -> JSONResponse:
    v = getattr(request.app.state, "v2", None)
    auth = getattr(v, "internal_tasks", None)
    if v is None or auth is None:
        return _error(404, "NOT_FOUND", "not found")
    try:
        auth.verify(request.headers.get("authorization"))
    except tasks.Forbidden as e:
        return _error(403, "FORBIDDEN", str(e))
    if not task_id.isalnum() or len(task_id) > 64:
        return _error(400, "BAD_REQUEST", "bad task id")
    key = f"tasks/{task_id}.json"
    try:
        job = tasks.job_from_json(body)
    except ValueError as e:
        return _error(400, "BAD_REQUEST", str(e))
    if not v.store.create(key, records.dumps({"state": "running"})):
        return JSONResponse(_task_state(v, key))  # duplicate delivery: report, never re-run
    with _key_lock(job.key):
        try:
            service.run_job(v, job)
            state: dict = {"state": "done"}
        except (
            Exception
        ) as e:  # recorded, so Cloud Tasks does not retry a job whose failure is known
            state = {"state": "failed", "reason": f"{type(e).__name__}: {e}"[:300]}
    b = v.store.get(key)
    v.store.put(key, records.dumps(state), if_generation=b.generation if b else None)
    return JSONResponse(state)


def _task_state(v: V2, key: str) -> dict:
    import json
    import time

    for _ in range(
        600
    ):  # a concurrent first delivery is still running: wait for its outcome (≤ 60 s)
        b = v.store.get(key)
        d = json.loads(b.data) if b else {"state": "unknown"}
        if d.get("state") != "running":
            return d
        time.sleep(0.1)
    return {"state": "running"}
