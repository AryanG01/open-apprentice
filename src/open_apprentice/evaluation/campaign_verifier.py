"""Independent verifier for a promo banner turned story card (spec 7.7).

Reads the source scene, the PRIVATE native state of the result, and the authored gold scene. It recomputes everything itself:
geometry from raw node attrs, text fit from the font tables (`text_layout`). It never imports or calls agent-facing tools
(`measure_node`, `observe_fit`) or engine code.
"""

from __future__ import annotations

from typing import Any

from open_apprentice.campaign.limits import (
    MIN_CTA_H,
    MIN_FONT,
    MIN_HERO_W,
    MIN_LEGAL_FONT,
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


def _box(nodes: list[Node], n: Node) -> Box:
    """Bounds in the coordinates of n's parent; a group is the union of its children."""
    sx, sy = n.get("scaleX", 1), n.get("scaleY", 1)
    if n["type"] == "group":
        kids = [_box(nodes, k) for k in _children(nodes, n["id"])]
        if not kids:
            return (n["x"], n["y"], 0.0, 0.0)
        x0, y0 = min(k[0] for k in kids), min(k[1] for k in kids)
        x1, y1 = max(k[0] + k[2] for k in kids), max(k[1] + k[3] for k in kids)
        return (n["x"] + x0 * sx, n["y"] + y0 * sy, (x1 - x0) * sx, (y1 - y0) * sy)
    return (n["x"], n["y"], n["width"] * sx, n["height"] * sy)


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


def verify_story(source: dict, final_native: dict, gold: dict | None) -> VerifierReport:
    """Judge a committed story-card result. `source` is the banner scene, `gold` the authored expected scene (None when the
    chosen outcome is not applicable, which always fails)."""
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
        if (
            a is None
            or n["height"] == 0
            or abs((n["width"] / n["height"]) / (a["width"] / a["height"]) - 1) > ASPECT_REL_TOL
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
        fx, fy = (
            n["x"] + f["x"] * n["width"] / a["width"],
            n["y"] + f["y"] * n["height"] / a["height"],
        )
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
        (c["width"], c["height"], c.get("format")) == (STORY_W, STORY_H, "9:16") for c in cards
    )
    rep.add(
        "card_sequence",
        bool(cards) and seqs == list(range(1, len(cards) + 1)) and shaped,
        str(seqs),
    )

    outside = []
    for c in cards:
        sf = c.get("safe") or {}
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
            small += [n["id"] for n in roles.get(r, []) if n["fontSize"] < MIN_FONT]
        small += [n["id"] for n in roles.get("legal", []) if n["fontSize"] < MIN_LEGAL_FONT]
        small += [n["id"] for n in roles.get("product_image", []) if _box(fin, n)[2] < MIN_HERO_W]
        for cta in roles.get("cta", []):
            label = _cta_label(fin, cta)
            if _box(fin, cta)[3] < MIN_CTA_H or label is None or label["fontSize"] < MIN_FONT:
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

    if gold is None:
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
            for k in ("x", "y", "width", "height"):
                if k in g and abs(n.get(k, 0) - g[k]) > GOLD_TOL_PX:
                    off.append(f"{g['id']}.{k}")
            for k in ("parent", "fontSize", "cornerRadius", "sequence"):
                if k in g and n.get(k) != g[k]:
                    off.append(f"{g['id']}.{k}")
        rep.add("matches_gold", not off, str(off[:10]))
    return rep
