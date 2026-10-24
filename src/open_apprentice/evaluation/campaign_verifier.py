"""Independent verifier for a promo banner turned story card (spec 7.7).

Reads the source scene, the PRIVATE native state of the result, and the authored gold scene. It recomputes everything itself:
geometry from raw node attrs, text fit from the font tables (`text_layout`). It never imports or calls agent-facing tools
(`measure_node`, `observe_fit`) or engine code.
"""

from __future__ import annotations

import base64
import re
import struct
from typing import Any

from open_apprentice.campaign.limits import (
    MIN_CTA_H,
    MIN_FONT,
    MIN_HERO_W,
    MIN_LEGAL_FONT,
    SAFE,
    STORY_H,
    STORY_W,
)
from open_apprentice.evaluation.text_layout import _manifest, fit
from open_apprentice.evaluation.verifier import VerifierReport

GOLD_TOL_PX = 2.0
ASPECT_REL_TOL = 0.005
ORDER = ("brand_mark", "product_image", "headline", "price", "cta", "legal")
COPY_ROLES = ("headline", "price", "legal")
WRITABLE = {
    "x",
    "y",
    "width",
    "height",
    "scaleX",
    "scaleY",
    "parent",
    "z",
    "fontSize",
    "cornerRadius",
}
CARD_ONLY = {"format", "safe", "sequence"}
Node = dict[str, Any]
Box = tuple[float, float, float, float]


def _cards(nodes: list[Node]) -> list[Node]:
    return sorted((n for n in nodes if n["type"] == "artboard"), key=lambda n: n.get("sequence", 0))


def _children(nodes: list[Node], pid: str) -> list[Node]:
    return [n for n in nodes if n.get("parent") == pid]


def _local(nodes: list[Node], n: Node) -> tuple[float, float]:
    """Top-left of n in its parent's top-left frame. Konva states are already there; Fabric keeps a group child's
    left/top in the group's centre frame ("group_center"), so the parent's half size is added back here.
    """
    if n.get("frame") == "group_center":
        parent = next(p for p in nodes if p["id"] == n["parent"])
        return n["x"] + parent["width"] / 2, n["y"] + parent["height"] / 2
    return n["x"], n["y"]


def _box(nodes: list[Node], n: Node) -> Box:
    """Bounds in the coordinates of n's parent (top-left frame); a group is the union of its children."""
    sx, sy = n.get("scaleX", 1), n.get("scaleY", 1)
    x, y = _local(nodes, n)
    if n["type"] == "group":
        kids = [_box(nodes, k) for k in _children(nodes, n["id"])]
        if not kids:
            return (x, y, 0.0, 0.0)
        x0, y0 = min(k[0] for k in kids), min(k[1] for k in kids)
        x1, y1 = max(k[0] + k[2] for k in kids), max(k[1] + k[3] for k in kids)
        return (x + x0 * sx, y + y0 * sy, (x1 - x0) * sx, (y1 - y0) * sy)
    return (x, y, n["width"] * sx, n["height"] * sy)


def _scale(nodes: list[Node], n: Node | None) -> tuple[float, float]:
    """Effective scale of n inside its card: its own scale times every ancestor group's (the card itself is unscaled)."""
    by_id = {m["id"]: m for m in nodes}
    sx = sy = 1.0
    while n is not None and n["type"] != "artboard":
        sx, sy = sx * n.get("scaleX", 1), sy * n.get("scaleY", 1)
        n = by_id.get(n.get("parent"))
    return sx, sy


def _font_px(nodes: list[Node], n: Node) -> float:
    return n["fontSize"] * _scale(nodes, n)[1]


def _roled(nodes: list[Node], card: Node) -> dict[str, list[Node]]:
    out: dict[str, list[Node]] = {}
    for n in _children(nodes, card["id"]):
        if n.get("role") and n["role"] != "background":
            out.setdefault(n["role"], []).append(n)
    return out


def _cta_label(nodes: list[Node], cta: Node) -> Node | None:
    return next((n for n in _children(nodes, cta["id"]) if n["type"] == "text"), None)


def _copy(nodes: list[Node]) -> dict[str, str]:
    out = {
        n["role"]: n["text"] for n in nodes if n.get("role") in COPY_ROLES and n["type"] == "text"
    }
    cta = next((n for n in nodes if n.get("role") == "cta"), None)
    label = _cta_label(nodes, cta) if cta else None
    if label:
        out["cta_label"] = label["text"]
    return out


