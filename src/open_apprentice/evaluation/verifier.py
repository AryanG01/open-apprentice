"""Independent final verifier (spec 12).

Reads PRIVATE native scene state and composes world-space affine matrices itself. It must not
import, call, or share semantic conversion code with any agent-facing tool (`measure_node`,
`observe_geometry`, the engine). Agent-visible packages are forbidden from importing this module
(import-linter contract in pyproject.toml).

Scene format (shared schema only): {"nodes": [{"id", "parent", "type", "x", "y", "width",
"height", "scaleX", "scaleY", "rotation", "fill"}]}. Rotation is unsupported (spec 12.2) and
rejected rather than approximated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ABS_TOL_PX = 0.5  # spec 12.3 starting default; freeze before final evaluation
REL_TOL = 1e-3

Matrix = tuple[float, float, float, float, float, float]  # a b c d e f (2D affine)
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class VerifierInputError(Exception):
    """Malformed or unsupported scene. Surfaced, never scored as pass."""


def _mul(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (
        a * A + c * B,
        b * A + d * B,
        a * C + c * D,
        b * C + d * D,
        a * E + c * F + e,
        b * E + d * F + f,
    )


def _local(node: dict[str, Any]) -> Matrix:
    if abs(float(node.get("rotation", 0.0))) > 1e-9:
        raise VerifierInputError(f"rotation unsupported: {node['id']}")
    if node.get("originX", "left") != "left" or node.get("originY", "top") != "top":
        raise VerifierInputError(
            f"non-default origin unsupported: {node['id']}"
        )  # refuse rather than guess
    sx, sy = float(node.get("scaleX", 1.0)), float(node.get("scaleY", 1.0))
    return (sx, 0.0, 0.0, sy, float(node.get("x", 0.0)), float(node.get("y", 0.0)))


def world_bounds(scene: dict[str, Any]) -> dict[str, tuple[float, float, float, float]]:
    """id -> (left, top, width, height) in world space, for every node with a size."""
    nodes = {n["id"]: n for n in scene["nodes"]}
    if len(nodes) != len(scene["nodes"]):
        raise VerifierInputError("duplicate node ids")
    cache: dict[str, Matrix] = {}

    def world(nid: str, seen: frozenset[str] = frozenset()) -> Matrix:
        if nid in cache:
            return cache[nid]
        if nid in seen:
            raise VerifierInputError("parent cycle")
        n = nodes[nid]
        parent = n.get("parent")
        if parent is not None and parent not in nodes:
            raise VerifierInputError(f"missing parent {parent}")
        m = _mul(world(parent, seen | {nid}) if parent else IDENTITY, _local(n))
        cache[nid] = m
        return m

    out = {}
    for nid, n in nodes.items():
        m = world(nid)
        if "width" in n and "height" in n:
            w, h = float(n["width"]) * m[0], float(n["height"]) * m[3]
            out[nid] = (m[4], m[5], w, h)
    return out


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class VerifierReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    def failed(self) -> list[str]:
        return [c.name for c in self.checks if not c.passed]

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name, bool(ok), detail))


def _close(a: float, b: float, scale: float = 0.0) -> bool:
    return abs(a - b) <= ABS_TOL_PX + REL_TOL * abs(scale)


def verify_gap_row(initial: dict, final: dict, task: dict) -> VerifierReport:
    """Spec 12.2 gap_row checks. `task` follows the canonical representation (6.2)."""
    rep = VerifierReport()
    ids: list[str] = task["selected_ids"]
    gap = float(task["parameters"]["gap_px"])
    left, top = float(task["parameters"]["left_px"]), float(task["parameters"]["top_px"])
    canvas = task["canvas"]

    f_ids = [n["id"] for n in final["nodes"]]
    i_ids = [n["id"] for n in initial["nodes"]]
    rep.add(
        "objects_exist_exactly_once",
        sorted(f_ids) == sorted(i_ids) and len(set(f_ids)) == len(f_ids),
        f"initial={len(i_ids)} final={len(f_ids)}",
    )
    if not rep.checks[-1].passed:
        return rep  # geometry below is meaningless if the object set changed

    wi, wf = world_bounds(initial), world_bounds(final)

    rep.add(
        "sizes_preserved",
        all(
            _close(wf[i][2], wi[i][2], wi[i][2]) and _close(wf[i][3], wi[i][3], wi[i][3])
            for i in ids
        ),
        "world width/height of selected objects",
    )

    ordered = sorted(ids, key=lambda i: wf[i][0])
    rep.add("order_preserved", ordered == ids, f"world left-to-right={ordered}")

    gaps = [wf[b][0] - (wf[a][0] + wf[a][2]) for a, b in zip(ids, ids[1:])]
    rep.add("edge_gaps_match", all(_close(g, gap, gap) for g in gaps), f"gaps={gaps}")
    rep.add("left_edge_matches", _close(wf[ids[0]][0], left), f"left={wf[ids[0]][0]}")
    rep.add(
        "top_aligned", all(_close(wf[i][1], top) for i in ids), f"tops={[wf[i][1] for i in ids]}"
    )

    unsel = [i for i in i_ids if i not in ids and i in wi]
    rep.add(
        "no_unauthorized_move",
        all(all(_close(x, y, y) for x, y in zip(wf[i], wi[i])) for i in unsel),
        f"unselected checked={len(unsel)}",
    )

    istyle = {n["id"]: n.get("fill") for n in initial["nodes"]}
    rep.add("styles_preserved", all(n.get("fill") == istyle[n["id"]] for n in final["nodes"]))

    rep.add(
        "within_canvas",
        all(
            wf[i][0] >= -ABS_TOL_PX
            and wf[i][1] >= -ABS_TOL_PX
            and wf[i][0] + wf[i][2] <= canvas["width"] + ABS_TOL_PX
            and wf[i][1] + wf[i][3] <= canvas["height"] + ABS_TOL_PX
            for i in ids
        ),
    )

    # A "success" with no mutation must not pass by coincidence of the initial layout.
    moved = any(not all(_close(x, y, y) for x, y in zip(wf[i], wi[i])) for i in ids)
    already = (
        all(
            all(
                _close(g, gap, gap)
                for g in [wi[b][0] - (wi[a][0] + wi[a][2]) for a, b in zip(ids, ids[1:])]
            )
            for _ in [0]
        )
        and _close(wi[ids[0]][0], left)
        and all(_close(wi[i][1], top) for i in ids)
    )
    rep.add(
        "scene_actually_changed_or_already_satisfied",
        moved or already,
        f"moved={moved} already_satisfied={already}",
    )
    return rep


def verify_expected_geometry(
    initial: dict, final: dict, expected: dict, selected_ids: list[str]
) -> VerifierReport:
    """Compare ACTUAL world geometry (composed here) with externally supplied expected geometry.

    `expected` maps selected ids (existing objects) and clone symbols (created objects, identified by
    their node id == symbol) to {x,y,w,h} in world space. Used for held-out intent correctness: the
    expectation comes from the private teacher rule, so a native binding that executes the learner's
    own wrong rule perfectly still FAILS here.
    """
    rep = VerifierReport()
    wi, wf = world_bounds(initial), world_bounds(final)
    i_ids = {n["id"] for n in initial["nodes"]}
    f_ids = [n["id"] for n in final["nodes"]]
    symbols = [k for k in expected if k not in i_ids]
    rep.add("no_duplicate_ids", len(set(f_ids)) == len(f_ids))
    rep.add(
        "exactly_the_expected_new_objects",
        sorted(set(f_ids) - i_ids) == sorted(symbols),
        f"created={sorted(set(f_ids) - i_ids)} expected={sorted(symbols)}",
    )
    rep.add("original_objects_still_exist", i_ids <= set(f_ids))
    if not all(c.passed for c in rep.checks):
        return rep

    def box(k):
        return wf[k]

    bad = []
    for k, e in expected.items():
        got = box(k)
        want = (float(e["x"]), float(e["y"]), float(e["w"]), float(e["h"]))
        if not all(_close(g, w, w) for g, w in zip(got, want)):
            bad.append((k, got, want))
    rep.add("geometry_matches_expected", not bad, f"{bad[:3]}")
    untouched = [i for i in i_ids if i not in expected and i in wi]
    rep.add(
        "unselected_unchanged",
        all(all(_close(x, y, y) for x, y in zip(wf[i], wi[i])) for i in untouched),
        f"checked={len(untouched)}",
    )
    return rep
