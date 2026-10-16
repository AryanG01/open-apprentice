from fractions import Fraction as F

import pytest

from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.patch import apply_geometry
from tests.unit.drawio.fixtures import drawio, label, model, node

M = model([node("n1", 40, 40, 100, 50), label("l1", 50, 100)])


def cells(raw, page=0):
    return {c.id: c for c in load_drawio(raw).pages[page].cells}


def test_resize_and_move_a_node():
    f = load_drawio(drawio(M))
    out, ser = apply_geometry(f, 0, {"n1": {"w": F(201, 2), "x": F(60)}}, None, f.doc_hash)
    g = cells(out)["n1"].geometry
    assert (g["width"], g["x"], g["height"]) == ("101", "60", "50") and ser == {
        "n1": {"w": 101, "x": 60}
    }


def test_narrow_the_page_and_keep_other_bytes():
    f = load_drawio(drawio(M))
    out, _ = apply_geometry(f, 0, {}, F(300), f.doc_hash)
    assert load_drawio(out).pages[0].model["pageWidth"] == "300"
    assert f.raw.split(b'pageWidth="600"') == out.split(b'pageWidth="300"')


def test_missing_attribute_is_inserted():
    m = model(
        [
            '<mxCell id="n1" value="N" style="rounded=0;" vertex="1" parent="1"><mxGeometry width="10" height="10" as="geometry"/></mxCell>'
        ]
    )
    f = load_drawio(drawio(m))
    out, _ = apply_geometry(f, 0, {"n1": {"x": F(5), "y": F(6)}}, None, f.doc_hash)
    assert (cells(out)["n1"].geometry["x"], cells(out)["n1"].geometry["y"]) == ("5", "6")


def test_compressed_page_and_stale_hash():
    f = load_drawio(drawio(M, model([node("z", 1, 1)]), compressed=(True, True)))
    out, _ = apply_geometry(f, 0, {"n1": {"h": F(80)}}, None, f.doc_hash)
    g = load_drawio(out)
    assert (
        not g.pages[0].compressed
        and g.pages[1].compressed
        and cells(out)["n1"].geometry["height"] == "80"
    )
    with pytest.raises(DrawioRefused, match="changed"):
        apply_geometry(f, 0, {"n1": {"h": F(80)}}, None, "0" * 64)
