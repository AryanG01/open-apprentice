"""Does Nemotron VL read a banner image well enough to help? Renders banners through the real engine, asks the vision model
for their layers and scores role, box overlap and words against the banner's own layers (the fixtures' authored nodes).

The decision rule below is fixed before any live run; see docs/evaluation/campaign_vision_protocol.md."""

from __future__ import annotations

import statistics
from typing import Any

from open_apprentice.budget import Ledger, Limits
from open_apprentice.campaign.fixtures import load_fixture
from open_apprentice.campaign.vision import (
    IMAGE_ROLES,
    LAYER_ROLES,
    TEXT_ROLES,
    LayerProposal,
    propose_layers,
)
from open_apprentice.evaluation.harness import EvaluatorHarness
from open_apprentice.providers.base import Provider

DEV_BANNERS = ("teach_before", "short_a", "short_b", "de_long_a", "de_long_b", "fr_long")
OWNER = "campaign-vision"
MATCH_IOU = 0.5  # a layer counts as found when its box overlaps the true one at least this much
GO_BANNERS, GO_MEDIAN_IOU = (
    5,
    0.6,
)  # of 6 banners fully matched, and the median box overlap of the text layers
PARTIAL_BANNERS, PARTIAL_TEXT = (
    5,
    0.7,
)  # roles named right on 5 of 6 and 70% of the words read exactly


def norm(s: str) -> str:
    return " ".join((s or "").split())


def iou(a: list[float], b: list[float]) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    inter = w * h if w > 0 and h > 0 else 0.0
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def banner_frame(scene: dict) -> tuple[float, float]:
    """The banner artboard's size: the fixtures are not all 1280 x 720, and a model's boxes are relative to the image."""
    b = next(n for n in scene["nodes"] if n["type"] == "artboard")
    return float(b["width"]), float(b["height"])


def contained(box: list[float], frame: list[float]) -> float:
    """Share of `box` that lies inside `frame` (1.0 = fully inside)."""
    w = min(box[0] + box[2], frame[0] + frame[2]) - max(box[0], frame[0])
    h = min(box[1] + box[3], frame[1] + frame[3]) - max(box[1], frame[1])
    area = box[2] * box[3]
    return (w * h) / area if w > 0 and h > 0 and area > 0 else 0.0


def gold_layers(scene: dict) -> dict[str, dict]:
    """role -> {box, text, font_px} from the banner's own authored nodes (the button's box is its plate)."""
    nodes = scene["nodes"]
    out: dict[str, dict] = {}
    for n in nodes:
        r = n.get("role")
        if n.get("parent") != "banner" or r not in LAYER_ROLES:
            continue
        if r == "cta":
            plate = next(k for k in nodes if k.get("parent") == n["id"] and k["type"] == "shape")
            label = next(k for k in nodes if k.get("parent") == n["id"] and k["type"] == "text")
            out[r] = {
                "box": [n["x"], n["y"], plate["width"], plate["height"]],
                "text": label["text"],
                "font_px": label["fontSize"],
            }
        else:
            out[r] = {
                "box": [n["x"], n["y"], n["width"], n["height"]],
                "text": n.get("text", ""),
                "font_px": n.get("fontSize", 0),
            }
    return out


def score_case(
    proposal: LayerProposal, gold: dict[str, dict], frame: tuple[float, float] = (1280, 720)
) -> dict[str, Any]:
    """`frame` is the banner's size in the gold's units; proposal boxes are pixels of a 1280 x 720 banner and are scaled to it."""
    kx, ky = frame[0] / 1280, frame[1] / 720
    by: dict[str, list] = {}
    for l in proposal.layers:
        by.setdefault(l.role, []).append(l)
    scores, inside, text_hits = {}, {}, 0
    for r, g in gold.items():
        got = by.get(r, [])
        one = len(got) == 1 and len(got[0].box) == 4
        box = (
            [got[0].box[0] * kx, got[0].box[1] * ky, got[0].box[2] * kx, got[0].box[3] * ky]
            if one
            else None
        )
        scores[r] = iou(box, g["box"]) if one else 0.0
        inside[r] = contained(box, g["box"]) if one else 0.0
        if r in TEXT_ROLES and len(got) == 1 and norm(got[0].text) == norm(g["text"]):
            text_hits += 1
    return {
        "roles_present": set(by) == set(gold) and all(len(v) == 1 for v in by.values()),
        "all_matched": all(s >= MATCH_IOU for s in scores.values()),
        "iou": {r: round(s, 3) for r, s in scores.items()},
        "inside": {
            r: round(s, 3) for r, s in inside.items()
        },  # POST HOC: not part of the registered rule
        "text_exact": text_hits,
        "text_roles": sum(r in TEXT_ROLES for r in gold),
        "origin": proposal.origin,
        "problems": proposal.problems,
    }


