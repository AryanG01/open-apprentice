"""/api/v2 routes (spec 8). Thin: identify the owner, call the service layer, map its exceptions to HTTP."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from open_apprentice.api.v2 import identity, records, service
from open_apprentice.api.v2.context import V2
from open_apprentice.drawio.parse import MAX_UPLOAD, DrawioRefused

router = APIRouter(prefix="/api/v2")


def _v2(request: Request) -> V2:
    return request.app.state.v2


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
