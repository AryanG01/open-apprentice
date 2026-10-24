"""Reading a flat banner image (the "bring your own banner" path). Nemotron VL proposes the layers (role, box, words, size,
colour); nothing it says is trusted: a deterministic check names every problem, the owner corrects the layers, and the
corrected layers become the same scene shape the fixtures use, which must also pass the existing role gate.

Pixels are never judged here. Crops, the background colour and image sizes are measured in the owner's browser and
re-read from the image headers on the server; the model only proposes."""

from __future__ import annotations

import functools
import math
import pathlib
import re
from dataclasses import dataclass, field
from typing import Optional

from fontTools.ttLib import TTFont

from open_apprentice.budget import Ledger
from open_apprentice.campaign.imageinfo import ImageError, image_size
from open_apprentice.campaign.limits import ROLES
from open_apprentice.campaign.model import call_model
from open_apprentice.campaign.roles import check_role_mapping, has_currency
from open_apprentice.campaign.scene import RoleError, role_map
from open_apprentice.providers.base import Provider, StrictModel

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "campaign_vision.md"
# ponytail: repo-relative font path, like evaluation/text_layout.py; the API image carries services/engine/vendor.
_FONT = (
    pathlib.Path(__file__).resolve().parents[3]
    / "services"
    / "engine"
    / "vendor"
    / "fonts"
    / "LiberationSans-Regular.ttf"
)

CANVAS_W, CANVAS_H = 1280, 720
LAYER_ROLES = tuple(
    r for r in ROLES if r != "background"
)  # the background is a colour, not a layer
IMAGE_ROLES = ("brand_mark", "product_image")
TEXT_ROLES = ("headline", "price", "legal", "cta")
ASSET_ID = re.compile(r"u-[0-9a-f]{12}-(brand_mark|product_image)")
UID = re.compile(r"[0-9a-f]{12}")
HEX = re.compile(r"#[0-9a-fA-F]{6}")
MAX_TEXT = {"headline": 200, "price": 80, "legal": 300, "cta": 40}
MIN_IMAGE_SIDE = 24
MIN_CTA_W, MIN_CTA_H = 60, 24
MAX_OVERLAP = 0.15  # an image box may share this fraction of its area with a text box before its crop would hold words
MIN_CONTRAST = 3.0  # WCAG ratio for large text
LINE_HEIGHT = {"headline": 1.1, "price": 1.1, "legal": 1.3, "cta": 1.1}
DEFAULT_PLATE = "#ffd23f"


class Layer(StrictModel):
    """One layer as the owner edits it: a pixel box [x, y, w, h] on the 1280x720 banner."""

    role: str
    box: list[float]
    text: str = ""
    font_px: float = 0
    bold: bool = False
    color: str = ""  # text colour; for the button, the label colour
    fill: str = ""  # the button plate's colour (button only)


class VisionLayer(StrictModel):
    role: str
    box: list[float]  # [x_min, y_min, x_max, y_max] on a 0..1000 grid of the image
    text: str = ""
    font_px: Optional[float] = None
    bold: bool = False
    color: str = ""
    fill: str = ""


class VisionOut(StrictModel):
    language: str = "en"
    layers: list[VisionLayer]


@dataclass
class LayerProposal:
    layers: list[Layer]
    language: str
    origin: str  # model | manual
    problems: list[str] = field(
        default_factory=list
    )  # what check_layers found in the layers as proposed
    note: str = ""  # why the manual template was used, when it was
    tokens: int = 0
    raw: Optional[dict] = None  # the model's reply as parsed, for audit


@functools.cache
def _cmap() -> frozenset[int]:
    return frozenset(TTFont(_FONT)["cmap"].getBestCmap())