def verdict(cases: list[dict]) -> dict[str, Any]:
    n = len(cases)
    matched = sum(c["all_matched"] for c in cases)
    present = sum(c["roles_present"] for c in cases)
    text_ious = [c["iou"][r] for c in cases for r in TEXT_ROLES if r in c["iou"]]
    median = statistics.median(text_ious) if text_ious else 0.0
    inside = [c["inside"][r] for c in cases for r in TEXT_ROLES if r in c.get("inside", {})]
    words = sum(c["text_exact"] for c in cases) / max(1, sum(c["text_roles"] for c in cases))
    if matched >= min(GO_BANNERS, n) and median >= GO_MEDIAN_IOU:
        decision = "go"
    elif present >= min(PARTIAL_BANNERS, n) and words >= PARTIAL_TEXT:
        decision = "partial"
    else:
        decision = "no-go"
    return {
        "banners": n,
        "all_matched": matched,
        "roles_present": present,
        "median_text_iou": round(median, 3),
        "words_exact": round(words, 3),
        "median_text_inside": round(statistics.median(inside), 3) if inside else None,  # post hoc
        "decision": decision,
    }


def rescore(rows: list[dict]) -> list[dict]:
    """Score stored replies again (no model call): rebuilds each proposal from the raw reply and applies the current scoring."""
    from open_apprentice.campaign.vision import check_layers, from_vision

    out = []
    for r in rows:
        scene = load_fixture(r["banner"])["scene"]
        gold = gold_layers(scene)
        if r.get("raw"):
            proposal = from_vision(r["raw"])
            proposal.problems = check_layers(proposal.layers)
        else:  # the manual template was used: nothing the model said
            proposal = LayerProposal([], "en", "manual", note=r.get("note", ""))
        out.append(
            {
                **r,
                "frame": list(banner_frame(scene)),
                "score": score_case(proposal, gold, banner_frame(scene)),
            }
        )
    return out


def render_png(harness: EvaluatorHarness, scene: dict) -> str:
    session = harness.open_session(scene, OWNER)[0]
    try:
        return session.call("export_scene", format="png")["data_url"]
    finally:
        session.close()


async def run_dev(provider: Provider | None, engine_url: str, token: str) -> list[dict]:
    harness = EvaluatorHarness(engine_url, token)
    ledger = Ledger(Limits(tokens=400_000, calls=12))
    rows = []
    for fid in DEV_BANNERS:
        scene = load_fixture(fid)["scene"]
        png = render_png(harness, scene)
        proposal = await propose_layers(provider, ledger, png)
        gold = gold_layers(scene)
        rows.append(
            {
                "banner": fid,
                "gold": gold,
                "proposed": [l.model_dump() for l in proposal.layers],
                "raw": proposal.raw,
                "note": proposal.note,
                "tokens": proposal.tokens,
                "frame": list(banner_frame(scene)),
                "score": score_case(proposal, gold, banner_frame(scene)),
            }
        )
    return rows


def render_markdown(rows: list[dict], *, model: str, spent_usd: float, calls: int) -> str:
    v = verdict([r["score"] for r in rows])
    lines = [
        "# Reading a banner image: development probe",
        "",
        f"Model `{model}` · {len(rows)} development banners rendered by the real engine · {calls} calls · ${spent_usd:.3f} (ledger). "
        "Development fixtures, not held out; one run, no retries.",
        "",
        f"**Decision: {v['decision']}** (rule fixed beforehand: go = {GO_BANNERS} of 6 banners with every layer found at box overlap "
        f"≥ {MATCH_IOU} and median text-layer overlap ≥ {GO_MEDIAN_IOU}; partial = roles named right on {PARTIAL_BANNERS} of 6 and ≥ "
        f"{int(PARTIAL_TEXT * 100)}% of words exact).",
        "",
        f"- Every layer found on **{v['all_matched']} of {v['banners']}** banners; all six roles named once on {v['roles_present']}.",
        f"- Median box overlap of the text layers: **{v['median_text_iou']}**; words read exactly: **{v['words_exact']}**.",
        "",
        "| banner | roles named | all found | "
        + " | ".join(f"{r} IoU" for r in LAYER_ROLES)
        + " | words exact | origin |",
        "|---|---|---|" + "---|" * len(LAYER_ROLES) + "---|---|",
    ]
    for r in rows:
        s = r["score"]
        lines.append(
            f"| {r['banner']} | {'yes' if s['roles_present'] else 'no'} | {'yes' if s['all_matched'] else 'no'} | "
            + " | ".join(str(s["iou"].get(role, "-")) for role in LAYER_ROLES)
            + f" | {s['text_exact']}/{s['text_roles']} | {s['origin']} |"
        )
    return "\n".join(lines) + "\n"
