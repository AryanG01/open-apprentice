"""Versioned, hashed supported-domain manifest (spec 8.9). Requests outside it are 'unsupported' for
symbolic claims even if concrete execution works. Tuned on dev/validation only, then frozen."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

import yaml


@dataclass(frozen=True)
class DomainManifest:
    version: int = 1
    object_count_min: int = 2
    object_count_max: int = 8
    card_min: int = 24
    card_max: int = 512
    canvas_w_min: int = 64
    canvas_w_max: int = 1600
    canvas_h_min: int = 64
    canvas_h_max: int = 1200
    query_visible_difference_px: Fraction = Fraction(1)

    @classmethod
    def from_config(cls, path: str = "configs/dev.yaml") -> "DomainManifest":
        d = yaml.safe_load(open(path))["supported_domain"]
        return cls(
            version=d["version"],
            object_count_min=d["object_count"]["min"],
            object_count_max=d["object_count"]["max"],
            card_min=d["card_size_px"]["min"],
            card_max=d["card_size_px"]["max"],
            canvas_w_min=d["canvas_width_px"]["min"],
            canvas_w_max=d["canvas_width_px"]["max"],
            canvas_h_min=d["canvas_height_px"]["min"],
            canvas_h_max=d["canvas_height_px"]["max"],
            query_visible_difference_px=Fraction(str(d["query_visible_difference_px"])),
        )

    @classmethod
    def from_canonical(cls, d: dict[str, Any]) -> "DomainManifest":
        d = dict(d)
        d["query_visible_difference_px"] = Fraction(d["query_visible_difference_px"])
        return cls(**d)

    def canonical(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["query_visible_difference_px"] = str(self.query_visible_difference_px)
        return d

    @property
    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.canonical(), sort_keys=True).encode()).hexdigest()

    def contains(self, objects: list[dict], canvas: dict) -> bool:
        """Is this concrete input inside the declared domain (finite, in-canvas, sizes in range)?"""
        cw, ch = Fraction(canvas["w"]), Fraction(canvas["h"])
        if not (
            self.canvas_w_min <= cw <= self.canvas_w_max
            and self.canvas_h_min <= ch <= self.canvas_h_max
        ):
            return False
        if not self.object_count_min <= len(objects) <= self.object_count_max:
            return False
        for o in objects:
            x, y, w, h = (Fraction(o[k]) for k in ("x", "y", "w", "h"))
            if not (self.card_min <= w <= self.card_max and self.card_min <= h <= self.card_max):
                return False
            if x < 0 or y < 0 or x + w > cw or y + h > ch:
                return False
        return True
