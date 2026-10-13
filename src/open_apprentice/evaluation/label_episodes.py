"""Episode builder for the label-placement redesign experiment (evaluator side).

An episode = one hidden behaviour, 1-2 demonstrations (before/after), a batch of unlabeled documents visible during
teaching (Lane B), and fresh documents never shown (Lane A). Four kinds, expected outcome in brackets:

  unambiguous   the demonstrations pin down the behaviour within the declared catalogue            [commit, no question]
  ambiguous     several catalogue behaviours fit; a batch document separates them                  [ask, then commit]
  unsupported   the behaviour depends on an attribute that is not in the observation              [abstain]
  noisy         one demonstrated label is displaced, so no catalogue behaviour fits every demo     [abstain / flag]

AMBIGUITY IS RELATIVE to the declared CATALOGUE (24 behaviours: primary side x fallback x scope x gap) and to the PROBE
pool (behaviours that agree on every probe scene are one class). It says nothing about behaviours outside the catalogue.
Learners get `agent_visible(ep)` only: no truth, no ambiguity label, no expected outcome. Evaluator code: agent-visible
modules must not import this file.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from fractions import Fraction as F
from itertools import product
from typing import Any

from open_apprentice.concepts.rules import RuleError, evaluate_rule
from open_apprentice.evaluation.labels import (
    Spec,
    apply_oracle,
    check_after,
    make_scene,
    oracle,
)

GAPS = (F(8), F(12), F(16))
OTHER = {"right": "below", "below": "right"}
CATALOGUE: tuple[Spec, ...] = tuple(
    Spec(p, OTHER[p] if fb else None, sc, g)
    for p, fb, sc, g in product(("right", "below"), (False, True), ("all", "notes"), GAPS)
)
KINDS = ("unambiguous", "ambiguous", "unsupported", "noisy")
EXPECTED = {
    "unambiguous": "commit_without_asking",
    "ambiguous": "ask_then_commit",
    "unsupported": "abstain",
    "noisy": "abstain",
}
SPLIT_BASE = {"development": 10_000, "heldout": 50_000}
N_FRESH = 3
N_BATCH = 3
NOISE_PX = 30


def _probe_pool() -> list[dict]:
    return [make_scene(900_000 + i, 4 + i % 7, warnings=i % 3, crowd=i % 4 != 3) for i in range(30)]


PROBES = _probe_pool()


def _frozen(targets: dict[str, tuple[F, F]]) -> tuple:
    return tuple(sorted((k, v) for k, v in targets.items()))


def behaviour_class(spec: Spec) -> tuple:
    """What the spec does on every probe scene. Two specs with the same class are one hypothesis."""
    return tuple(_frozen(oracle(spec, s)) for s in PROBES)


def fits_demo(spec: Spec, before: dict, after: dict) -> bool:
    want = oracle(spec, before)
    a = {o["id"]: o for o in after["objects"]}
    for o in before["objects"]:
        got = (F(a[o["id"]]["x"]), F(a[o["id"]]["y"]))
        base = (F(o["x"]), F(o["y"]))
        if got != want.get(o["id"], base):
            return False
    return True


def consistent_classes(demos: list[tuple[dict, dict]]) -> dict[tuple, list[Spec]]:
    out: dict[tuple, list[Spec]] = {}
    for spec in CATALOGUE:
        if all(fits_demo(spec, b, a) for b, a in demos):
            out.setdefault(behaviour_class(spec), []).append(spec)
    return out


def separates(scene: dict, classes: dict[tuple, list[Spec]]) -> bool:
    return len({_frozen(oracle(v[0], scene)) for v in classes.values()}) > 1


def _hidden_flag(scene_key: str, label_id: str) -> bool:
    return hashlib.sha256(f"{scene_key}/{label_id}".encode()).digest()[0] % 2 == 0


def _unsupported_oracle(scene: dict, key: str) -> dict[str, tuple[F, F]]:
    """Goes below when a hidden per-label flag is set, right otherwise. The flag is not in the observation."""
    from open_apprentice.evaluation.labels import pose

    byid = {o["id"]: o for o in scene["objects"]}
    return {
        o["id"]: pose(
            "below" if _hidden_flag(key, o["id"]) else "right", byid[o["attached"]], o, F(12)
        )
        for o in scene["objects"]
        if o["kind"] == "label"
    }


@dataclass
class LabelEpisode:
    id: str
    kind: str
    split: str
    seed: int
    truth: Spec | None  # None for unsupported / noisy
    demos: list[tuple[dict, dict]]
    batch: list[dict]
    fresh: list[dict]
    unsupported_key: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def expected(self) -> str:
        return EXPECTED[self.kind]

    def classes(self) -> dict[tuple, list[Spec]]:
        return consistent_classes(self.demos)

    def true_targets(self, scene: dict) -> dict[str, tuple[F, F]]:
        if self.truth is not None:
            return oracle(self.truth, scene)
        return _unsupported_oracle(scene, self.unsupported_key)

    def teacher_answer(self, scene: dict) -> dict:
        """What the teacher shows when asked about a batch document: the true after-state."""
        return apply_oracle(scene, self.true_targets(scene))


def agent_visible(ep: LabelEpisode) -> dict:
    return {
        "demonstrations": [{"before": b, "after": a} for b, a in ep.demos],
        "batch": ep.batch,
    }


def _scenes(rng: random.Random, n: int, **kw: Any) -> list[dict]:
    return [
        make_scene(
            rng.randrange(10**6),
            kw.get("nodes", rng.randrange(4, 13)),
            warnings=rng.randrange(0, 4),
            crowd=rng.random() < 0.75,
        )
        for _ in range(n)
    ]


def _demo(spec: Spec, scene: dict) -> tuple[dict, dict]:
    return scene, apply_oracle(scene, oracle(spec, scene))


def build_episode(kind: str, split: str, seed: int) -> LabelEpisode:
    rng = random.Random(SPLIT_BASE[split] + seed)
    for _ in range(400):
        truth = rng.choice(CATALOGUE)
        n_demo = rng.choice((1, 2))
        demo_scenes = _scenes(rng, n_demo)
        demos = [_demo(truth, s) for s in demo_scenes]
        classes = consistent_classes(demos)
        batch = _scenes(rng, N_BATCH)
        fresh = _scenes(rng, N_FRESH)
        ep_id = f"{split}-{kind}-{seed:02d}"
        if kind == "unambiguous":
            if len(classes) != 1 or not oracle(truth, demo_scenes[0]):
                continue
            return LabelEpisode(ep_id, kind, split, seed, truth, demos, batch, fresh)
        if kind == "ambiguous":
            if len(classes) < 2 or not any(separates(s, classes) for s in batch):
                continue
            # at least one fresh document must also tell the candidates apart, or a wrong commitment cannot be seen
            if not any(separates(s, classes) for s in fresh):
                continue
            return LabelEpisode(ep_id, kind, split, seed, truth, demos, batch, fresh)
        if kind == "noisy":
            if len(classes) < 1:
                continue
            before, after = demos[0]
            moved = sorted(oracle(truth, before))
            if not moved:
                continue
            victim = moved[rng.randrange(len(moved))]
            bad = {k: dict(v) if isinstance(v, dict) else v for k, v in after.items()}
            bad["objects"] = [dict(o) for o in after["objects"]]
            for o in bad["objects"]:
                if o["id"] == victim:
                    o["x"] = F(o["x"]) + NOISE_PX
            noisy = [(before, bad), *demos[1:]]
            if consistent_classes(noisy):
                continue
            return LabelEpisode(
                ep_id,
                kind,
                split,
                seed,
                truth,
                noisy,
                batch,
                fresh,
                meta={"displaced": victim, "px": NOISE_PX},
            )
        if kind == "unsupported":
            key = f"{split}/{seed}"
            hidden = [apply_oracle(s, _unsupported_oracle(s, key)) for s in demo_scenes]
            ud = list(zip(demo_scenes, hidden))
            if consistent_classes(ud):
                continue  # some catalogue behaviour happens to fit: not unsupported
            return LabelEpisode(
                ep_id, kind, split, seed, None, ud, batch, fresh, unsupported_key=key
            )
        raise ValueError(kind)
    raise RuntimeError(f"could not build a {kind} episode for seed {seed}")


def build_manifest(
    split: str = "development", counts: dict[str, int] | None = None
) -> list[LabelEpisode]:
    counts = counts or {"unambiguous": 8, "ambiguous": 8, "unsupported": 4, "noisy": 4}
    return [build_episode(k, split, i) for k in KINDS for i in range(counts[k])]


def manifest_hash(eps: list[LabelEpisode]) -> str:
    def enc(o: Any) -> Any:
        if isinstance(o, F):
            return f"{o.numerator}/{o.denominator}"
        raise TypeError(type(o))

    blob = json.dumps(
        [(e.id, e.kind, e.demos, e.batch, e.fresh, e.unsupported_key) for e in eps],
        default=enc,
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def score_commit(ep: LabelEpisode, rule: list) -> dict:
    """Run a committed rule on every fresh document and check it against the TRUE behaviour. Axes stay separate."""
    rows = []
    for scene in ep.fresh:
        want = ep.true_targets(scene)
        try:
            state = evaluate_rule(rule, scene["objects"], scene["canvas"])
        except RuleError as e:
            rows.append({"error": str(e), "intent": False, "preservation": False, "layout": False})
            continue
        after = {
            "objects": [
                dict(o, **{k: state[o["id"]][k] for k in ("x", "y", "w", "h")})
                for o in scene["objects"]
            ],
            "canvas": scene["canvas"],
        }
        r = check_after(scene, after, want)
        rows.append({k: r[k] for k in ("intent", "preservation", "layout")})
    return {
        "per_scene": rows,
        "complete": all(all(r[k] for k in ("intent", "preservation", "layout")) for r in rows),
    }
