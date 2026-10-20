import pytest

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from tests.unit.drawio.fixtures import LABEL, drawio, label, model, node


def page(cells, **kw):
    return load_drawio(drawio(model(cells, **kw))).pages[0]


def test_supported_label_is_movable_and_node_is_fixed():
    c = classify(page([node("n1", 40, 40), label("l1", 50, 100)]))
    assert c.movable == ("l1",) and c.fixed == ("n1",)


@pytest.mark.parametrize(
    "cell, reason",
    [
        (label("l1", 50, 100, style=LABEL.format(align="center") + "rotation=30;"), "rotated"),
        (
            '<UserObject id="l1" label="x"><mxCell style="text;" vertex="1" parent="1">'
            '<mxGeometry x="1" y="1" width="9" height="9" as="geometry"/></mxCell></UserObject>',
            "wrapper",
        ),
        (
            '<mxCell id="l1" value="x" style="text;" vertex="1" parent="1">'
            '<mxGeometry x="0.5" y="0.5" relative="1" as="geometry"/></mxCell>',
            "relative",
        ),
    ],
)
def test_unsupported_labels_become_obstacles_with_reasons(cell, reason):
    c = classify(page([node("n1", 40, 40), cell]))
    assert "l1" in c.fixed and reason in c.reasons["l1"]


def test_group_children_are_obstacles_in_document_coordinates_and_container_is_not_counted():
    g = (
        '<mxCell id="g" style="group;" vertex="1" parent="1">'
        '<mxGeometry x="100" y="100" width="200" height="100" as="geometry"/></mxCell>'
    )
    child = (
        '<mxCell id="k" value="c" style="rounded=0;" vertex="1" parent="g">'
        '<mxGeometry x="10" y="20" width="30" height="40" as="geometry"/></mxCell>'
    )
    c = classify(page([g, child]))
    assert c.fixed == ("k",) and c.absolute["k"] == (110, 120, 30, 40)


def test_missing_coordinates_count_as_zero():
    assert classify(page([label("l1", None, None)])).absolute["l1"][:2] == (0, 0)


@pytest.mark.parametrize(
    "kw, cells, reason",
    [
        ({"extra": ""}, [node("n1", -10, 0)], "outside the page"),
        ({"w": 100}, [node("n1", 50, 0)], "outside the page"),
        (
            {},
            [node(f"n{i}", (i % 20) * 12, (i // 20) * 12, 10, 10) for i in range(401)],
            "400 objects",
        ),
        ({}, [label(f"l{i}", (i % 20) * 12, (i // 20) * 25, w=10) for i in range(201)], "200 movable labels"),
        (
            {},
            [label("l1", 0, 0, style=LABEL.format(align="left") + "fontFamily=Comic Sans MS;")],
            "font",
        ),
    ],
)
def test_page_refusals(kw, cells, reason):
    with pytest.raises(DrawioRefused, match=reason):
        classify(page(cells, **kw))


def test_page_scale_and_page_zero_are_refused():
    raw = drawio(model([node("n1", 0, 0)]).replace('pageScale="1"', 'pageScale="2"'))
    with pytest.raises(DrawioRefused, match="pageScale"):
        classify(load_drawio(raw).pages[0])
    raw = drawio(model([node("n1", 0, 0)]).replace('page="1"', 'page="0"'))
    with pytest.raises(DrawioRefused, match="page view"):
        classify(load_drawio(raw).pages[0])


def test_corpus_pages_classify():
    for name in ("d1", "d2", "d3"):
        raw = open(f"tests/fixtures/drawio_corpus/dev/{name}.drawio", "rb").read()
        for p in load_drawio(raw).pages:
            c = classify(p)
            assert c.movable and c.fixed
