"""A layout plan: the rule's targets placed into concrete story cards (spec 7.4-7.5)."""

from __future__ import annotations

from dataclasses import dataclass, field

from open_apprentice.campaign.layout_rule import LayoutOutcome, Target
from open_apprentice.campaign.limits import OPTIONAL_ROLES, SAFE, STORY_H, STORY_W

CARD_GAP = 100  # card 2 starts at x = STORY_W + CARD_GAP (the 9A gold layout)


def card(card_id: str, sequence: int) -> dict:
    return {
        "id": card_id,
        "x": (sequence - 1) * (STORY_W + CARD_GAP),
        "sequence": sequence,
        "width": STORY_W,
        "height": STORY_H,
        "format": "9:16",
        "safe": dict(SAFE),
    }


@dataclass
class LayoutPlan:
    source_artboard: str
    artboards: list[dict]
    targets: list[Target]
    kinds: dict[str, str]  # node id -> scene type, for every target (clones included)
    roles: dict[str, str] = field(
        default_factory=dict
    )  # node id -> role (CTA children: cta/<type>)
    clones: list[tuple[str, str]] = field(default_factory=list)  # (source id, new id)
    origin: str = "search"


def _close_stacking_gaps(targets: list[Target], nodes: dict[str, dict]) -> None:
    """A taught stacking order counts every part of the banner; when a banner lacks some (no price, say) the order has gaps and
    the engine refuses an index past the last layer. Re-rank each card's layers by their stacking so the order is the same
    and the indexes are dense."""
    by_parent: dict[str, list[tuple[int, Target]]] = {}
    for t in targets:
        n = nodes.get(t.node_id)
        if t.parent is None or n is None:
            continue
        z = t.z if t.z is not None else n.get("z")
        if z is not None:
            by_parent.setdefault(t.parent, []).append((z, t))
    for members in by_parent.values():
        ranked = sorted(members, key=lambda m: m[0])
        if [z for z, _ in ranked] != list(range(len(ranked))):
            for rank, (_, t) in enumerate(ranked):
                t.z = rank


def plan_from_layout(
    outcome: LayoutOutcome, source: dict, source_artboard: str, origin: str
) -> LayoutPlan:
    """One story card; role nodes of the source artboard move into it unless their target names another parent; nodes
    inside a group (the CTA's children) keep their group."""
    nodes = {n["id"]: n for n in source["nodes"]}
    targets = []
    for t in outcome.targets.values():
        n = nodes.get(t.node_id)
        top_level = n is None or n.get("parent") == source_artboard
        targets.append(
            Target(**{**t.__dict__, "parent": t.parent or ("story-1" if top_level else None)})
        )
    present = {n.get("role") for n in source["nodes"] if n.get("parent") == source_artboard}
    if any(
        r not in present for r in OPTIONAL_ROLES
    ):  # only absent parts cause gaps; a bad index in a rule must still fail
        _close_stacking_gaps(targets, nodes)
    kinds = {t.node_id: nodes[t.node_id]["type"] if t.node_id in nodes else "rect" for t in targets}
    roles = {}
    for n in source["nodes"]:
        if n.get("role"):
            roles[n["id"]] = n["role"]
            for k in source["nodes"]:
                if k.get("parent") == n["id"]:
                    roles[k["id"]] = f"{n['role']}/{k['type']}"
    return LayoutPlan(source_artboard, [card("story-1", 1)], targets, kinds, roles, origin=origin)