def _source_id(fid: str, source_ids: set[str]) -> str | None:
    if fid in source_ids:
        return fid
    if (
        fid.endswith("-2") and fid[:-2] in source_ids
    ):  # the card-2 copy of a repeated node (brand mark, background)
        return fid[:-2]
    return None


def _intersects(a: Box, b: Box) -> bool:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w > 0 and h > 0


_UPLOAD_ID = re.compile(r"u-[0-9a-f]{12}-(brand_mark|product_image)")


def uploaded_sizes(raw: dict | None) -> dict[str, dict]:
    """Natural size of each uploaded crop, read from its PNG header here (not through the agent's or the engine's code).
    Anything that is not a PNG data URL under an upload id is left out, so image_aspect fails for it."""
    out: dict[str, dict] = {}
    for aid, url in (raw or {}).items():
        prefix = "data:image/png;base64,"
        if not _UPLOAD_ID.fullmatch(aid) or not isinstance(url, str) or not url.startswith(prefix):
            continue
        try:
            head = base64.b64decode(url[len(prefix) : len(prefix) + 64], validate=False)
        except ValueError:
            continue
        if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            w, h = struct.unpack(">II", head[16:24])
            if w > 0 and h > 0:
                out[aid] = {"width": w, "height": h}
    return out


def verify_story(
    source: dict, final_native: dict, gold: dict | None, *, gold_applies: bool = True
) -> VerifierReport:
    """Judge a committed story-card result. `source` is the banner scene, `gold` the authored expected scene (None when the
    chosen outcome is not applicable, which always fails). `gold_applies=False` is for a reading the gold was not written
    for (the owner's "scale like the example" choice): matches_gold is then left out, never counted as passed."""
    rep = VerifierReport()
    src, fin = source["nodes"], final_native["nodes"]
    cards = _cards(fin)
    by_card = {c["id"]: _roled(fin, c) for c in cards}
    texts = [n for n in fin if n["type"] == "text"]
    images = [n for n in fin if n["type"] == "image"]
    assets = {
        k.split("/", 1)[1].rsplit(".", 1)[0]: v
        for k, v in _manifest()["files"].items()
        if k.startswith("assets/")
    }
    assets |= uploaded_sizes(source.get("assets"))

    want, got = _copy(src), _copy(fin)
    rep.add(
        "exact_copy",
        want == got,
        "" if want == got else f"{sorted(k for k in want if want[k] != got.get(k))}",
    )

    counts = {k: sum(1 for t in texts if t["text"] == v) for k, v in want.items()}
    rep.add("copy_once", all(c == 1 for c in counts.values()), str(counts))

    src_cta = next(n for n in src if n.get("role") == "cta")
    ctas = [n for n in fin if n.get("role") == "cta"]
    rep.add(
        "link_preserved",
        len(ctas) == 1 and ctas[0].get("link") == src_cta.get("link"),
        str([c.get("link") for c in ctas]),
    )

    logo = next(n for n in src if n.get("role") == "brand_mark")["asset"]
    marks = [by_card[c["id"]].get("brand_mark", []) for c in cards]
    rep.add(
        "logo_preserved",
        bool(cards) and all(len(m) == 1 and m[0].get("asset") == logo for m in marks),
        str(marks),
    )

    bad_aspect = []
    for n in images:
        a = assets.get(n.get("asset"))
        sx, sy = _scale(fin, n)
        h = n["height"] * sy
        if (
            a is None
            or h == 0
            or abs((n["width"] * sx / h) / (a["width"] / a["height"]) - 1) > ASPECT_REL_TOL
        ):
            bad_aspect.append(n["id"])
    rep.add("image_aspect", not bad_aspect, str(bad_aspect))
    rep.add(
        "image_uncropped",
        all(n.get("crop") is None for n in images),
        str([n["id"] for n in images if n.get("crop")]),
    )

    hidden = []
    for n in images:
        a, card = assets.get(n.get("asset")), next(
            (c for c in cards if c["id"] == n.get("parent")), None
        )
        f = n.get("focal")
        if a is None or card is None or f is None:
            hidden.append(n["id"])
            continue
        sx, sy = _scale(fin, n)
        lx, ly = _local(fin, n)
        fx = lx + f["x"] * n["width"] * sx / a["width"]
        fy = ly + f["y"] * n["height"] * sy / a["height"]
        if not (0 <= fx <= card["width"] and 0 <= fy <= card["height"]):
            hidden.append(n["id"])
    rep.add("focal_visible", not hidden, str(hidden))

    misordered = []
    for c in cards:
        tops = [(r, _box(fin, by_card[c["id"]][r][0])[1]) for r in ORDER if by_card[c["id"]].get(r)]
        if any(a[1] >= b[1] for a, b in zip(tops, tops[1:])):
            misordered.append(c["id"])
    rep.add("role_order", not misordered, str(misordered))

    seqs = [c.get("sequence") for c in cards]
    shaped = all(
        (c["width"], c["height"], c.get("format"), c.get("safe"))
        == (STORY_W, STORY_H, "9:16", SAFE)
        for c in cards
    )
    rep.add(
        "card_sequence",
        bool(cards) and seqs == list(range(1, len(cards) + 1)) and shaped,
        str(seqs),
    )

    outside = []
    for c in cards:
        sf = SAFE  # the frozen limits, never the result's own metadata
        for nodes in by_card[c["id"]].values():
            for n in nodes:
                x, y, w, h = _box(fin, n)
                if x < sf.get("left", 0) or y < sf.get("top", 0):
                    outside.append(n["id"])
                elif x + w > c["width"] - sf.get("right", 0) or y + h > c["height"] - sf.get(
                    "bottom", 0
                ):
                    outside.append(n["id"])
    rep.add("inside_safe", not outside, str(outside))

    small = []
    for c in cards:
        roles = by_card[c["id"]]
        for r in ("headline", "price"):
            small += [n["id"] for n in roles.get(r, []) if _font_px(fin, n) < MIN_FONT]
        small += [n["id"] for n in roles.get("legal", []) if _font_px(fin, n) < MIN_LEGAL_FONT]
        small += [n["id"] for n in roles.get("product_image", []) if _box(fin, n)[2] < MIN_HERO_W]
        for cta in roles.get("cta", []):
            label = _cta_label(fin, cta)
            if _box(fin, cta)[3] < MIN_CTA_H or label is None or _font_px(fin, label) < MIN_FONT:
                small.append(cta["id"])
    rep.add("minimum_sizes", not small, str(small))

    overflow = []
    for t in texts:
        f = fit(
            t["text"],
            t["width"],
            t["fontSize"],
            t.get("fontStyle") == "bold",
            t.get("lineHeight", 1),
        )
        if f.word_too_wide or f.height > t["height"]:
            overflow.append(t["id"])
    rep.add("text_fits", not overflow, str(overflow))

    overlapping = []
    for c in cards:
        flat = [n for nodes in by_card[c["id"]].values() for n in nodes]
        for i, a in enumerate(flat):
            overlapping += [
                (a["id"], b["id"]) for b in flat[i + 1 :] if _intersects(_box(fin, a), _box(fin, b))
            ]
    rep.add("no_overlap", not overlapping, str(overlapping))

    src_by_id = {n["id"]: n for n in src}
    changed = []
    for n in fin:
        if n["type"] == "artboard":
            continue
        sid = _source_id(n["id"], set(src_by_id))
        if sid is None:
            changed.append(f"{n['id']}: not in the source")
            continue
        for k, v in src_by_id[sid].items():
            if k not in WRITABLE and k not in CARD_ONLY and k != "id" and n.get(k) != v:
                changed.append(f"{n['id']}.{k}")
    rep.add("non_writable_unchanged", not changed, str(changed[:10]))

    if not gold_applies:
        pass
    elif gold is None:
        rep.add(
            "matches_gold", False, "no gold: the chosen outcome is not applicable to this banner"
        )
    else:
        fin_by_id = {n["id"]: n for n in fin}
        off = [] if set(fin_by_id) == {n["id"] for n in gold["nodes"]} else ["node set differs"]
        for g in gold["nodes"]:
            n = fin_by_id.get(g["id"])
            if n is None:
                continue
            x, y = _local(fin, n)
            eff = {"x": x, "y": y}
            if (
                n["type"] != "group"
            ):  # effective size: Fabric keeps images at natural size and carries the scale
                eff |= {
                    "width": n["width"] * n.get("scaleX", 1),
                    "height": n["height"] * n.get("scaleY", 1),
                }
            for k, v in eff.items():
                if k in g and abs(v - g[k]) > GOLD_TOL_PX:
                    off.append(f"{g['id']}.{k}")
            for k in ("parent", "fontSize", "cornerRadius", "sequence"):
                if k in g and n.get(k) != g[k]:
                    off.append(f"{g['id']}.{k}")
        rep.add("matches_gold", not off, str(off[:10]))
    return rep
