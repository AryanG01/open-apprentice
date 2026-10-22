"""Frozen layout limits for the story format (spec 7.1, 10; frozen by plan 9A)."""

STORY_W = 1080
STORY_H = 1920
SAFE = {"top": 220, "right": 72, "bottom": 220, "left": 72}
MIN_FONT = 40
MIN_LEGAL_FONT = 24
MIN_CTA_H = 96
MIN_HERO_W = 432
ROLES: tuple[str, ...] = (
    "background",
    "brand_mark",
    "product_image",
    "headline",
    "price",
    "cta",
    "legal",
)


def fit_limits() -> dict:
    """The `limits` argument of the engine's observe_fit tool."""
    return {
        "safe": dict(SAFE),
        "min_font": MIN_FONT,
        "min_legal_font": MIN_LEGAL_FONT,
        "min_cta_height": MIN_CTA_H,
        "min_hero_width": MIN_HERO_W,
    }
