"""Sketch door: Nemotron VL reads a rough wireframe into layers. The response is the upload response, so the banner door's
editor and `/uploads/{uid}/confirm` are reused unchanged (docs/superpowers/specs/2026-10-26-sketch-to-banner-design.md)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from open_apprentice.api.campaign import (
    MAX_UPLOADS,
    UPLOAD_H,
    UPLOAD_W,
    UploadIn,
    _account,
    _rate_limit,
    _vision,
    _ws,
)
from open_apprentice.campaign.imageinfo import ImageError, image_size
from open_apprentice.campaign.sketch import propose_sketch_layers

router = APIRouter(prefix="/api/campaign", tags=["campaign"])


@router.post("/workspaces/{wid}/sketches")
async def upload_sketch(request: Request, wid: str, body: UploadIn) -> dict:
    """Nemotron VL reads the owner's wireframe and proposes layers (words usually empty). Checked, returned with its
    problems; only the owner's confirmed layers ever become a banner."""
    _rate_limit(request, "campaign")
    ws = _ws(request, wid)
    try:
        _, w, h = image_size(body.image)
    except ImageError as e:
        raise HTTPException(422, str(e)) from e
    if (w, h) != (UPLOAD_W, UPLOAD_H):
        raise HTTPException(
            422, f"the sketch must be {UPLOAD_W} x {UPLOAD_H} pixels (16:9); this one is {w} x {h}"
        )
    async with ws.lock:
        if len(ws.uploads) + len(ws.banners) >= MAX_UPLOADS:
            raise HTTPException(
                409, f"a workspace holds {MAX_UPLOADS} banners at most; start a new one"
            )
        provider, note = _vision(request, ws)
        try:
            proposal = await propose_sketch_layers(provider, ws.ledger, body.image)
        finally:
            _account(request, ws)
        if provider is None:
            proposal.note = note
        uid = uuid.uuid4().hex[:12]
        ws.uploads[uid] = {"image": body.image, "kind": "sketch"}
    return {
        "upload_id": uid,
        "origin": proposal.origin,
        "language": proposal.language,
        "layers": [ly.model_dump() for ly in proposal.layers],
        "problems": proposal.problems,
        "note": proposal.note,
        "model": (
            getattr(provider, "requested_model", "")
            if provider and proposal.origin == "model"
            else ""
        ),
    }
