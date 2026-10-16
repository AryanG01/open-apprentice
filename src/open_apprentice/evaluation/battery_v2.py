"""The Plan 5 battery: 36 final episodes (18 development), the learner-visible projection, and the hashed freeze
(evaluator side; spec 7).

Scene ids are fixed per episode: demonstrations d0..d1, batch b0..b2, correction target c0 (all learner-visible),
diagnostic scenes x0..x3 and scoring scenes s0..s2 (private). Agent-visible modules must not import this file.
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
from dataclasses import dataclass, field
from fractions import Fraction as F
from pathlib import Path
from typing import Any, Optional

from open_apprentice.evaluation.label_episodes import CATALOGUE, consistent_classes, separates
from open_apprentice.evaluation.labels import Spec, _layout_violations, apply_oracle, overlaps
from open_apprentice.evaluation.specs_v2 import STRATA, VSpec, oracle_v, scene_v
from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import scene_from_payload
from open_apprentice.teaching.scope import members

GENERATOR_VERSION = "battery-v2.1"
SCORING_VERSION = "score-v2.1"
TOLERANCE = F(1, 2)
SEED_BASE = {"dev": 110_000, "final": 170_000}
ATTEMPTS = 900
REPO = Path(__file__).resolve().parents[3]
REAL_FILES = {  # docs/corpus/drawio_provenance.md
    "f1": "cf538204a77dbda9077827c0dceba850748ab032e53d42e3e9fba3c3e0215d40",
    "f2": "6d405ac75d76a21512383e7a97ee86debb03b757d720fa9b9fff6abf3625e17b",
    "f3": "23b305bc21766e2f314b8e5478bb6238c0b2fc60d4d0aa2bb1289916afde843a",
}

# corrections: base catalogue behaviour -> corrected behaviour, and the selector naming exactly the labels that change
TEMPLATES = {
    "warn_below": ("all", "role_sides", 'o.role == "warning"'),
    "tall_below": ("all", "size_side", "object(o.attached).w <= object(o.attached).h"),
    "notes_then_warn": ("notes", "role_sides", 'o.role == "warning"'),
}

_SEQ_FINAL = (
    [("compatible", t) for t in ("warn_below", "tall_below", "notes_then_warn", "tall_below")]
    + [("superseding", t) for t in ("warn_below", "tall_below", "notes_then_warn", "warn_below")]
    + [("conflict", "warn_below"), ("conflict", "notes_then_warn")]
    + [("override", "warn_below"), ("accidental", "warn_below")]
)
_SEQ_DEV = [
    ("compatible", "tall_below"),
    ("compatible", "warn_below"),
    ("superseding", "notes_then_warn"),
    ("conflict", "warn_below"),
    ("override", "warn_below"),
    ("accidental", "warn_below"),
]
PLAN: dict[str, list[tuple[str, Any]]] = {
    "final": [("catalogue", "clarify")] * 4
    + [("catalogue", "identify")] * 4
    + [
        ("beyond", VSpec("gap_by_width", ())),
        ("beyond", VSpec("role_sides", (F(12),))),
        ("beyond", VSpec("fallback_chain", (F(12),))),
        ("beyond", VSpec("size_side", (F(12),))),
        ("beyond", VSpec("gap_by_width", ())),
        ("beyond", VSpec("role_sides", (F(8),))),
        ("beyond", VSpec("fallback_chain", (F(16),))),
        ("beyond", VSpec("size_side", (F(16),))),
    ]
    + [("inconsistent", None)] * 4
    + [("unsupported", "unobservable")] * 2
    + [("unsupported", "forced_overlap"), ("unsupported", "unsupported_structure")]
    + [("sequential", s) for s in _SEQ_FINAL],
    "dev": [("catalogue", "clarify")] * 2
    + [("catalogue", "identify")] * 2
    + [
        ("beyond", VSpec("gap_by_width", ())),
        ("beyond", VSpec("role_sides", (F(16),))),
        ("beyond", VSpec("fallback_chain", (F(8),))),
        ("beyond", VSpec("size_side", (F(8),))),
    ]
    + [("inconsistent", None)] * 2
    + [("unsupported", "forced_overlap"), ("unsupported", "unsupported_structure")]
    + [("sequential", s) for s in _SEQ_DEV],
}


class FrozenMismatch(ValueError):
    pass


@dataclass
class Episode:
    id: str
    stratum: str
    spec: VSpec
    demo_scenes: list[dict]
    demo_outputs: list[dict]
    batch_scenes: list[dict]
    scoring_scenes: list[dict]
    clarification_required: bool
    correction: Optional[dict]
    seed: int
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------------- generation


class _Retry(Exception):
    pass


def _labels(scene: dict) -> list[dict]:
    return [o for o in scene["objects"] if o["kind"] == "label"]


def _final(spec: VSpec, scene: dict) -> dict[str, tuple[F, F]]:
    """Every label's position after the behaviour (moved or left where it was)."""
    moved = oracle_v(spec, scene)
    return {o["id"]: moved.get(o["id"], (F(o["x"]), F(o["y"]))) for o in _labels(scene)}


