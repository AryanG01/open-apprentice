"""Frozen layout limits for the story format (spec 7.1, 10; frozen by plan 9A)."""

STORY_W = 1080
STORY_H = 1920
SAFE = {"top": 220, "right": 72, "bottom": 220, "left": 72}
MIN_FONT = 40
MIN_LEGAL_FONT = 24
MIN_CTA_H = 96
MIN_HERO_W = 432
MIN_HERO_TALL_H = 480  # a tall, narrow product (a bottle) is large enough when it is at least this tall: width OR height, so every earlier result still passes
ROLES: tuple[str, ...] = (
    "background",
    "brand_mark",
    "product_image",
    "headline",
    "price",
    "cta",
    "legal",
)
# real designs rarely carry all of these (docs/evaluation/real_world_coverage.md); each one present is still fully checked
OPTIONAL_ROLES: tuple[str, ...] = ("price", "cta", "legal")
REQUIRED_ROLES: tuple[str, ...] = tuple(r for r in ROLES if r not in OPTIONAL_ROLES)


def fit_limits() -> dict:
    """The `limits` argument of the engine's observe_fit tool."""
    return {
        "safe": dict(SAFE),
        "min_font": MIN_FONT,
        "min_legal_font": MIN_LEGAL_FONT,
        "min_cta_height": MIN_CTA_H,
        "min_hero_width": MIN_HERO_W,
        "min_hero_tall_height": MIN_HERO_TALL_H,
    }
