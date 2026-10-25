"""The two built-in overflow outcomes (spec 7.5). Fixed reference transforms of the learned base plan, labelled "builtin":
never learned, never credited to the learner or to a model."""

from __future__ import annotations

import copy

from open_apprentice.campaign.layout_rule import Target
from open_apprentice.campaign.limits import MIN_HERO_W, SAFE, STORY_H, STORY_W
from open_apprentice.campaign.plan import LayoutPlan, card
from open_apprentice.concepts.rules import ASK_OPTIONS

BUILTINS = ASK_OPTIONS  # ("builtin_shrink_hero", "builtin_split_two_cards")
ORIGIN = "builtin"
HERO_GAP = 40  # shrink: headline starts this far below the shrunken hero
CARD2_PRICE_TOP = 800  # split: card 2's offer block starts here
OFFER_GAP = 32  # split: price to CTA
CARD2_LEGAL_H = 320  # split: legal frame height, bottom-anchored
BOTTOM = STORY_H - SAFE["bottom"]
OFFER = (
    "price",
    "cta",
    "legal",
)  # the parts card 2 carries; any of them may be absent from a banner


def split_applicable(base: LayoutPlan) -> bool:
    """A banner with no price, button or small print has nothing to put on a second card."""
    return any(role in OFFER for role in _by_role(base))


def _by_role(plan: LayoutPlan) -> dict[str, Target]:
    return {plan.roles[t.node_id]: t for t in plan.targets if t.node_id in plan.roles}


def shrink_hero(base: LayoutPlan) -> LayoutPlan:
    plan = copy.deepcopy(base)
    r = _by_role(plan)
    hero, head = r["product_image"], r["headline"]
    w = min(hero.w, MIN_HERO_W)
    h = hero.h * w / hero.w
    hero.x, hero.w, hero.h = (STORY_W - w) / 2, w, h
    bottom = head.y + head.h
    head.y = hero.y + h + HERO_GAP
    head.h = bottom - head.y
    plan.origin = ORIGIN
    return plan


def split_two_cards(base: LayoutPlan) -> LayoutPlan:
    plan = copy.deepcopy(base)
    r = _by_role(plan)
    bg, logo = r["background"], r["brand_mark"]
    plan.artboards = [card("story-1", 1), card("story-2", 2)]
    plan.clones = [(bg.node_id, f"{bg.node_id}-2"), (logo.node_id, f"{logo.node_id}-2")]
    copies = []
    for src in (bg, logo):
        c = copy.deepcopy(src)
        c.node_id = f"{src.node_id}-2"
        copies.append(c)
        plan.kinds[c.node_id] = plan.kinds[src.node_id]
        plan.roles[c.node_id] = plan.roles[src.node_id]
    head = r["headline"]
    head.h = BOTTOM - head.y
    offer = [r[k] for k in OFFER if k in r]
    top = CARD2_PRICE_TOP
    for part in offer:  # price, then button below it, then the small print bottom-anchored
        if part is r.get("legal"):
            part.h = CARD2_LEGAL_H
            part.y = BOTTOM - CARD2_LEGAL_H
        else:
            part.y = top
            top += part.h + OFFER_GAP
    cards = {
        "story-1": [bg, logo, r["product_image"], head],
        "story-2": [*copies, *offer],
    }
    for card_id, members in cards.items():
        for z, t in enumerate(members):  # each card stacks from zero, in reading order
            t.parent, t.z = card_id, z
    plan.targets += copies
    plan.origin = ORIGIN
    return plan