def _after(spec: VSpec, scene: dict) -> dict:
    return apply_oracle(scene, oracle_v(spec, scene))


def _strip_warnings(scene: dict) -> dict:
    return {
        "objects": [dict(o, role="note") if o["kind"] == "label" else o for o in scene["objects"]],
        "canvas": scene["canvas"],
    }


def _with_corner(scene: dict) -> dict:
    """Add a node in the bottom-right corner with its label parked above it: right and below are off the page."""
    cw, ch = scene["canvas"]["w"], scene["canvas"]["h"]
    node = {"id": "nc", "kind": "node", "role": "", "attached": ""}
    node |= {"x": cw - 100, "y": ch - 50, "w": 90, "h": 40}
    label = {"id": "lc", "kind": "label", "role": "note", "attached": "nc"}
    label |= {"x": cw - 100, "y": ch - 74, "w": 56, "h": 16}
    boxes = [(F(o["x"]), F(o["y"]), F(o["w"]), F(o["h"])) for o in scene["objects"]]
    for new in (node, label):
        if any(overlaps((F(new["x"]), F(new["y"]), F(new["w"]), F(new["h"])), b) for b in boxes):
            raise _Retry
    return {"objects": [*scene["objects"], node, label], "canvas": scene["canvas"]}


def _rotate_first_label(scene: dict) -> dict:
    objs = [dict(o) for o in scene["objects"]]
    next(o for o in objs if o["kind"] == "label")["rotation"] = 90
    return {"objects": objs, "canvas": scene["canvas"]}


def _cat(spec: Spec) -> VSpec:
    return VSpec("catalogue", (spec,))


class _Gen:
    def __init__(self, seed: int, attempt: int) -> None:
        self.seed, self.attempt, self.k = seed, attempt, 0
        self.rng = random.Random(seed * 10_000 + attempt)

    def scene(self, stratum: Optional[str] = None) -> dict:
        self.k += 1
        stratum = stratum or STRATA[(self.seed + self.k) % len(STRATA)]
        return scene_v(stratum, (self.seed * 10_000 + self.attempt) * 100 + self.k)

    def scenes(self, n: int, stratum: Optional[str] = None) -> list[dict]:
        return [self.scene(stratum) for _ in range(n)]


def _mark(demos: list[tuple[dict, dict]]) -> bool:
    return len(consistent_classes(demos)) >= 2


