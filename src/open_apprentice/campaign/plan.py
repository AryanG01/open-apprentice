"""A layout plan: the rule's targets placed into concrete story cards (spec 7.4-7.5)."""

from __future__ import annotations

from dataclasses import dataclass, field

from open_apprentice.campaign.layout_rule import LayoutOutcome, Target
from open_apprentice.campaign.limits import SAFE, STORY_H, STORY_W

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
    clones: list[tuple[str, str]] = field(default_factory=list)  # (source id, new id)
    origin: str = "search"


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
    kinds = {t.node_id: nodes[t.node_id]["type"] if t.node_id in nodes else "rect" for t in targets}
    return LayoutPlan(source_artboard, [card("story-1", 1)], targets, kinds, origin=origin)