def _lum(hex_: str) -> float:
    def lin(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def readable_on(bg: str) -> str:
    """White or near-black, whichever reads better on `bg`."""
    return "#ffffff" if contrast("#ffffff", bg) >= contrast("#111111", bg) else "#111111"


def fit_font(text: str, w: float, h: float, bold: bool, line_height: float = 1.1) -> float:
    """The largest size at which `text` is estimated to fit w x h (coarse average glyph width: 0.55 em, 0.6 bold). Only used
    to keep the rebuilt banner legible; the story card's sizes come from the learned rule and are measured by the engine.
    """
    cw = 0.6 if bold else 0.55
    f = max(6.0, h / line_height)
    while f > 6:
        per_line = max(1, int(w / (cw * f)))
        lines = sum(max(1, math.ceil(len(par) / per_line)) for par in (text or " ").split("\n"))
        if lines * line_height * f <= h:
            return round(f, 1)
        f *= 0.96
    return 6.0


def from_vision(raw: VisionOut | dict) -> LayerProposal:
    """Model boxes (corner pairs on a 0..1000 grid) to pixel boxes on the 1280x720 banner."""
    out = raw if isinstance(raw, VisionOut) else VisionOut.model_validate(raw)
    layers = []
    for v in out.layers:
        if len(v.box) != 4 or not all(math.isfinite(c) for c in v.box):
            layers.append(Layer(role=v.role, box=[0, 0, 0, 0], text=v.text))
            continue
        x1, y1, x2, y2 = v.box
        box = [
            round(x1 * CANVAS_W / 1000, 1),
            round(y1 * CANVAS_H / 1000, 1),
            round((x2 - x1) * CANVAS_W / 1000, 1),
            round((y2 - y1) * CANVAS_H / 1000, 1),
        ]
        size = v.font_px
        if not size and v.role in TEXT_ROLES:
            size = fit_font(v.text, box[2], box[3], v.bold, LINE_HEIGHT[v.role])
        layers.append(
            Layer(
                role=v.role,
                box=box,
                text=v.text,
                font_px=size or 0,
                bold=v.bold,
                color=v.color,
                fill=v.fill,
            )
        )
    return LayerProposal(layers, (out.language or "en")[:2].lower(), "model")


def manual_template() -> list[Layer]:
    """A generic 16:9 arrangement with no words: the owner drags the boxes and types the text."""
    box = lambda x, y, w, h: [float(x), float(y), float(w), float(h)]  # noqa: E731
    return [
        Layer(role="brand_mark", box=box(64, 48, 192, 48)),
        Layer(role="product_image", box=box(80, 152, 480, 480)),
        Layer(role="headline", box=box(640, 160, 576, 176), font_px=48, bold=True),
        Layer(role="price", box=box(640, 352, 576, 52), font_px=36, bold=True),
        Layer(role="cta", box=box(640, 432, 256, 76), font_px=28, bold=True),
        Layer(role="legal", box=box(640, 560, 576, 80), font_px=16),
    ]


def _overlap(a: list[float], b: list[float]) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def check_layers(layers: list[Layer], background: Optional[str] = None) -> list[str]:
    """Every reason these layers cannot become a banner, in plain words. Empty means usable. Contrast is judged only once
    the background colour (measured in the browser) is known."""
    problems: list[str] = []
    by_role: dict[str, list[Layer]] = {}
    for l in layers:
        by_role.setdefault(l.role, []).append(l)
    problems += [f"unknown role {r}" for r in by_role if r not in LAYER_ROLES]
    problems += [f"role {r} is missing" for r in LAYER_ROLES if r not in by_role]
    problems += [
        f"role {r} is given to more than one layer" for r, ls in by_role.items() if len(ls) > 1
    ]
    if problems:
        return problems
    one = {r: ls[0] for r, ls in by_role.items()}
    label = {r: r.replace("_", " ") for r in LAYER_ROLES}
    for r, l in one.items():
        if len(l.box) != 4 or not all(math.isfinite(c) for c in l.box):
            problems.append(f"{label[r]} has no usable box")
            continue
        x, y, w, h = l.box
        if w <= 0 or h <= 0:
            problems.append(f"{label[r]} box is empty")
        elif (
            x < -0.02 * CANVAS_W
            or y < -0.02 * CANVAS_H
            or x + w > 1.02 * CANVAS_W
            or y + h > 1.02 * CANVAS_H
        ):
            problems.append(f"{label[r]} box is outside the banner")
        elif r in IMAGE_ROLES and min(w, h) < MIN_IMAGE_SIDE:
            problems.append(f"{label[r]} box is too small to crop (under {MIN_IMAGE_SIDE} px)")
        elif r == "cta" and (w < MIN_CTA_W or h < MIN_CTA_H):
            problems.append(f"the button box is too small ({MIN_CTA_W} x {MIN_CTA_H} px at least)")
        if l.color and not HEX.fullmatch(l.color):
            problems.append(f"{label[r]} colour must be a #rrggbb value")
        if l.fill and not HEX.fullmatch(l.fill):
            problems.append(f"{label[r]} fill colour must be a #rrggbb value")
    for r in TEXT_ROLES:
        l = one[r]
        if not l.text.strip():
            problems.append(f"{label[r]} text is empty: type the words that are in the image")
        elif len(l.text) > MAX_TEXT[r]:
            problems.append(f"{label[r]} text is too long ({MAX_TEXT[r]} characters at most)")
        else:
            missing = sorted({c for c in l.text if not c.isspace() and ord(c) not in _cmap()})
            if missing:
                problems.append(
                    f"{label[r]} uses characters Liberation Sans cannot draw: {''.join(missing[:5])}"
                )
        if l.font_px <= 0:
            problems.append(f"{label[r]} text size is missing")
    if all(one[r].text.strip() for r in ("price",)) and not (
        re.search(r"\d", one["price"].text) and has_currency(one["price"].text)
    ):
        problems.append("price must contain a number and a currency")
    sizes = [one[r].font_px for r in ("headline", "price", "legal")]
    if all(s > 0 for s in sizes) and not sizes[2] < min(sizes[0], sizes[1]):
        problems.append("legal must be the smallest text (smaller than the headline and the price)")
    for ir in IMAGE_ROLES:
        img = one[ir]
        area = img.box[2] * img.box[3] if len(img.box) == 4 else 0
        for tr in TEXT_ROLES:
            if (
                area > 0
                and len(one[tr].box) == 4
                and _overlap(img.box, one[tr].box) / area > MAX_OVERLAP
            ):
                problems.append(
                    f"{label[ir]} box overlaps the {label[tr]} text: its crop would contain words"
                )
    if background:
        if not HEX.fullmatch(background):
            problems.append("background colour must be a #rrggbb value")
        else:
            for r in ("headline", "price", "legal"):
                c = one[r].color
                if c and HEX.fullmatch(c) and contrast(c, background) < MIN_CONTRAST:
                    problems.append(f"{label[r]} text has too little contrast with the background")
            cta = one["cta"]
            if cta.color and cta.fill and HEX.fullmatch(cta.color) and HEX.fullmatch(cta.fill):
                if contrast(cta.color, cta.fill) < MIN_CONTRAST:
                    problems.append("the button label has too little contrast with its plate")
    return problems


def _text_node(nid, parent, text, size, bold, color, align, x, y, w, h, z, line_height) -> dict:
    return {
        "id": nid,
        "type": "text",
        "parent": parent,
        "text": text,
        "fontFamily": "Liberation Sans",
        "fontSize": size,
        "fontStyle": "bold" if bold else "normal",
        "lineHeight": line_height,
        "align": align,
        "wrap": "word",
        "fill": color,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "z": z,
    }


def build_scene(
    layers: list[Layer],
    *,
    background: str,
    crops: dict[str, str],
    uid: str,
    link: Optional[str],
    locale: str,
) -> dict:
    """The owner's layers as a campaign scene (same node shapes as fixture_data/short_a.json). The two crops travel in
    scene["assets"] under per-upload ids. Raises ValueError with every reason when the layers are not usable.
    """
    if not UID.fullmatch(uid or ""):
        raise ValueError("uid must be 12 lowercase hex characters")
    problems = check_layers(layers, background)
    if problems:
        raise ValueError("; ".join(problems))
    if link is not None and not (re.fullmatch(r"https://[^\s]{1,480}", link)):
        raise ValueError("the link must be an https URL")
    if not re.fullmatch(r"[a-z]{2}", locale or ""):
        raise ValueError("the language must be a two-letter code")
    one = {l.role: l for l in layers}
    p = f"u-{uid}"
    nodes: list[dict] = [
        {
            "id": "banner",
            "type": "artboard",
            "x": 0,
            "y": 0,
            "width": CANVAS_W,
            "height": CANVAS_H,
            "format": "16:9",
            "safe": {"top": 0, "right": 0, "bottom": 0, "left": 0},
            "sequence": 1,
        },
        {
            "id": f"{p}-bg",
            "type": "rect",
            "parent": "banner",
            "role": "background",
            "x": 0,
            "y": 0,
            "width": CANVAS_W,
            "height": CANVAS_H,
            "fill": background.lower(),
            "z": 0,
        },
    ]
    assets: dict[str, str] = {}
    for z, r in enumerate(IMAGE_ROLES, start=1):
        l = one[r]
        url = crops.get(r)
        if not url:
            raise ValueError(f"the {r.replace('_', ' ')} crop is missing")
        try:
            kind, nat_w, nat_h = image_size(url, max_bytes=1_000_000)
        except ImageError as e:
            raise ValueError(f"the {r.replace('_', ' ')} crop is not usable: {e}") from e
        if kind != "png":
            raise ValueError(f"the {r.replace('_', ' ')} crop must be a PNG")
        aid = f"{p}-{r}"
        assets[aid] = url
        x, y, w, h = l.box
        nodes.append(
            {
                "id": f"{p}-{r.split('_')[0]}",
                "type": "image",
                "parent": "banner",
                "role": r,
                "asset": aid,
                "crop": None,
                "focal": {"x": nat_w / 2, "y": nat_h / 2},
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "z": z,
            }
        )
    text_color = {
        r: one[r].color or readable_on(background) for r in ("headline", "price", "legal")
    }
    for z, (r, short) in enumerate(
        (("headline", "head"), ("price", "price"), ("legal", "legal")), start=3
    ):
        l = one[r]
        x, y, w, h = l.box
        lh = LINE_HEIGHT[r]
        size = round(min(l.font_px, fit_font(l.text, w, h, l.bold, lh)), 1)
        node = _text_node(
            f"{p}-{short}", "banner", l.text, size, l.bold, text_color[r], "left", x, y, w, h, z, lh
        )
        node["role"] = r
        nodes.append(node)
    cta = one["cta"]
    x, y, w, h = cta.box
    plate = cta.fill or DEFAULT_PLATE
    label = cta.color or readable_on(plate)
    size = round(min(cta.font_px, fit_font(cta.text, w, h * 0.7, True, 1.1)), 1)
    label_h = round(size * 1.33, 1)
    group = {
        "id": f"{p}-cta",
        "type": "group",
        "parent": "banner",
        "role": "cta",
        "x": x,
        "y": y,
        "z": 5,
    }
    if link is not None:
        group["link"] = link
    nodes.append(group)
    nodes.append(
        {
            "id": f"{p}-cta-plate",
            "type": "shape",
            "parent": f"{p}-cta",
            "x": 0,
            "y": 0,
            "width": w,
            "height": h,
            "fill": plate,
            "cornerRadius": round(h / 2, 1),
            "z": 0,
        }
    )
    nodes.append(
        _text_node(
            f"{p}-cta-label",
            f"{p}-cta",
            cta.text,
            size,
            True,
            label,
            "center",
            0,
            max(0.0, round((h - label_h) / 2, 1)),
            w,
            label_h,
            1,
            1.1,
        )
    )
    scene = {"canvas": {"width": CANVAS_W, "height": CANVAS_H}, "nodes": nodes, "assets": assets}
    # second, independent gate: the same role checks the roles lane applies to an owner-confirmed mapping
    mapping = {n["id"]: n["role"] for n in nodes if n.get("role")}
    try:
        role_map(scene, "banner")
    except RoleError as e:
        raise ValueError("; ".join(e.problems)) from e
    again = check_role_mapping(scene, "banner", mapping)
    if again:
        raise ValueError("; ".join(again))
    return scene


async def propose_layers(
    provider: Optional[Provider], ledger: Optional[Ledger], data_url: str
) -> LayerProposal:
    """Ask Nemotron VL to read the banner. A reply that fails the checks is still returned, with its problems, so the owner
    can fix it in the editor; only no provider, no reply or an unparseable reply falls back to the manual template.
    """
    if provider is None:
        return LayerProposal(
            manual_template(),
            "en",
            "manual",
            note="no vision model is configured on this server: place the boxes yourself",
        )
    res = await call_model(
        provider,
        ledger,
        role="campaign_vision",
        prompt=PROMPT,
        payload={"task": "read this banner", "canvas": {"width": CANVAS_W, "height": CANVAS_H}},
        schema=VisionOut,
        max_tokens=8000,  # a long headline made the reasoning model hit 4000 twice (probe run 1)
        image=data_url,
    )
    if res.parsed is None:
        return LayerProposal(
            manual_template(), "en", "manual", note=res.error or "no reply", tokens=res.tokens
        )
    proposal = from_vision(res.parsed)
    proposal.problems, proposal.tokens = check_layers(proposal.layers), res.tokens
    proposal.raw = res.parsed.model_dump()
    return proposal
