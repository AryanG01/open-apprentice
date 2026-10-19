"""The demo library (apps/web/public/samples/library): generated, owner-authored diagrams that every import step accepts."""

import hashlib
import json
from pathlib import Path

import pytest

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import load_drawio

LIB = Path("apps/web/public/samples/library")
INDEX = (
    json.loads((LIB / "index.json").read_text()) if (LIB / "index.json").exists() else {"files": []}
)


def test_the_library_has_at_least_100_diagrams_listed_with_hashes():
    assert len(INDEX["files"]) >= 100
    on_disk = sorted(p.name for p in LIB.glob("*.drawio"))
    assert on_disk == sorted(f["file"] for f in INDEX["files"])
    for f in INDEX["files"]:
        assert hashlib.sha256((LIB / f["file"]).read_bytes()).hexdigest() == f["sha256"], f["file"]


@pytest.mark.parametrize("entry", INDEX["files"], ids=lambda f: f["file"])
def test_every_library_diagram_is_accepted_with_all_labels_movable(entry):
    raw = (LIB / entry["file"]).read_bytes()
    assert b"image=" not in raw and b"data:" not in raw and b"http" not in raw.split(b">", 1)[1]
    page = load_drawio(raw).pages[0]
    c = classify(page)
    assert len(c.movable) == entry["labels"] and not c.reasons
    assert 4 <= len(c.movable) <= 16


def test_the_library_is_reproducible_from_its_seed(tmp_path):
    from scripts.corpus.generate_library import generate

    generate(tmp_path, count=3)
    for f in INDEX["files"][:3]:
        assert (tmp_path / f["file"]).read_bytes() == (LIB / f["file"]).read_bytes()


@pytest.mark.parametrize("entry", INDEX["files"], ids=lambda f: f["file"])
def test_the_demo_rule_fits_every_library_diagram(entry):
    """Every note left-aligned 8 below its box stays on the page and overlaps nothing (geometry upper bounds)."""
    c = classify(load_drawio((LIB / entry["file"]).read_bytes()).pages[0])
    boxes = {k: v for k, v in c.absolute.items() if k not in c.movable and k != "title"}
    placed = {}
    for lid in c.movable:
        ax, ay, aw, ah = c.absolute[lid.removesuffix("-note")]
        _, _, w, h = c.absolute[lid]
        placed[lid] = (ax, ay + ah + 8, w, h)
    every = list(boxes.values()) + list(placed.values())
    for lid, (x, y, w, h) in placed.items():
        assert 0 <= x and x + w <= c.width and y + h <= c.height, lid
        for o in every:
            if o == (x, y, w, h):
                continue
            ox, oy, ow, oh = o
            assert x + w <= ox or ox + ow <= x or y + h <= oy or oy + oh <= y, (lid, o)
