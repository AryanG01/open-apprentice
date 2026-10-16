"""Client for the engine's /drawio/render route. Measurements arrive as floats and are kept as exact 1/64 rationals (spec 6
quantum)."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

import httpx

from open_apprentice.drawio.parse import DrawioRefused, Page, page_document


@dataclass(frozen=True)
class Box:
    x: Fraction
    y: Fraction
    w: Fraction
    h: Fraction


@dataclass(frozen=True)
class Rendered:
    labels: dict[str, tuple[Box, int]]  # cell -> (measured glyph box, rendered line count)
    nodes: dict[
        str, tuple[Box, Optional[Box], Fraction]
    ]  # cell -> (cell-state box, rendered element box, stroke width)
    missing: tuple[str, ...]
    profile: dict
    png: Optional[bytes]
    svg: Optional[str]


def q64(v: float | int | str) -> Fraction:
    return Fraction(round(Fraction(v) * 64), 64)


def _box(d: dict) -> Box:
    return Box(q64(d["x"]), q64(d["y"]), q64(d["w"]), q64(d["h"]))


def parse_render(body: dict) -> Rendered:
    return Rendered(
        labels={k: (_box(v["box"]), int(v["lines"])) for k, v in body["labels"].items()},
        nodes={
            k: (
                _box(v["state"]),
                _box(v["element"]) if v.get("element") else None,
                q64(v.get("stroke", 1)),
            )
            for k, v in body["nodes"].items()
        },
        missing=tuple(body.get("missing", ())),
        profile=dict(body.get("profile", {})),
        png=base64.b64decode(body["png"]) if body.get("png") else None,
        svg=body.get("svg"),
    )


def render_page(
    page: Page, engine_url: str, *, png: bool = True, svg: bool = False, timeout: float = 30.0
) -> Rendered:
    try:
        r = httpx.post(
            f"{engine_url}/drawio/render",
            json={"xml": page_document(page), "want_png": png, "want_svg": svg},
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise DrawioRefused(f"the renderer is unavailable ({type(e).__name__})") from e
    try:
        body = r.json()
    except ValueError as e:
        raise DrawioRefused(
            f"the renderer returned an unreadable response ({r.status_code})"
        ) from e
    if r.status_code != 200:
        message = body.get("error", {}).get("message", r.status_code)
        raise DrawioRefused(f"the page could not be rendered: {message}")
    return parse_render(body)
