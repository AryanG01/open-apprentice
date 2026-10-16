"""Spec 6 round-trip matrix: every row patches, publishes and re-measures through the real engine."""

from fractions import Fraction as F

import pytest

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.patch import plan_edits
from open_apprentice.drawio.publish import publish
from open_apprentice.drawio.render import render_page
from open_apprentice.drawio.scene import build_scene
from open_apprentice.storage.store import LocalStore
from tests.unit.drawio.fixtures import drawio, label, model, node


def run(engine_url, tmp_path, raw, cell, dx, dy, page_index=0):
    f = load_drawio(raw)
    page = f.pages[page_index]
    c = classify(page)
    r = render_page(page, engine_url)
    nodes = [n for n in c.fixed if n in r.nodes]
    s = build_scene(c, r, {m: (nodes[0], "note") for m in c.movable})
    o = next(o for o in s.scene["objects"] if o["id"] == cell)
    targets = {cell: (o["x"] + dx, o["y"] + dy)}
    edits = plan_edits(page, s.offsets, targets)
    store = LocalStore(tmp_path)
    rec = publish(
        store,
        f"out/{cell}.drawio",
        f,
        page_index,
        edits,
        targets,
        s,
        lambda p: render_page(p, engine_url),
    )
    return f, rec, store.get(f"out/{cell}.drawio")


@pytest.mark.parametrize("align", ["left", "center", "right"])
def test_aligned_html_labels(engine_url, tmp_path, align):
    raw = drawio(model([node("n1", 40, 40), label("l1", 200, 200, align=align)]))
    _, rec, _ = run(engine_url, tmp_path, raw, "l1", F(20), F(-10))
    assert rec.published, rec


def test_plain_text_label(engine_url, tmp_path):
    style = "text;align=left;verticalAlign=middle;"
    raw = drawio(model([node("n1", 40, 40), label("l1", 200, 200, style=style)]))
    _, rec, _ = run(engine_url, tmp_path, raw, "l1", F(15), F(5))
    assert rec.published, rec


def test_nonzero_viewer_translate(engine_url, tmp_path):
    raw = drawio(model([node("n1", 500, 400), label("l1", 600, 520)], w=900, h=700))
    _, rec, _ = run(engine_url, tmp_path, raw, "l1", F(10), F(10))
    assert rec.published, rec


def test_fractional_target_requires_rounding(engine_url, tmp_path):
    raw = drawio(model([node("n1", 40, 40), label("l1", 200, 200)]))
    _, rec, _ = run(engine_url, tmp_path, raw, "l1", F(75, 2), F(-12))
    row = rec.conformance["labels"]["l1"]
    assert rec.published and row["exact"] != [str(v) for v in row["serialized"]], rec


def test_missing_coordinates_inserted(engine_url, tmp_path):
    raw = drawio(model([node("n1", 300, 200), label("l1", None, None)]))
    _, rec, out = run(engine_url, tmp_path, raw, "l1", F(30), F(40))
    geo = {c.id: c for c in load_drawio(out.data).pages[0].cells}["l1"].geometry
    assert rec.published and "x" in geo and "y" in geo, rec


def test_compressed_page(engine_url, tmp_path):
    raw = drawio(model([node("n1", 40, 40), label("l1", 200, 200)]), compressed=(True,))
    _, rec, out = run(engine_url, tmp_path, raw, "l1", F(10), F(10))
    assert rec.published and not load_drawio(out.data).pages[0].compressed, rec


def test_multi_page_untouched_bytes(engine_url, tmp_path):
    raw = drawio(model([node("z", 10, 10)]), model([node("n1", 40, 40), label("l1", 200, 200)]))
    f, rec, out = run(engine_url, tmp_path, raw, "l1", F(10), F(10), page_index=1)
    s, e = f.pages[0].content_span
    assert rec.published and out.data[s:e] == f.raw[s:e], rec


def test_real_corpus_file_round_trip(engine_url, tmp_path):
    raw = open("tests/fixtures/drawio_corpus/dev/d2.drawio", "rb").read()
    cell = classify(load_drawio(raw).pages[0]).movable[0]
    _, rec, _ = run(engine_url, tmp_path, raw, cell, F(0), F(1))
    assert rec.published, rec


def test_refuses_unmeasurable_label(engine_url):
    raw = drawio(model([node("n1", 40, 40), label("l1", 200, 200, value="&amp;nbsp;")]))
    page = load_drawio(raw).pages[0]
    with pytest.raises(DrawioRefused, match="measured"):
        build_scene(classify(page), render_page(page, engine_url), {"l1": ("n1", "note")})


def test_refuses_out_of_rectangle_content():
    with pytest.raises(DrawioRefused, match="outside the page"):
        classify(load_drawio(drawio(model([node("n1", 560, 40)]))).pages[0])
