"""Library diagrams render in the real draw.io engine with every note single-line and mapped to its own box."""

import json
from pathlib import Path

import pytest

from open_apprentice.drawio import mapping as mp
from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import load_drawio
from open_apprentice.drawio.render import render_page
from open_apprentice.drawio.scene import build_scene

LIB = Path("apps/web/public/samples/library")
FILES = [f["file"] for f in json.loads((LIB / "index.json").read_text())["files"]][:18]


@pytest.mark.parametrize("name", FILES)
def test_library_diagram_maps_each_note_to_its_box(engine_url, name):
    f = load_drawio((LIB / name).read_bytes())
    c = classify(f.pages[0])
    r = render_page(f.pages[0], engine_url)
    m = mp.propose(c, r, f.doc_hash)
    assert {cid: e["node_id"] for cid, e in m.labels.items()} == {
        cid: cid.removesuffix("-note") for cid in c.movable
    }
    scene = build_scene(
        c, r, {cid: (e["node_id"], "note") for cid, e in m.labels.items()}, f.doc_hash
    )
    assert len(scene.movable) == len(c.movable)  # no note renders on two lines