def _learning(stratum: str, variant: Any, g: _Gen) -> dict:
    """Catalogue, beyond, inconsistent and unsupported episodes."""
    rng = g.rng
    meta: dict = {}
    if stratum == "catalogue":
        spec = _cat(rng.choice(CATALOGUE))
        demo_scenes = g.scenes(rng.choice((1, 2)))
        batch, scoring = g.scenes(3), g.scenes(3)
        demos = [(s, _after(spec, s)) for s in demo_scenes]
        classes = consistent_classes(demos)
        if variant == "identify" and (len(classes) != 1 or not oracle_v(spec, demo_scenes[0])):
            raise _Retry
        if variant == "clarify" and not (
            len(classes) >= 2
            and any(separates(s, classes) for s in batch)
            and any(separates(s, classes) for s in scoring)
        ):
            raise _Retry
    elif stratum == "beyond":
        spec = variant
        demo_scenes, batch, scoring = g.scenes(2), g.scenes(3), g.scenes(3)
        if spec.kind == "fallback_chain":
            demo_scenes[0], scoring[0] = _with_corner(demo_scenes[0]), _with_corner(scoring[0])
        demos = [(s, _after(spec, s)) for s in demo_scenes]
        if consistent_classes(demos):
            raise _Retry
    elif stratum == "inconsistent":
        s = g.scene()
        first = rng.choice(CATALOGUE)
        others = [c for c in CATALOGUE if _final(_cat(c), s) != _final(_cat(first), s)]
        second = rng.choice(others)
        spec, demo_scenes = _cat(first), [s, s]
        demos = [(s, _after(spec, s)), (s, _after(_cat(second), s))]
        batch, scoring = g.scenes(3), g.scenes(3)
        meta = {"conflict_spec": vspec_to_json(_cat(second))}
    elif stratum == "unsupported":
        meta = {"subtype": variant}
        if variant == "unobservable":
            spec = VSpec("unobservable", (f"battery/{g.seed}",))
            demo_scenes = g.scenes(rng.choice((1, 2)))
        elif variant == "forced_overlap":
            spec = _cat(Spec("right", None, "all", F(12)))
            demo_scenes = g.scenes(rng.choice((1, 2)), "narrow")
        else:
            spec = _cat(rng.choice(CATALOGUE))
            demo_scenes = [_rotate_first_label(s) for s in g.scenes(rng.choice((1, 2)))]
        batch, scoring = g.scenes(3), g.scenes(3)
        if variant == "unsupported_structure":
            batch = [_rotate_first_label(s) for s in batch]
            scoring = [_rotate_first_label(s) for s in scoring]
        demos = [(s, _after(spec, s)) for s in demo_scenes]
        if variant == "unobservable" and consistent_classes(demos):
            raise _Retry
        if variant == "forced_overlap":
            after = {o["id"]: o for o in demos[0][1]["objects"]}
            if not _layout_violations(
                after, oracle_v(spec, demo_scenes[0]), demo_scenes[0]["canvas"]
            ):
                raise _Retry
    else:
        raise ValueError(stratum)
    return {
        "spec": spec,
        "demo_scenes": demo_scenes,
        "demo_outputs": [a for _, a in demos],
        "batch_scenes": batch,
        "scoring_scenes": scoring,
        "clarification_required": _mark(demos),
        "correction": None,
        "meta": meta,
    }


def _sequential(variant: tuple[str, str], g: _Gen) -> dict:
    kind, template = variant
    scope, corrected_kind, selector = TEMPLATES[template]
    gap = g.rng.choice((F(8), F(12), F(16)))
    base_spec = Spec("right", None, scope, gap)
    base, corrected = _cat(base_spec), VSpec(corrected_kind, (gap,))

    def changed(scene: dict) -> set[str]:
        a, b = _final(base, scene), _final(corrected, scene)
        return {k for k in a if a[k] != b[k]}

    demo_scenes = g.scenes(g.rng.choice((1, 2)))
    if kind == "compatible" and template != "tall_below":
        demo_scenes = [_strip_warnings(s) for s in demo_scenes]
    demos = [(s, _after(base, s)) for s in demo_scenes]
    classes = consistent_classes(demos)
    batch, scoring = g.scenes(3), g.scenes(3)
    if not any(base_spec in v for v in classes.values()):
        raise _Retry
    if len(classes) >= 2 and not any(separates(s, classes) for s in batch):
        raise _Retry
    demo_changed = any(changed(s) for s in demo_scenes)
    if (kind == "compatible") == demo_changed and kind in ("compatible", "superseding", "conflict"):
        raise _Retry
    correction: dict[str, Any]
    if kind in ("override", "accidental"):
        target = g.scene()
        lab = g.rng.choice(_labels(target))["id"]
        out = _final(base, target)
        out[lab] = (out[lab][0] + (30 if kind == "override" else 6), out[lab][1])
        correction = {"spec": None, "selector": None, "diagnostic_scenes": [], "mask": [lab]}
        correction |= {"scene": target, "corrected_output": out}
    else:
        target = demo_scenes[0] if kind == "conflict" else g.scene()
        diagnostic = g.scenes(4)
        for group in (diagnostic, scoring):
            if not any(changed(s) for s in group) or not any(
                len(changed(s)) < len(_labels(s)) for s in group
            ):
                raise _Retry
        if not changed(target):
            raise _Retry
        for s in [target, *diagnostic, *scoring]:
            if members(selector, scene_from_payload(codec.loads(codec.dumps(s)))) != changed(s):
                raise RuntimeError(f"selector of {template} does not name the changed labels")
        correction = {"spec": corrected, "selector": selector, "diagnostic_scenes": diagnostic}
        correction |= {"scene": target, "corrected_output": _final(corrected, target)}
        correction["mask"] = sorted(changed(target))
    correction |= {"kind": kind, "template": template}
    return {
        "spec": base,
        "demo_scenes": demo_scenes,
        "demo_outputs": [a for _, a in demos],
        "batch_scenes": batch,
        "scoring_scenes": scoring,
        "clarification_required": _mark(demos),
        "correction": correction,
        "meta": {},
    }


