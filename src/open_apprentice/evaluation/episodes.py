"""Evaluator-owned episode manifests (spec 21.1, 21.10-21.11). PRIVATE: agent-visible code must never import
this module (import-linter contract). Latent rules, template names and the drift schedule live only here.

Structure per episode: two concepts (spacing + badge), eight scored tasks:
  2 same-backend, 2 transfer (other backend), 2 composition, 2 'recovery' layouts after the allowed tool change.
Splits are by TEMPLATE (rule structure / operator combination) and by object-size range, never by random id;
exact scenes never repeat across splits. 4 of 12 episodes are no-change controls.
Held-out structure available on the declared common subset: rule templates, operator combinations, size
ranges, card counts. Nesting is NOT held out because the Fabric subset has no groups (documented limit).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from fractions import Fraction as F
from typing import Any, Optional

from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.concepts.schemas import canonical, sha

STAGES = (
    "same_backend",
    "same_backend",
    "transfer",
    "transfer",
    "composition",
    "composition",
    "recovery",
    "recovery",
)
# Rule-structure templates per split (disjoint). 'clamp' and 'affine' are operator combinations never seen in dev.
BADGE_TEMPLATES = {
    "development": ("const", "prop", "min"),
    "validation": ("max",),
    "final": ("clamp", "affine"),
}
SPACING_TEMPLATES = {
    "development": ("edge",),
    "validation": ("pitch",),
    "final": ("edge_wide", "pitch_wide"),
}
WIDTH_RANGE = {
    "development": (40, 121),
    "validation": (130, 201),
    "final": (24, 40),
}  # card widths; final ALSO draws 200-400
MAX_ROW_PX = 1000  # total card width per row, so rules' outputs stay on canvas
CANVAS = {"w": F(1400), "h": F(700)}
DRIFT = {
    "fabric": {"move_origin": "center"},
    "konva": {"move_anchor": "center"},
}  # artificial intervention, one family


def _lit(f: F) -> Any:
    return int(f) if f.denominator == 1 else {"rat": f"{f.numerator}/{f.denominator}"}


def _op(n: str, *a: Any) -> dict:
    return {"op": n, "args": list(a)}


def _w(i: int = 0) -> dict:
    return _op("get", {"ref": f"objects.{i}"}, "w")


def badge_latent(template: str, rng: random.Random) -> tuple[list, dict]:
    r = F(rng.choice([2, 3, 4, 5, 6, 8, 10]), 100)
    c = F(rng.choice([6, 8, 10, 12, 16]))
    lo, hi = F(rng.choice([6, 8, 10])), F(rng.choice([20, 24, 28]))
    k = F(rng.choice([2, 3, 4, 5]))
    margin = {
        "const": _lit(c),
        "prop": _op("mul", _w(), _lit(r)),
        "min": _op("min", _op("mul", _w(), _lit(r)), _lit(c + 8)),
        "max": _op("max", _op("mul", _w(), _lit(r)), _lit(c)),
        "clamp": _op("min", _lit(hi), _op("max", _lit(lo), _op("mul", _w(), _lit(r)))),
        "affine": _op("add", _op("mul", _w(), _lit(r)), _lit(k)),
    }[template]
    card, proto = {"ref": "objects.0"}, {"ref": "objects.1"}
    rule = [
        {"op": "let", "name": "m", "value": margin},
        {
            "op": "emit_target",
            "kind": "clone_place",
            "proto": proto,
            "symbol": "badge",
            "x": _op(
                "sub",
                _op("add", _op("get", card, "x"), _w()),
                _op("add", {"ref": "locals.m"}, _op("get", proto, "w")),
            ),
            "y": _op("add", _op("get", card, "y"), {"ref": "locals.m"}),
        },
    ]
    return rule, {"template": template}


def spacing_latent(template: str, rng: random.Random) -> tuple[list, dict]:
    left, top = F(rng.choice([40, 60, 80])), F(rng.choice([60, 100, 120]))
    R = lambda p: {"ref": p}
    if template.startswith("edge"):
        g = F(rng.choice([24, 32, 40]) if template == "edge_wide" else rng.choice([12, 16, 20]))
        rule = [
            {"op": "let", "name": "cursor", "value": _lit(left)},
            {
                "op": "for_each",
                "var": "o",
                "over": R("objects"),
                "body": [
                    {
                        "op": "emit_target",
                        "kind": "move_existing",
                        "target": R("locals.o"),
                        "x": R("locals.cursor"),
                        "y": _lit(top),
                    },
                    {
                        "op": "let",
                        "name": "cursor",
                        "value": _op(
                            "add",
                            R("locals.cursor"),
                            _op("add", _op("get", R("locals.o"), "w"), _lit(g)),
                        ),
                    },
                ],
            },
        ]
    else:
        p = F(
            rng.choice([150, 170, 190]) if template == "pitch_wide" else rng.choice([100, 120, 140])
        )
        rule = [
            {"op": "let", "name": "c", "value": _op("add", _lit(left), _op("div", _w(), 2))},
            {
                "op": "for_each",
                "var": "o",
                "over": R("objects"),
                "body": [
                    {
                        "op": "emit_target",
                        "kind": "move_existing",
                        "target": R("locals.o"),
                        "x": _op(
                            "sub", R("locals.c"), _op("div", _op("get", R("locals.o"), "w"), 2)
                        ),
                        "y": _lit(top),
                    },
                    {"op": "let", "name": "c", "value": _op("add", R("locals.c"), _lit(p))},
                ],
            },
        ]
    return rule, {"template": template}


def _widths(split: str, rng: random.Random, n: int) -> list[int]:
    lo, hi = WIDTH_RANGE[split]
    out = []
    for _ in range(n):
        if split == "final" and rng.random() < 0.5:
            out.append(rng.randrange(200, 401, 10))  # held-out LARGE sizes too
        else:
            out.append(rng.randrange(lo, hi, 10))
    while (
        sum(out) > MAX_ROW_PX
    ):  # keep rows on the canvas without changing the size distribution's shape
        i = out.index(max(out))
        out[i] = max(24, out[i] - 10)
    return out


def make_cards(split: str, rng: random.Random, n: int) -> list[dict]:
    ws = _widths(split, rng, n)
    x, objs = 10, []
    for i, w in enumerate(ws):
        objs.append(
            {
                "id": f"card{i}",
                "x": F(x),
                "y": F(rng.randrange(300, 420, 10)),
                "w": F(w),
                "h": F(rng.randrange(40, 100, 10)),
            }
        )
        x += w + rng.randrange(10, 40, 10)
    return objs


@dataclass(frozen=True)
class Task:
    task_id: str
    stage: str  # PRIVATE (a 'recovery' label would reveal the change)
    kind: str  # spacing | badge | composition
    backend: str
    scene: dict  # canonical scene: objects (cards..., proto, bystander) + canvas
    selected: tuple[str, ...]
    proto: str = "proto"


@dataclass
class Episode:
    episode_id: str
    split: str
    index: int
    source_backend: str
    target_backend: str
    spacing: list  # PRIVATE latent
    badge: list  # PRIVATE latent
    templates: dict  # PRIVATE
    demos: dict  # {"spacing": demo, "badge": demo} teacher-provided demonstrations
    drift: Optional[dict]  # PRIVATE; applied from the 'recovery' stage onward on the target backend
    tasks: list[Task] = field(default_factory=list)


def _scene(cards: list[dict], rng: random.Random) -> dict:
    return {
        "objects": cards
        + [
            {"id": "proto", "x": F(1300), "y": F(20), "w": F(20), "h": F(20)},
            {"id": "bystander", "x": F(1300), "y": F(640), "w": F(50), "h": F(40)},
        ],
        "canvas": CANVAS,
    }


def make_episode(split: str, seed: int, index: int, drift: bool) -> Episode:
    rng = random.Random(f"{split}:{seed}:{index}")
    bt = BADGE_TEMPLATES[split][index % len(BADGE_TEMPLATES[split])]
    st = SPACING_TEMPLATES[split][index % len(SPACING_TEMPLATES[split])]
    badge, _ = badge_latent(bt, rng)
    spacing, _ = spacing_latent(st, rng)
    src, dst = ("konva", "fabric") if index % 2 == 0 else ("fabric", "konva")
    ep_id = "ep-" + hashlib.sha256(f"{split}{seed}{index}".encode()).hexdigest()[:10]

    # teacher demonstrations (one example each)
    dc = make_cards(split, rng, 3)[:3]
    sp_scene = {"objects": dc, "canvas": CANVAS}
    bd_card = [dict(dc[0]), {"id": "proto", "x": F(0), "y": F(0), "w": F(20), "h": F(20)}]
    bd_scene = {"objects": bd_card, "canvas": CANVAS}
    demos = {
        "spacing": {"scene": sp_scene, "after": evaluate_rule(spacing, dc, CANVAS)},
        "badge": {"scene": bd_scene, "after": evaluate_rule(badge, bd_card, CANVAS)},
    }

    tasks = []
    for k, stage in enumerate(STAGES):
        n = 3 + (k % 3)  # 3..5 cards
        cards = make_cards(split, rng, n)
        kind = "composition" if stage == "composition" else ("spacing" if k % 2 == 0 else "badge")
        backend = src if stage == "same_backend" else dst
        tid = "t-" + hashlib.sha256(f"{ep_id}{k}{kind}".encode()).hexdigest()[:10]
        tasks.append(
            Task(tid, stage, kind, backend, _scene(cards, rng), tuple(c["id"] for c in cards))
        )
    return Episode(
        ep_id,
        split,
        index,
        src,
        dst,
        spacing,
        badge,
        {"badge": bt, "spacing": st},
        demos,
        DRIFT[dst] if drift else None,
        tasks,
    )


def drift_flags(n: int = 12) -> list[bool]:
    """4 no-change controls and 8 drift episodes, balanced across backend direction (even/odd index)."""
    flags = [True] * n
    for i in (0, 1, 6, 7)[: max(0, n // 3)]:  # two no-change controls per direction
        flags[i] = False
    return flags


@dataclass
class Manifest:
    split: str
    seed: int
    episodes: list[Episode]
    frozen: bool = False
    freeze_info: Optional[dict] = None

    def snapshot_hashes(self) -> set[str]:
        return {sha(t.scene) for e in self.episodes for t in e.tasks}

    def template_ids(self) -> set[str]:
        return {f"{k}:{v}" for e in self.episodes for k, v in e.templates.items()}

    def content_hash(self) -> str:
        payload = [
            (
                e.episode_id,
                sha(e.spacing),
                sha(e.badge),
                e.drift,
                [(t.task_id, t.stage, t.kind, t.backend, sha(t.scene)) for t in e.tasks],
            )
            for e in self.episodes
        ]
        return hashlib.sha256(canonical(payload).encode()).hexdigest()

    def freeze(self, commit: str) -> str:
        if self.frozen:
            raise ValueError("already frozen")
        self.frozen, self.freeze_info = True, {"commit": commit, "hash": self.content_hash()}
        return self.freeze_info["hash"]

    def verify_frozen(self) -> bool:
        return self.frozen and self.freeze_info["hash"] == self.content_hash()


def make_manifest(split: str, seed: int = 0, n_episodes: int = 12) -> Manifest:
    flags = drift_flags(n_episodes)
    return Manifest(
        split, seed, [make_episode(split, seed, i, flags[i]) for i in range(n_episodes)]
    )


# ----------------------------------------------------------------------------- agent-visible projection
def agent_visible(task: Task) -> dict:
    """Everything a policy may see about a task. No stage, no latent, no template, no drift, no episode split."""
    objs = [
        {k: (str(v) if isinstance(v, F) else v) for k, v in o.items()}
        for o in task.scene["objects"]
    ]
    handle = {
        "spacing": "concept_1",
        "badge": "concept_2",
        "composition": "concept_1_then_concept_2",
    }[task.kind]
    return {
        "task_id": task.task_id,
        "kind": handle,
        "backend": task.backend,
        "scene_objects": objs,
        "canvas": {k: str(v) for k, v in task.scene["canvas"].items()},
        "selected_ids": list(task.selected),
        "prototype_id": task.proto,
    }
