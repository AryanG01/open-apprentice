"""Regression tests for the Plan 3 whole-branch review findings (each failed before its fix)."""

import signal
from fractions import Fraction as F

import pytest

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio, page_document
from open_apprentice.drawio.patch import plan_edits
from open_apprentice.drawio.publish import publish
from open_apprentice.drawio.scene import build_scene
from open_apprentice.storage.store import LocalStore
from tests.unit.drawio.fixtures import drawio, model, node
from tests.unit.drawio.test_publish import M, fake_render


class _Timeout(Exception):
    pass


@pytest.fixture
def deadline():
    def boom(*_):
        raise _Timeout("took too long")

    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(2)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


# ---- Critical 1: file text never reaches the renderer wrapper unescaped
INJECTED_ID = (
    "x&quot;&gt;&lt;mxGraphModel&gt;&lt;root&gt;&lt;mxCell id=&quot;0&quot;/&gt;"
    "&lt;mxCell id=&quot;e&quot; value=&quot;&amp;lt;img src=x onerror=alert(1)&amp;gt;&quot; "
    "style=&quot;text;html=1;&quot; vertex=&quot;1&quot; parent=&quot;0&quot;/&gt;"
    "&lt;/root&gt;&lt;/mxGraphModel&gt;&lt;/diagram&gt;&lt;diagram id=&quot;y"
)


def test_diagram_id_cannot_inject_a_second_page_into_the_renderer():
    raw = (
        f'<mxfile><diagram id="{INJECTED_ID}" name="P">'
        + model([node("n1", 0, 0)])
        + "</diagram></mxfile>"
    ).encode()
    with pytest.raises(DrawioRefused):  # unsafe page ids are now refused at load (hardening review M1)
        load_drawio(raw)


def test_benign_ampersand_in_page_id_still_renders_as_one_page():
    raw = (
        '<mxfile><diagram id="a&amp;b" name="P">'
        + model([node("n1", 0, 0)])
        + "</diagram></mxfile>"
    ).encode()
    with pytest.raises(DrawioRefused):
        load_drawio(raw)


def test_userobject_placeholder_attributes_are_checked_like_labels():
    m = model(
        [
            '<UserObject id="u1" label="%evil%" placeholders="1" evil="&lt;img src=x onerror=alert(1)&gt;">'
            '<mxCell style="text;html=1;" vertex="1" parent="1">'
            '<mxGeometry x="1" y="2" width="30" height="20" as="geometry"/></mxCell></UserObject>'
        ]
    )
    with pytest.raises(DrawioRefused, match="label content"):
        load_drawio(drawio(m))


# ---- Important 2: parent cycles are refused, never looped on
@pytest.mark.parametrize(
    "cells",
    [
        [
            '<mxCell id="a" vertex="1" parent="b"><mxGeometry x="1" y="1" width="5" height="5" as="geometry"/></mxCell>',
            '<mxCell id="b" vertex="1" parent="a"><mxGeometry x="1" y="1" width="5" height="5" as="geometry"/></mxCell>',
        ],
        [
            '<mxCell id="a" vertex="1" parent="a"><mxGeometry x="1" y="1" width="5" height="5" as="geometry"/></mxCell>'
        ],
    ],
)
def test_parent_cycles_are_refused_quickly(deadline, cells):
    with pytest.raises(DrawioRefused, match="cycl"):
        classify(load_drawio(drawio(model(cells))).pages[0])


# ---- Important 3: hostile numbers are refused quickly and cleanly
@pytest.mark.parametrize("value", ["1e999999999", "1/0", "nan", "0x10", "1_000"])
def test_hostile_geometry_numbers_are_refused(deadline, value):
    cell = (
        f'<mxCell id="n1" value="N" style="rounded=0;" vertex="1" parent="1">'
        f'<mxGeometry x="{value}" y="0" width="10" height="10" as="geometry"/></mxCell>'
    )
    with pytest.raises(DrawioRefused, match="not a number"):
        classify(load_drawio(drawio(model([cell]))).pages[0])


def test_hostile_page_size_is_refused(deadline):
    raw = drawio(model([node("n1", 0, 0)]).replace('pageWidth="600"', 'pageWidth="1e999999999"'))
    with pytest.raises(DrawioRefused, match="not a number"):
        classify(load_drawio(raw).pages[0])


def test_ordinary_draw_io_numbers_still_parse():
    cell = (
        '<mxCell id="n1" value="N" style="rounded=0;" vertex="1" parent="1">'
        '<mxGeometry x="12.5" y="-0" width="10" height="7.25" as="geometry"/></mxCell>'
    )
    assert classify(load_drawio(drawio(model([cell]))).pages[0]).absolute["n1"] == (
        F(25, 2),
        0,
        10,
        F(29, 4),
    )


# ---- Important 5: publish refuses a document other than the one measured
def test_publish_refuses_a_document_changed_since_measurement(tmp_path):
    v1 = load_drawio(drawio(M))
    page = v1.pages[0]
    before = build_scene(classify(page), fake_render(page), {"l1": ("n1", "note")}, v1.doc_hash)
    targets = {"l1": (F(150), F(58))}
    edits = plan_edits(page, before.offsets, targets)
    v2 = load_drawio(drawio(M.replace('x="300"', 'x="310"')))  # a neighbour moved; l1 untouched
    store = LocalStore(tmp_path)
    with pytest.raises(DrawioRefused, match="changed"):
        publish(store, "out/x.drawio", v2, 0, edits, targets, before, fake_render)
    assert store.get("out/x.drawio") is None
