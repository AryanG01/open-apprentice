"""Behaviour specs beyond the 24-program catalogue, and scene strata, for the Plan 5 battery (evaluator side).

`oracle_v` is plain Python and shares no code with `concepts/rules`: a learner's program is judged against an
implementation it never sees. Every oracle returns the final (x, y) of the labels it moves and never moves a node.
Agent-visible modules must not import this file.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction as F
from typing import Any

from open_apprentice.evaluation.label_episodes import _unsupported_oracle
from open_apprentice.evaluation.labels import _blocked, _box, make_scene, oracle, pose

KINDS = ("catalogue", "gap_by_width", "role_sides", "fallback_chain", "size_side", "unobservable")
STRATA = ("grid", "rows", "columns", "sparse", "narrow")


@dataclass(frozen=True)
class VSpec:
    """kind + params. catalogue: (labels.Spec,); gap_by_width: (); role_sides / fallback_chain / size_side: (gap,);
    unobservable: (hidden key,)."""

    kind: str
    params: tuple


def _pose_v(side: str, anchor: dict, label: dict, gap: F) -> tuple[F, F]:
    if side != "left":
        return pose(side, anchor, label, gap)
    xa, ya, _, ha = _box(anchor)
    return xa - gap - F(label["w"]), ya + (ha - F(label["h"])) / 2


def oracle_v(spec: VSpec, scene: dict) -> dict[str, tuple[F, F]]:
    if spec.kind == "catalogue":
        return oracle(spec.params[0], scene)
    if spec.kind == "unobservable":
        return _unsupported_oracle(scene, spec.params[0])
    if spec.kind not in KINDS:
        raise ValueError(f"unknown spec kind {spec.kind!r}")
    objs = scene["objects"]
    byid = {o["id"]: o for o in objs}
    out: dict[str, tuple[F, F]] = {}
    for lab in objs:
        if lab["kind"] != "label":
            continue
        a = byid[lab["attached"]]
        if spec.kind == "gap_by_width":
            out[lab["id"]] = pose("right", a, lab, min(F(24), max(F(8), F(a["w"]) / 10)))
            continue
        gap = F(spec.params[0])
        if spec.kind == "role_sides":
            out[lab["id"]] = pose("below" if lab["role"] == "warning" else "right", a, lab, gap)
        elif spec.kind == "size_side":
            out[lab["id"]] = pose("right" if F(a["w"]) > F(a["h"]) else "below", a, lab, gap)
        else:  # fallback_chain: right, then below, then left regardless
            for side in ("right", "below", "left"):
                px, py = _pose_v(side, a, lab, gap)
                box = (px, py, F(lab["w"]), F(lab["h"]))
                if side == "left" or not _blocked(box, lab, a, objs, scene["canvas"]):
                    break
            out[lab["id"]] = (px, py)
    return out


def _objects(
    rng: random.Random, slots: list[tuple[int, int]], warnings: int
) -> list[dict[str, Any]]:
    """One node per slot (top-left, jittered) and one label per node, parked just under it."""
    nodes, labels = [], []
    warn = set(rng.sample(range(len(slots)), min(warnings, len(slots))))
    for i, (x, y) in enumerate(slots):
        w, h = rng.choice((50, 70, 90, 140)), rng.choice((40, 60, 80))
        n = {
            "id": f"n{i}",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": x + rng.randrange(0, 20),
            "y": y + rng.randrange(0, 20),
            "w": w,
            "h": h,
        }
        nodes.append(n)
        labels.append(
            {
                "id": f"l{i}",
                "kind": "label",
                "role": "warning" if i in warn else "note",
                "attached": n["id"],
                "x": n["x"],
                "y": n["y"] + h + 4,
                "w": rng.choice((40, 56, 80)),
                "h": rng.choice((16, 20)),
            }
        )
    return nodes + labels


def scene_v(stratum: str, seed: int) -> dict:
    """A deterministic document for one stratum. Every object starts inside the page."""
    rng = random.Random(f"{stratum}/{seed}")
    if stratum == "grid":
        return make_scene(seed, rng.randrange(6, 11), warnings=rng.randrange(1, 4))
    if stratum == "narrow":
        return make_scene(seed, rng.randrange(4, 8), warnings=rng.randrange(1, 3), canvas_w=600)
    if stratum == "rows":
        slots = [
            (40 + c * 225, 120 + r * 320) for r in range(2) for c in range(rng.randrange(3, 6))
        ]
    elif stratum == "columns":
        slots = [(60 + c * 400, 40 + r * 180) for c in range(3) for r in range(rng.randrange(2, 5))]
    elif stratum == "sparse":
        cells = [(80 + c * 400, 80 + r * 400) for c in range(3) for r in range(2)]
        slots = rng.sample(cells, rng.randrange(2, 5))
    else:
        raise ValueError(f"unknown stratum {stratum!r}")
    return {"objects": _objects(rng, slots, rng.randrange(1, 3)), "canvas": {"w": 1200, "h": 800}}
