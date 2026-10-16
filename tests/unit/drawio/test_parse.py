import pytest

from open_apprentice.drawio.parse import DrawioRefused, compress_page_xml, load_drawio
from tests.unit.drawio.fixtures import drawio, label, model, node

CORPUS = "tests/fixtures/drawio_corpus/dev"


def test_reads_uncompressed_page_cells_and_geometry_span():
    f = load_drawio(drawio(model([node("n1", 40, 40), label("l1", 50, 100)])))
    page = f.pages[0]
    cells = {c.id: c for c in page.cells}
    assert cells["l1"].style["text"] == "" and cells["l1"].geometry["x"] == "50"
    s, e = cells["l1"].geometry_span
    assert page.xml[s:e].startswith(b"<mxGeometry") and page.xml[s:e].endswith(b">")
    assert f.raw[page.content_span[0] : page.content_span[1]] == page.xml


def test_reads_compressed_page_identically():
    m = model([node("n1", 40, 40), label("l1", 50, 100)])
    a = load_drawio(drawio(m)).pages[0]
    b = load_drawio(drawio(m, compressed=(True,))).pages[0]
    assert b.compressed and [c.id for c in a.cells] == [c.id for c in b.cells]


def test_real_corpus_files_load():
    for name in ("d1", "d2", "d3"):
        f = load_drawio(open(f"{CORPUS}/{name}.drawio", "rb").read())
        assert f.pages and all(p.model["pageScale"] == "1" for p in f.pages)


def test_missing_coordinates_are_absent_not_invented():
    cells = load_drawio(drawio(model([label("l1", None, None)]))).pages[0].cells
    c = {c.id: c for c in cells}["l1"]
    assert "x" not in c.geometry and "y" not in c.geometry


def test_wrapper_cells_take_the_wrapper_id_and_are_marked():
    m = model(
        [
            '<UserObject id="u1" label="hi"><mxCell style="text;" vertex="1" parent="1">'
            '<mxGeometry x="1" y="2" width="3" height="4" as="geometry"/></mxCell></UserObject>'
        ]
    )
    c = {c.id: c for c in load_drawio(drawio(m)).pages[0].cells}["u1"]
    assert c.wrapper and c.value == "hi"


@pytest.mark.parametrize(
    "raw, reason",
    [
        (b'<!DOCTYPE x [<!ENTITY a "b">]><mxfile/>', "DOCTYPE"),
        (drawio(model([node("n1", 0, 0), node("n1", 10, 10)])), "duplicate cell id"),
        (
            drawio(
                model(
                    ['<mxCell id="z" vertex="1" parent="nope"><mxGeometry as="geometry"/></mxCell>']
                )
            ),
            "unknown parent",
        ),
        (b"\xff\xfe<mxfile/>", "UTF-8"),
        (b"<mxfile>" + b"x" * (2 * 1024 * 1024) + b"</mxfile>", "2 MB"),
        (
            drawio(model([label("l1", 0, 0, value="&lt;img src=x onerror=alert(1)&gt;")])),
            "label content",
        ),
        (
            drawio(model([label("l1", 0, 0, value="&lt;script&gt;x&lt;/script&gt;")])),
            "label content",
        ),
    ],
)
def test_refusals_carry_a_reason(raw, reason):
    with pytest.raises(DrawioRefused, match=reason):
        load_drawio(raw)


def test_decompression_bomb_is_refused():
    bomb = compress_page_xml(
        b"<mxGraphModel><root>" + b" " * (5 * 1024 * 1024) + b"</root></mxGraphModel>"
    )
    with pytest.raises(DrawioRefused, match="4 MB"):
        load_drawio(f'<mxfile><diagram id="p" name="P">{bomb}</diagram></mxfile>'.encode())


def test_simple_formatting_html_is_allowed():
    load_drawio(drawio(model([label("l1", 0, 0, value="&lt;b&gt;bold&lt;/b&gt;&lt;br&gt;x")])))