def _opaque(split: str, seed: int) -> str:
    return "e" + hashlib.sha256(f"oa-battery/{split}/{seed}".encode()).hexdigest()[:10]


def build_battery(split: str) -> list[Episode]:
    out = []
    for i, (stratum, variant) in enumerate(PLAN[split]):
        seed = SEED_BASE[split] + i
        for attempt in range(ATTEMPTS):
            g = _Gen(seed, attempt)
            try:
                body = (
                    _sequential(variant, g)
                    if stratum == "sequential"
                    else _learning(stratum, variant, g)
                )
            except _Retry:
                continue
            out.append(Episode(_opaque(split, seed), stratum, seed=seed, **body))
            break
        else:
            raise RuntimeError(f"could not build {stratum}/{variant} for seed {seed}")
    return out


# ---------------------------------------------------------------------------------------------------- JSON


def _plain(o: Any) -> Any:
    return codec.loads(codec.dumps(o))


def vspec_to_json(s: VSpec) -> dict:
    if s.kind == "catalogue":
        c = s.params[0]
        return {"kind": s.kind, "params": [_plain(c.__dict__)]}
    return {"kind": s.kind, "params": _plain(list(s.params))}


def vspec_from_json(d: dict) -> VSpec:
    p = d["params"]
    if d["kind"] == "catalogue":
        c = p[0]
        return VSpec("catalogue", (Spec(c["primary"], c["fallback"], c["scope"], F(c["gap"])),))
    if d["kind"] == "unobservable":
        return VSpec("unobservable", tuple(p))
    return VSpec(d["kind"], tuple(F(v) for v in p))


def _out_json(out: dict) -> dict:
    return _plain({k: list(v) for k, v in out.items()})


def _out_from(d: dict) -> dict[str, tuple[F, F]]:
    return {k: (F(v[0]), F(v[1])) for k, v in d.items()}


def episode_to_json(ep: Episode) -> dict:
    c = ep.correction
    corr = None
    if c is not None:
        corr = _plain({k: v for k, v in c.items() if k not in ("spec", "corrected_output")})
        corr["spec"] = vspec_to_json(c["spec"]) if c["spec"] is not None else None
        corr["corrected_output"] = _out_json(c["corrected_output"])
    return {
        "id": ep.id,
        "stratum": ep.stratum,
        "spec": vspec_to_json(ep.spec),
        "demo_scenes": _plain(ep.demo_scenes),
        "demo_outputs": _plain(ep.demo_outputs),
        "batch_scenes": _plain(ep.batch_scenes),
        "scoring_scenes": _plain(ep.scoring_scenes),
        "clarification_required": ep.clarification_required,
        "correction": corr,
        "seed": ep.seed,
        "meta": _plain(ep.meta),
    }


def episode_from_json(d: dict) -> Episode:
    def scenes(xs: list) -> list[dict]:
        return [scene_from_payload(s) for s in xs]

    corr = d["correction"]
    if corr is not None:
        corr = dict(corr)
        corr["spec"] = vspec_from_json(corr["spec"]) if corr["spec"] is not None else None
        corr["corrected_output"] = _out_from(corr["corrected_output"])
        corr["scene"] = scene_from_payload(corr["scene"])
        corr["diagnostic_scenes"] = scenes(corr["diagnostic_scenes"])
    return Episode(
        d["id"],
        d["stratum"],
        vspec_from_json(d["spec"]),
        scenes(d["demo_scenes"]),
        scenes(d["demo_outputs"]),
        scenes(d["batch_scenes"]),
        scenes(d["scoring_scenes"]),
        d["clarification_required"],
        corr,
        d["seed"],
        d["meta"],
    )


def scene_ids(ep: Episode) -> dict[str, dict]:
    """Every scene of the episode by id, private ones included (the teacher's view)."""
    out = {f"d{i}": s for i, s in enumerate(ep.demo_scenes)}
    out |= {f"b{i}": s for i, s in enumerate(ep.batch_scenes)}
    out |= {f"s{i}": s for i, s in enumerate(ep.scoring_scenes)}
    if ep.correction is not None:
        out["c0"] = ep.correction["scene"]
        out |= {f"x{i}": s for i, s in enumerate(ep.correction["diagnostic_scenes"])}
    return out


