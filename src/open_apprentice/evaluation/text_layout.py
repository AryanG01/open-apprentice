"""Independent text layout for the campaign verifier (spec 7.7).

Reads glyph advances straight from the vendored Liberation Sans font tables. It shares no code with the engine and never asks
the engine to measure. Wrapping follows the documented Konva `wrap: "word"` rule (longest prefix that fits, cut back to the
last space or hyphen, trim). Kerning is ignored, so widths can differ from the browser's by a little; the verifier treats a
line-count disagreement with the engine as a failure (spec 7.7), and the fixtures stay clear of wrap boundaries.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from fontTools.ttLib import TTFont

# ponytail: repo-relative path; the API image would need services/engine/vendor copied in before the verifier runs there.
_VENDOR = Path(__file__).resolve().parents[3] / "services" / "engine" / "vendor"
_FILES = {False: "LiberationSans-Regular.ttf", True: "LiberationSans-Bold.ttf"}


@cache
def _manifest() -> dict:
    return json.loads((_VENDOR / "MANIFEST.json").read_text())


def _load_font(name: str, expected_sha256: str) -> tuple[dict[int, str], dict[str, int], int]:
    data = (_VENDOR / "fonts" / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError(f"font {name} does not match its recorded hash")
    font = TTFont(Path(_VENDOR / "fonts" / name))
    advances = {glyph: adv for glyph, (adv, _lsb) in font["hmtx"].metrics.items()}
    return font.getBestCmap(), advances, font["head"].unitsPerEm


@cache
def _font(bold: bool) -> tuple[dict[int, str], dict[str, int], int]:
    name = _FILES[bold]
    return _load_font(name, _manifest()["files"][f"fonts/{name}"]["sha256"])


def advance_width(text: str, font_size: float, bold: bool) -> float:
    cmap, advances, upem = _font(bold)
    units = sum(advances[cmap.get(ord(ch), ".notdef")] for ch in text)
    return units * font_size / upem


def wrap(text: str, width: float, font_size: float, bold: bool) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        line = para
        while advance_width(line, font_size, bold) > width:
            lo, hi = 0, len(line)  # longest prefix that fits
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if advance_width(line[:mid], font_size, bold) <= width:
                    lo = mid
                else:
                    hi = mid - 1
            cut = max(lo, 1)
            at = max(line.rfind(" ", 0, cut), line.rfind("-", 0, cut)) + 1
            if at > 0:
                cut = at
            lines.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
            if not line:
                break
        else:
            lines.append(line)
    return lines


@dataclass
class Fit:
    lines: list[str]
    height: float
    word_too_wide: bool


def fit(text: str, width: float, font_size: float, bold: bool, line_height: float) -> Fit:
    lines = wrap(text, width, font_size, bold)
    wide = any(advance_width(w, font_size, bold) > width for w in text.split())
    return Fit(lines, len(lines) * font_size * line_height, wide)
