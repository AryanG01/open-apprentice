"""Reading a rough wireframe (the "start from a sketch" door). Same reply shape and parsing as reading a banner
(vision.from_vision); the differences are that the words are usually not legible (empty text is expected, not a problem) and
that nothing it says is trusted: the owner types or pastes the words and confirms the layers through the normal path."""

from __future__ import annotations

import pathlib
from typing import Optional

from open_apprentice.budget import Ledger
from open_apprentice.campaign.vision import (
    CANVAS_H,
    CANVAS_W,
    TEXT_ROLES,
    LayerProposal,
    VisionOut,
    check_layers,
    from_vision,
    manual_template,
)
from open_apprentice.campaign.model import call_model
from open_apprentice.providers.base import Provider

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "campaign_sketch.md"
DEFAULT_FONT_PX = {"headline": 48, "price": 36, "cta": 28, "legal": 16}


def _manual(note: str, tokens: int = 0) -> LayerProposal:
    return LayerProposal(manual_template(), "en", "manual", note=note, tokens=tokens)


async def propose_sketch_layers(
    provider: Optional[Provider], ledger: Optional[Ledger], data_url: str
) -> LayerProposal:
    """Ask Nemotron VL to read the sketch. Fallbacks match propose_layers: no provider, no reply, an unparseable or
    out-of-bounds reply -> the manual template with a note. Any other reply is returned with its problems.
    """
    if provider is None:
        return _manual("no vision model is configured on this server: place the boxes yourself")
    res = await call_model(
        provider,
        ledger,
        role="campaign_sketch",
        prompt=PROMPT,
        payload={"task": "read this sketch", "canvas": {"width": CANVAS_W, "height": CANVAS_H}},
        schema=VisionOut,
        max_tokens=8000,
        image=data_url,
    )
    if res.parsed is None:
        return _manual(res.error or "no reply", res.tokens)
    try:
        proposal = from_vision(res.parsed)
    except ValueError as e:
        return _manual(f"Nemotron's reading was not usable ({type(e).__name__})", res.tokens)
    for ly, v in zip(
        proposal.layers, res.parsed.layers
    ):  # from_vision keeps order; it guesses a size from the box
        if (
            ly.role in TEXT_ROLES and not v.font_px
        ):  # when none is given, but a sketch's box says nothing about type size
            ly.font_px = DEFAULT_FONT_PX[ly.role]
    proposal.problems = check_layers(proposal.layers, allow_empty_text=True)
    proposal.tokens, proposal.raw = res.tokens, res.parsed.model_dump()
    return proposal
