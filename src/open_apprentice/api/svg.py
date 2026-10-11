"""Real-SVG lane API (EXPERIMENTAL, spec 6.8). No model is used: the rule is the one the visitor taught in a live session, applied as a typed patch to an
owner-authored SVG, then VERIFIED by measuring rendered world geometry in the locked browser (native SVG matrices, not our arithmetic)."""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from open_apprentice.api.teach import _engine, _get, _rate_limit
from open_apprentice.svg.document import inventory, parse_document
from open_apprentice.svg.patch import Op, Patch, PatchRejected, apply_patch
from open_apprentice.svg.rule_apply import RuleNotApplicable, patch_for_pairs
from open_apprentice.svg.safety import SvgRejected

router = APIRouter(prefix="/api/svg", tags=["svg"])
SAMPLES = pathlib.Path(__file__).resolve().parents[1] / "svg" / "samples"
TOL = 0.5  # px; the same tolerance the layout verifier uses
LABEL = {
    "lane": "EXPERIMENTAL real-SVG lane",
    "rule": "the rule you taught in a live session, applied as a typed set_attribute patch",
    "model": "none",
    "verification": "rendered world geometry measured in the locked browser with native SVG matrices",
}


def _sample(name: str) -> str:
    p = SAMPLES / f"{name}.svg"
    if not p.name.endswith(".svg") or "/" in name or not p.exists():
        raise HTTPException(404, "unknown sample")
    return p.read_text()


class SvgIn(BaseModel):
    sample: Optional[str] = Field(default=None, max_length=60)
    svg: Optional[str] = Field(default=None, max_length=200_000)


class Pair(BaseModel):
    card: str = Field(max_length=100)
    badge: str = Field(max_length=100)


class ApplyIn(SvgIn):
    session_id: str = Field(max_length=40)
    pairs: list[Pair] = Field(min_length=1, max_length=20)


def _source(body: SvgIn) -> str:
    if (body.sample is None) == (body.svg is None):
        raise HTTPException(422, "send exactly one of 'sample' or 'svg'")
    return _sample(body.sample) if body.sample else body.svg or ""


def _doc(text: str):
    try:
        return parse_document(text)
    except SvgRejected as e:
        raise HTTPException(422, f"this document was not accepted: {e}") from e


