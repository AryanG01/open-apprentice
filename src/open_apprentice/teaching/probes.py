"""Generated probes (spec 4 rule 3): small, deterministic edits of a registered document that make surviving candidate rules
disagree when the batch documents cannot. Pure: scene edits and a counted evaluation under the round's statement budget. A probe
is only ever shown after the executor's renderer has rendered it and matched its selection geometry (see ProbeResult).

Families in release 1: node_resize, obstacle (another node moved into one rule's placement), narrow_canvas. Probes never change
text. Observable role flips and fresh arrangements are not generated (spec 11 scope cut 3)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from typing import Optional

from open_apprentice.concepts.rules import RuleError, evaluate_rule_counted
from open_apprentice.teaching import codec
from open_apprentice.teaching.teacher import SEPARATION, Output, max_error

FACTORS = (Fraction(1, 2), Fraction(2))


@dataclass(frozen=True)
class Probe:
    probe_id: str
    source_scene_id: str
    family: str
    edits: tuple[
        tuple[str, tuple[tuple[str, str], ...]], ...
    ]  # cell id -> ((attr, exact value), ...)
    canvas_w: Optional[str]
    scene: dict
    changed_attrs: int


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    scene_id: Optional[str] = None
    scene: Optional[dict] = None
    reason: str = ""


@dataclass(frozen=True)
class ProbeSearch:
    best: Optional[Probe]
    groups: list
    statements: int
    outcome: (
        str  # found | completed_no_disagreement | budget_exhausted | candidates_failed_on_inputs
    )


def _out_counted(rule: list, scene: dict) -> tuple[Optional[Output], int]:
    try:
        st, n = evaluate_rule_counted(rule, scene["objects"], scene["canvas"])
    except RuleError as e:
        return None, int(getattr(e, "steps", 0))
    return {
        o["id"]: (st[o["id"]]["x"], st[o["id"]]["y"])
        for o in scene["objects"]
        if o["kind"] == "label"
    }, n


def _box(o: dict) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    return Fraction(o["x"]), Fraction(o["y"]), Fraction(o["w"]), Fraction(o["h"])


def _overlap(a: dict, b: dict) -> bool:
    ax, ay, aw, ah = _box(a)
    bx, by, bw, bh = _box(b)
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _valid(scene: dict) -> bool:
    W, H = Fraction(scene["canvas"]["w"]), Fraction(scene["canvas"]["h"])
    for o in scene["objects"]:
        x, y, w, h = _box(o)
        if x < 0 or y < 0 or x + w > W or y + h > H:
            return False
    nodes = [o for o in scene["objects"] if o["kind"] == "node"]
    return not any(_overlap(a, b) for a, b in combinations(nodes, 2))


def _make(
    sid: str,
    family: str,
    base: dict,
    cells: dict[str, dict[str, Fraction]],
    canvas_w: Optional[Fraction],
) -> Optional[Probe]:
    objs = [dict(o, **cells.get(o["id"], {})) for o in base["objects"]]
    canvas = dict(base["canvas"], **({"w": canvas_w} if canvas_w is not None else {}))
    scene = {"objects": objs, "canvas": canvas}
    if not _valid(scene):
        return None
    edits = tuple(
        sorted((cid, tuple(sorted((k, str(v)) for k, v in a.items()))) for cid, a in cells.items())
    )
    cw = str(canvas_w) if canvas_w is not None else None
    pid = codec.digest({"s": sid, "f": family, "e": [list(e) for e in edits], "c": cw})[:20]
    changed = sum(len(a) for a in cells.values()) + (1 if canvas_w is not None else 0)
    return Probe(pid, sid, family, edits, cw, scene, changed)


def candidate_probes(
    scenes: dict[str, dict], roles: dict[str, str], cands: list[dict], limit: int = 128
) -> list[Probe]:
    """Deterministic probe candidates over demo/batch scenes, capped at `limit` (family order, then scene, then cell)."""
    out: dict[str, list[Probe]] = {"node_resize": [], "obstacle": [], "narrow_canvas": []}
    for sid in sorted(scenes):
        if roles.get(sid) not in ("demo", "batch"):
            continue
        sc = scenes[sid]
        objs = {o["id"]: o for o in sc["objects"]}
        anchors = sorted(
            {o["attached"] for o in sc["objects"] if o["kind"] == "label" and o["attached"] in objs}
        )
        for nid in anchors:
            n = objs[nid]
            for attr in ("w", "h"):
                for f in FACTORS:
                    p = _make(sid, "node_resize", sc, {nid: {attr: Fraction(n[attr]) * f}}, None)
                    if p:
                        out["node_resize"].append(p)
        outs = [(_out_counted(c["rule"], sc)[0], c) for c in cands]
        for (oa, _), (ob, _) in combinations(outs, 2):
            if oa is None or ob is None:
                continue
            for lid in sorted(set(oa) & set(ob)):
                if oa[lid] == ob[lid] or lid not in objs:
                    continue
                for o in sorted(objs.values(), key=lambda q: q["id"]):
                    if o["kind"] != "node" or o["id"] == objs[lid]["attached"]:
                        continue
                    x, y = oa[lid]
                    p = _make(
                        sid, "obstacle", sc, {o["id"]: {"x": Fraction(x), "y": Fraction(y)}}, None
                    )
                    if p:
                        out["obstacle"].append(p)
                        break
        right = max(Fraction(o["x"]) + Fraction(o["w"]) for o in sc["objects"])
        if right < Fraction(sc["canvas"]["w"]):
            p = _make(sid, "narrow_canvas", sc, {}, right)
            if p:
                out["narrow_canvas"].append(p)
    seen: set[str] = set()
    probes: list[Probe] = []
    for fam in ("node_resize", "obstacle", "narrow_canvas"):
        for p in out[fam]:
            if p.probe_id not in seen:
                seen.add(p.probe_id)
                probes.append(p)
    return probes[:limit]


def _usable(groups: list[tuple[Output, list[dict]]]) -> bool:
    if not 2 <= len(groups) <= 4:
        return False
    for (a, _), (b, _) in combinations(groups, 2):
        e = max_error(a, b)
        if e is None or e <= SEPARATION:
            return False
    return True


def search(probes: list[Probe], cands: list[dict], budget: int) -> ProbeSearch:
    """Evaluate every candidate on each probe until the statement budget would be exceeded; return the best usable probe."""
    used, failed = 0, False
    best: Optional[tuple[tuple, Probe, list]] = None
    for p in probes:
        groups: list[tuple[Output, list[dict]]] = []
        broken = False
        for c in cands:
            out, n = _out_counted(c["rule"], p.scene)
            used += n
            if used > budget:
                return ProbeSearch(best[1] if best else None, best[2] if best else [], used,
                                   "found" if best else "budget_exhausted")  # fmt: skip
            if out is None:
                broken = True
                continue
            for g in groups:
                if g[0] == out:
                    g[1].append(c)
                    break
            else:
                groups.append((out, [c]))
        failed = failed or broken
        if broken or not _usable(groups):
            continue
        n_c = len(cands)
        pairs = n_c * (n_c - 1) // 2 - sum(len(g) * (len(g) - 1) // 2 for _, g in groups)
        key = (-pairs, p.changed_attrs, len(p.scene["objects"]), p.probe_id)
        if best is None or key < best[0]:
            best = (key, p, groups)
    if best is not None:
        return ProbeSearch(best[1], best[2], used, "found")
    return ProbeSearch(
        None, [], used, "candidates_failed_on_inputs" if failed else "completed_no_disagreement"
    )


def probe_to_json(p: Probe) -> dict:
    return {
        "probe_id": p.probe_id,
        "source_scene_id": p.source_scene_id,
        "family": p.family,
        "edits": [[cid, [list(kv) for kv in attrs]] for cid, attrs in p.edits],
        "canvas_w": p.canvas_w,
        "scene": codec.loads(codec.dumps(p.scene)),
        "changed_attrs": p.changed_attrs,
    }


def probe_from_json(d: dict) -> Probe:
    from open_apprentice.teaching.constraints import scene_from_payload

    edits = tuple((cid, tuple((k, v) for k, v in attrs)) for cid, attrs in d["edits"])
    return Probe(d["probe_id"], d["source_scene_id"], d["family"], edits, d["canvas_w"], scene_from_payload(d["scene"]),
                 d["changed_attrs"])  # fmt: skip
