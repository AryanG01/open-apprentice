"""Does Nemotron VL read a rough wireframe into layers well enough to help? Draws a deterministic, seeded, wobbly
"hand-drawn" wireframe from each development fixture's authored layers, asks the vision model for the layers and scores
roles and box overlap against those layers. The decision rule below is fixed before any live run; see
docs/evaluation/campaign_sketch_protocol.md.

The wireframes are synthetic (a seeded jitter on straight lines), NOT hand drawn: they test the plumbing and the model's
basic reading. The owner's real sketches are the honest test and are reported as a separate labelled set.

Rendering is pure standard library (a small anti-aliased line rasteriser writing a grayscale PNG): the engine has no
SVG-to-PNG route, and this keeps the harness runnable offline and byte-for-byte reproducible."""

from __future__ import annotations

import base64
import math
import random
import statistics
import struct
import zlib
from typing import Any

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.sketch import propose_sketch_layers
from open_apprentice.campaign.vision import LAYER_ROLES, TEXT_ROLES, LayerProposal
from open_apprentice.evaluation.campaign_vision_eval import (
    DEV_BANNERS,
    banner_frame,
    gold_layers,
    iou,
)
from open_apprentice.providers.base import Provider

W, H = 1280, 720
INK, STROKE = 60, 3.0  # dark grey pencil on white
SEED = 20261026
FOUND_IOU = 0.3  # a layer counts as found when the model's box overlaps the true one at least this much (sketches are loose)
GO_SKETCHES, GO_MEDIAN_IOU = (
    5,
    0.5,
)  # of 6 sketches with every layer found, and the median overlap of all layers
PARTIAL_SKETCHES, PARTIAL_MEDIAN_IOU = (
    5,
    0.3,
)  # all six roles named once on 5 of 6 and the median overlap at least this


class Canvas:
    def __init__(self, seed: int) -> None:
        self.px = bytearray(b"\xff" * (W * H))
        self.rnd = random.Random(seed)
        self.extent: dict[str, list[float]] = {}
        self.role = ""

    def _grow(self, x: float, y: float) -> None:
        e = self.extent.setdefault(self.role, [x, y, x, y])
        e[:] = [min(e[0], x), min(e[1], y), max(e[2], x), max(e[3], y)]

    def segment(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self._grow(x0, y0)
        self._grow(x1, y1)
        r = STROKE / 2 + 0.5
        dx, dy = x1 - x0, y1 - y0
        n2 = dx * dx + dy * dy or 1.0
        for py in range(max(0, int(min(y0, y1) - r)), min(H, int(max(y0, y1) + r) + 1)):
            for px in range(max(0, int(min(x0, x1) - r)), min(W, int(max(x0, x1) + r) + 1)):
                t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / n2))
                d = math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))
                cov = max(0.0, min(1.0, r - d))
                if cov:
                    i = py * W + px
                    self.px[i] = min(self.px[i], round(255 - cov * (255 - INK)))

    def stroke(self, pts: list[tuple[float, float]]) -> None:
        for a, b in zip(pts, pts[1:]):
            self.segment(*a, *b)

    def wobble(self, x0: float, y0: float, x1: float, y1: float, amp: float = 1.8) -> list:
        """A hand-drawn line: points every ~28 px nudged sideways, ends overshooting a little."""
        length = math.hypot(x1 - x0, y1 - y0) or 1.0
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        o = self.rnd.uniform(-3, 5)
        x0, y0, x1, y1 = (
            x0 - ux * o,
            y0 - uy * o,
            x1 + ux * self.rnd.uniform(-3, 5),
            y1 + uy * self.rnd.uniform(-3, 5),
        )
        n = max(1, round(length / 28))
        pts = []
        for i in range(n + 1):
            j = self.rnd.uniform(-amp, amp) if 0 < i < n else self.rnd.uniform(-1, 1)
            pts.append((x0 + (x1 - x0) * i / n - uy * j, y0 + (y1 - y0) * i / n + ux * j))
        return pts

    def line(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.stroke(self.wobble(x0, y0, x1, y1))

    def box(self, x: float, y: float, w: float, h: float) -> None:
        for a, b in (
            ((x, y), (x + w, y)),
            ((x + w, y), (x + w, y + h)),
            ((x + w, y + h), (x, y + h)),
            ((x, y + h), (x, y)),
        ):
            self.line(*a, *b)

    def rounded(self, x: float, y: float, w: float, h: float) -> None:
        r = min(h / 2, 22.0)
        pts: list[tuple[float, float]] = []
        for cx, cy, a0 in (
            (x + w - r, y + r, -90),
            (x + w - r, y + h - r, 0),
            (x + r, y + h - r, 90),
            (x + r, y + r, 180),
        ):
            pts += [
                (
                    cx + r * math.cos(math.radians(a0 + k * 15)),
                    cy + r * math.sin(math.radians(a0 + k * 15)),
                )
                for k in range(7)
            ]
        pts.append(pts[0])
        self.stroke(
            [(px + self.rnd.uniform(-1.2, 1.2), py + self.rnd.uniform(-1.2, 1.2)) for px, py in pts]
        )

    def scribble(self, x0: float, x1: float, y: float, amp: float, step: float) -> None:
        """A row of pretend handwriting: a zig-zag with a gap every few strokes (word breaks)."""
        pts, x, k = [], x0, 0
        while x < x1:
            pts.append((x, y + (amp if k % 2 else -amp) * self.rnd.uniform(0.5, 1.1)))
            x, k = x + step * self.rnd.uniform(0.6, 1.4), k + 1
            if k % 14 == 0:
                self.stroke(pts)
                pts, x = [], x + step * 2.5
        self.stroke(pts)

    def dollar(self, cx: float, cy: float, s: float) -> None:
        """A hand-drawn $: one S stroke (a sine period) and a bar through it."""
        self.stroke(
            [
                (cx + 0.55 * s * math.sin(2 * math.pi * t / 12 + 0.4), cy - s + 2 * s * t / 12)
                for t in range(13)
            ]
        )
        self.line(cx, cy - s * 1.2, cx, cy + s * 1.2)

    def png(self) -> bytes:
        def chunk(tag: bytes, body: bytes) -> bytes:
            return (
                struct.pack(">I", len(body))
                + tag
                + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
            )

        rows = b"".join(b"\x00" + bytes(self.px[y * W : (y + 1) * W]) for y in range(H))
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9))
            + chunk(b"IEND", b"")
        )