def learner_view(ep: Episode) -> dict:
    """Demonstrations, batch documents and (sequential) the teacher's corrective edit. No spec, no scoring scenes,
    no marks, no scope."""
    scenes = {f"d{i}": s for i, s in enumerate(ep.demo_scenes)}
    scenes |= {f"b{i}": s for i, s in enumerate(ep.batch_scenes)}
    correction = None
    if ep.correction is not None:
        scenes["c0"] = ep.correction["scene"]
        correction = {
            "scene_id": "c0",
            "corrected_output": _out_json(ep.correction["corrected_output"]),
            "mask": list(ep.correction["mask"]),
        }
    return _plain(
        {
            "id": ep.id,
            "scenes": scenes,
            "demonstrations": [
                {"scene_id": f"d{i}", "after": a} for i, a in enumerate(ep.demo_outputs)
            ],
            "batch": [f"b{i}" for i in range(len(ep.batch_scenes))],
            "correction": correction,
        }
    )


# ---------------------------------------------------------------------------------------------------- freeze


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _commit() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def real_file_episodes(drawio_dir: Path) -> list[dict]:
    """Three final real-file episodes. Only the files' bytes are hashed here (checked against the provenance record);
    their contents are not parsed until the final run."""
    rng = random.Random(SEED_BASE["final"] + 900)
    out = []
    for name, want in REAL_FILES.items():
        got = _sha((drawio_dir / f"{name}.drawio").read_bytes())
        if got != want:
            raise FrozenMismatch(f"{name}.drawio hash {got} does not match its provenance record")
        out.append(
            {
                "id": _opaque("final-real", int(name[1:])),
                "file": f"benchmarks/final/drawio/{name}.drawio",
                "sha256": got,
                "spec": vspec_to_json(_cat(rng.choice(CATALOGUE))),
            }
        )
    return out


def freeze(split: str, out_dir: Path, drawio_dir: Optional[Path] = None) -> dict[str, str]:
    out_dir = Path(out_dir)
    (out_dir / "episodes").mkdir(parents=True, exist_ok=True)
    (out_dir / "learner").mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    entries = []
    for ep in build_battery(split):
        for rel, obj in (
            (f"episodes/{ep.id}.private.json", episode_to_json(ep)),
            (f"learner/{ep.id}.json", learner_view(ep)),
        ):
            raw = codec.dumps(obj)
            (out_dir / rel).write_bytes(raw)
            files[rel] = _sha(raw)
        entries.append(
            {
                "id": ep.id,
                "seed": ep.seed,
                "stratum": ep.stratum,
                "clarification_required": ep.clarification_required,
                "correction_kind": ep.correction["kind"] if ep.correction else None,
                "spec_hash": codec.digest(vspec_to_json(ep.spec)),
            }
        )
    private = {
        "split": split,
        "generator_version": GENERATOR_VERSION,
        "scoring_version": SCORING_VERSION,
        "tolerance": "1/2",
        "code_commit": _commit(),
        "seed_base": SEED_BASE[split],
        "episodes": entries,
        "files": files,
        "real_files": (
            real_file_episodes(drawio_dir or REPO / "benchmarks/final/drawio")
            if split == "final"
            else []
        ),
    }
    public = {"split": split, "episodes": sorted(e["id"] for e in entries)}
    for rel, obj in (("manifest.private.json", private), ("manifest.public.json", public)):
        (out_dir / rel).write_bytes(json.dumps(obj, indent=1, sort_keys=True).encode() + b"\n")
    return verify_frozen(out_dir)


def verify_frozen(out_dir: Path, expected: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Recompute every hash. Raises FrozenMismatch on any changed, missing or extra file."""
    out_dir = Path(out_dir)
    private_raw = (out_dir / "manifest.private.json").read_bytes()
    recorded = json.loads(private_raw)["files"]
    present = {
        str(p.relative_to(out_dir))
        for d in ("episodes", "learner")
        for p in (out_dir / d).glob("*.json")
    }
    if present != set(recorded):
        raise FrozenMismatch(f"file set differs: {sorted(present ^ set(recorded))}")
    for rel, want in recorded.items():
        if _sha((out_dir / rel).read_bytes()) != want:
            raise FrozenMismatch(f"{rel} does not match its recorded hash")
    hashes = dict(recorded)
    hashes["manifest.private.json"] = _sha(private_raw)
    hashes["manifest.public.json"] = _sha((out_dir / "manifest.public.json").read_bytes())
    if expected is not None and expected != hashes:
        bad = sorted(k for k in set(expected) | set(hashes) if expected.get(k) != hashes.get(k))
        raise FrozenMismatch(f"hashes differ from the recorded freeze: {bad}")
    return hashes