def _measure(request: Request, svg: str, ids: list[str]) -> dict[str, dict]:
    url, token = _engine(request)
    try:
        r = httpx.post(
            f"{url}/internal/svg/measure",
            json={"svg": svg, "ids": ids},
            headers={"x-evaluator-token": token},
            timeout=30,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(503, "the graphics engine could not measure the document") from e
    return {b["id"]: b for b in r.json()["boxes"] if not b.get("missing")}


def suggest_pairs(inv: dict) -> list[dict]:
    """Heuristic only: a small rectangle is paired with the nearest much larger rectangle. The visitor can change every pair."""
    rects = [r for r in inv["elements"] if r.get("editable")]
    area = lambda r: r["world"]["width"] * r["world"]["height"]  # noqa: E731
    size = inv.get("size", {})
    page = (size.get("width") or 0) * (size.get("height") or 0)
    cards = [
        r for r in rects if area(r) >= 6000 and not (page and area(r) > 0.6 * page)
    ]  # a page-sized background is not a card
    out, used = [], set()
    for b in sorted(
        (r for r in rects if area(r) <= 2500), key=lambda r: (r["world"]["x"], r["world"]["y"])
    ):

        def dist(c, b=b):
            cx, cy = (
                c["world"]["x"] + c["world"]["width"] / 2,
                c["world"]["y"] + c["world"]["height"] / 2,
            )
            return (cx - b["world"]["x"]) ** 2 + (cy - b["world"]["y"]) ** 2

        near = [c for c in cards if c["id"] not in used]
        if near:
            c = min(near, key=dist)
            used.add(c["id"])
            out.append({"card": c["id"], "badge": b["id"]})
    return out


@router.get("/samples")
async def samples() -> list[dict]:
    out = []
    for p in sorted(SAMPLES.glob("*.svg")):
        d = parse_document(p.read_text())
        inv = inventory(d)
        out.append(
            {
                "id": p.stem,
                "bytes": p.stat().st_size,
                "coverage": inv["coverage"],
                "suggested_pairs": suggest_pairs(inv),
            }
        )
    return out


@router.post("/inspect")
async def inspect(request: Request, body: SvgIn) -> dict:
    """Public, read-only: validate and list the elements, with their world geometry and what is (not) editable. The source is returned for display only."""
    text = _source(body)
    d = _doc(text)
    inv = inventory(d)
    return {"source": text, "inventory": inv, "suggested_pairs": suggest_pairs(inv), "label": LABEL}


@router.post("/apply")
async def apply(request: Request, body: ApplyIn) -> dict:
    _rate_limit(request, "svg")
    live = _get(request, body.session_id)
    if live.concept is None:
        raise HTTPException(
            409, "teach the rule first: this lane applies the rule you taught in Try it live"
        )
    text = _source(body)
    d = _doc(text)
    try:
        patch, expected = patch_for_pairs(
            d, live.concept.rule, [(p.card, p.badge) for p in body.pairs]
        )
        result = apply_patch(text, patch)
    except RuleNotApplicable as e:
        raise HTTPException(422, f"this rule cannot be applied to that selection: {e}") from e
    except PatchRejected as e:
        raise HTTPException(422, {"rejected": e.reasons}) from e
    editable = [r["id"] for r in inventory(d)["elements"] if r.get("editable")]
    before, after = await asyncio.gather(
        asyncio.to_thread(_measure, request, text, editable),
        asyncio.to_thread(_measure, request, result.text, editable),
    )
    badges = {p.badge for p in body.pairs}
    rows, ok = [], True
    for ex in expected:
        got, w = after.get(ex["badge"]), ex["world"]
        delta = (
            None
            if got is None
            else max(
                abs(got["x"] - w["x"]),
                abs(got["y"] - w["y"]),
                abs(got["width"] - w["width"]),
                abs(got["height"] - w["height"]),
            )
        )
        passed = delta is not None and delta <= TOL
        ok &= passed
        rows.append(
            {
                "badge": ex["badge"],
                "card": ex["card"],
                "expected": w,
                "measured": got,
                "max_error_px": delta,
                "passed": passed,
            }
        )
    moved = [
        i
        for i in editable
        if i in before
        and i in after
        and max(abs(before[i][k] - after[i][k]) for k in ("x", "y", "width", "height")) > 0.01
    ]
    others_unchanged = all(i in badges for i in moved)
    ok &= others_unchanged
    return jsonable_encoder(
        {
            "label": LABEL,
            "passed": bool(ok),
            "hash_before": result.hash_before,
            "hash_after": result.hash_after,
            "patch": patch.model_dump(),
            "diff": result.diff,
            "unrelated_byte_changes": result.unrelated_byte_changes,
            "scope": result.scope,
            "rows": rows,
            "moved_elements": moved,
            "only_selected_badges_moved": others_unchanged,
            "concept_hash": live.concept.sealed_hash(),
            "original_svg": text,
            "modified_svg": result.text,
            "coverage": inventory(d)["coverage"],
        }
    )


@router.post("/harmful-demo")
async def harmful_demo(body: SvgIn) -> dict:
    """Attempt a series of deliberately harmful patches against a document; every one must be rejected, with its reason. Reports honestly if one is not."""
    text = _source(body)
    d = _doc(text)
    rects = [r for r in inventory(d)["elements"] if r.get("editable")]
    if not rects:
        raise HTTPException(422, "this document has no editable rectangles")
    r0 = rects[0]
    cur = {k: str(int(v)) if float(v).is_integer() else str(v) for k, v in r0["local"].items()}
    attempts = [
        (
            "Patch written for a different version of the document",
            Patch(
                doc_hash="0" * 64,
                ops=[Op(element=r0["id"], attribute="x", expected_old=cur["x"], new="5")],
            ),
        ),
        (
            "Overwrite a value the patch never observed (stale)",
            Patch(
                doc_hash=d.hash,
                ops=[Op(element=r0["id"], attribute="x", expected_old="-12345", new="5")],
            ),
        ),
        (
            "Add an event handler (active content)",
            Patch(
                doc_hash=d.hash,
                ops=[Op(element=r0["id"], attribute="onclick", expected_old=None, new="alert(1)")],
            ),
        ),
        (
            "Point a fill at an external resource",
            Patch(
                doc_hash=d.hash,
                ops=[
                    Op(
                        element=r0["id"],
                        attribute="fill",
                        expected_old=r0.get("fill"),
                        new="url(http://evil.example/x)",
                    )
                ],
            ),
        ),
        (
            "Set a non-finite or absurd number",
            Patch(
                doc_hash=d.hash,
                ops=[
                    Op(element=r0["id"], attribute="width", expected_old=cur["width"], new="1e12")
                ],
            ),
        ),
        (
            "Two conflicting writes to the same attribute",
            Patch(
                doc_hash=d.hash,
                ops=[
                    Op(element=r0["id"], attribute="x", expected_old=cur["x"], new="1"),
                    Op(element=r0["id"], attribute="x", expected_old=cur["x"], new="2"),
                ],
            ),
        ),
        (
            "A valid edit bundled with an invalid one (must apply NOTHING)",
            Patch(
                doc_hash=d.hash,
                ops=[
                    Op(element=r0["id"], attribute="x", expected_old=cur["x"], new="1"),
                    Op(element=r0["id"], attribute="href", expected_old=None, new="http://x"),
                ],
            ),
        ),
    ]
    out: list[Any] = []
    for title, patch in attempts:
        try:
            apply_patch(text, patch)
            out.append({"attempt": title, "rejected": False, "reasons": []})
        except PatchRejected as e:
            out.append({"attempt": title, "rejected": True, "reasons": e.reasons})
    return {
        "label": LABEL,
        "all_rejected": all(a["rejected"] for a in out),
        "attempts": out,
        "document_unchanged": True,
    }