def to_canvas(gold: dict[str, dict], frame: tuple[float, float]) -> dict[str, dict]:
    """The gold layers in 1280 x 720 pixels (the fixtures are not all 1280 x 720)."""
    kx, ky = W / frame[0], H / frame[1]
    return {
        r: {
            **g,
            "box": [g["box"][0] * kx, g["box"][1] * ky, g["box"][2] * kx, g["box"][3] * ky],
            "font_px": g["font_px"] * ky,
        }
        for r, g in gold.items()
    }


def draw_wireframe(
    gold: dict[str, dict], frame: tuple[float, float], seed: int = SEED
) -> tuple[bytes, dict]:
    """(PNG bytes, per-role drawn extent [x0, y0, x1, y1]). Same input and seed, same bytes. Pictures are boxes (crossed for
    the product), the button a rounded box with a short scribble, text is rows of scribble sized from the text's length and
    font size; the price starts with a drawn dollar sign. No real words are written."""
    c = Canvas(seed)
    for role, g in to_canvas(gold, frame).items():
        x, y, w, h = g["box"]
        c.role = role
        if role == "brand_mark":
            c.box(x, y, w, h)
            c.scribble(x + w * 0.2, x + w * 0.8, y + h / 2, h * 0.16, 5)
        elif role == "product_image":
            c.box(x, y, w, h)
            c.line(x, y, x + w, y + h)
            c.line(x + w, y, x, y + h)
        elif role == "cta":
            c.rounded(x, y, w, h)
            c.scribble(x + w * 0.3, x + w * 0.7, y + h / 2, h * 0.12, 5)
        else:
            fpx = max(g["font_px"], 12.0)
            pitch = fpx * 1.5
            width = w * 0.97
            need = len(g["text"]) * 0.5 * fpx
            rows = max(1, min(int(h // pitch), math.ceil(need / width)))
            for i in range(rows):
                ry = y + pitch * (i + 0.5)
                last = need - width * (rows - 1) if i == rows - 1 else width
                x0 = x + 2
                if role == "price" and i == 0:
                    c.dollar(x0 + fpx * 0.3, ry, fpx * 0.38)
                    x0 += fpx * 0.9
                c.scribble(x0, x0 + max(fpx * 2, min(width, last)), ry, fpx * 0.2, fpx * 0.22)
    return c.png(), c.extent


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def score_case(
    proposal: LayerProposal, gold: dict[str, dict], frame: tuple[float, float]
) -> dict[str, Any]:
    truth = to_canvas(gold, frame)
    by: dict[str, list] = {}
    for ly in proposal.layers:
        by.setdefault(ly.role, []).append(ly)
    scores = {
        r: (
            iou(by[r][0].box, g["box"])
            if len(by.get(r, [])) == 1 and len(by[r][0].box) == 4
            else 0.0
        )
        for r, g in truth.items()
    }
    return {
        "roles_present": set(by) == set(truth) and all(len(v) == 1 for v in by.values()),
        "all_found": all(s >= FOUND_IOU for s in scores.values()),
        "iou": {r: round(s, 3) for r, s in scores.items()},
        # POST HOC (not part of the registered rule): the sketches contain no legible words, so any words are invented
        "invented_words": sum(
            bool(ly.text.strip()) for ly in proposal.layers if ly.role in TEXT_ROLES
        ),
        "origin": proposal.origin,
        "problems": proposal.problems,
    }


def verdict(cases: list[dict]) -> dict[str, Any]:
    n = len(cases)
    found = sum(c["all_found"] for c in cases)
    present = sum(c["roles_present"] for c in cases)
    ious = [s for c in cases for s in c["iou"].values()]
    median = statistics.median(ious) if ious else 0.0
    if found >= min(GO_SKETCHES, n) and median >= GO_MEDIAN_IOU:
        decision = "go"
    elif present >= min(PARTIAL_SKETCHES, n) and median >= PARTIAL_MEDIAN_IOU:
        decision = "partial"
    else:
        decision = "no-go"
    return {
        "sketches": n,
        "all_found": found,
        "roles_present": present,
        "median_iou": round(median, 3),
        "invented_words": sum(c["invented_words"] for c in cases),  # post hoc
        "decision": decision,
    }


async def run_dev(
    provider: Provider | None, engine_url: str | None = None, token: str | None = None
) -> list[dict]:
    """`engine_url` and `token` are accepted for parity with campaign_vision_eval.run_dev and are not used: the wireframes
    are drawn in-process, so the probe needs no browser."""
    ledger = Ledger(Limits(tokens=400_000, calls=12))
    rows = []
    for i, fid in enumerate(DEV_BANNERS):
        scene = load_fixture(fid)["scene"]
        frame, gold = banner_frame(scene), gold_layers(scene)
        png, extent = draw_wireframe(gold, frame, SEED + i)
        proposal = await propose_sketch_layers(provider, ledger, data_url(png))
        rows.append(
            {
                "sketch": fid,
                "gold": {r: g["box"] for r, g in to_canvas(gold, frame).items()},
                "drawn_extent": {r: [round(v, 1) for v in e] for r, e in extent.items()},
                "proposed": [ly.model_dump() for ly in proposal.layers],
                "raw": proposal.raw,
                "note": proposal.note,
                "tokens": proposal.tokens,
                "score": score_case(proposal, gold, frame),
            }
        )
    return rows


def render_markdown(rows: list[dict], *, model: str, spent_usd: float, calls: int) -> str:
    v = verdict([r["score"] for r in rows])
    lines = [
        "# Reading a rough sketch: development probe",
        "",
        f"Model `{model}` · {len(rows)} synthetic wireframes (seeded wobbly lines drawn from the development fixtures, NOT hand "
        f"drawn) · {calls} calls · ${spent_usd:.3f} (ledger). Development fixtures, not held out; one run, no retries. The owner's "
        "real sketches are a separate set and are the honest test.",
        "",
        f"**Decision: {v['decision']}** (rule fixed beforehand: go = every layer found at box overlap ≥ {FOUND_IOU} on "
        f"{GO_SKETCHES} of 6 sketches and median overlap of all layers ≥ {GO_MEDIAN_IOU}; partial = all six roles named once on "
        f"{PARTIAL_SKETCHES} of 6 and median overlap ≥ {PARTIAL_MEDIAN_IOU}).",
        "",
        f"- Every layer found on **{v['all_found']} of {v['sketches']}** sketches; all six roles named once on {v['roles_present']}.",
        f"- Median box overlap of all layers: **{v['median_iou']}**.",
        f"- Post hoc: words the model wrote although the sketches carry none: {v['invented_words']}.",
        "",
        "| sketch | roles named | all found | "
        + " | ".join(f"{r} IoU" for r in LAYER_ROLES)
        + " | origin |",
        "|---|---|---|" + "---|" * len(LAYER_ROLES) + "---|",
    ]
    for r in rows:
        s = r["score"]
        lines.append(
            f"| {r['sketch']} | {'yes' if s['roles_present'] else 'no'} | {'yes' if s['all_found'] else 'no'} | "
            + " | ".join(str(s["iou"].get(role, "-")) for role in LAYER_ROLES)
            + f" | {s['origin']} |"
        )
    return "\n".join(lines) + "\n"
