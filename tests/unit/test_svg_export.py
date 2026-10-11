"""The exported SVG is script-free, well-formed, keeps ids/geometry exactly, carries provenance, and cannot be injected through ids or text."""

import xml.etree.ElementTree as ET

from open_apprentice.api.svg_export import build_svg, safe_id

NS = {"s": "http://www.w3.org/2000/svg", "oa": "https://open-apprentice.invalid/ns"}
BOXES = [
    {"id": "card", "x": 100, "y": 100, "w": 300, "h": 80, "role": "card"},
    {"id": "badge", "x": 356.5, "y": 124, "w": 20, "h": 20, "role": "badge"},
    {"id": "proto", "x": 0, "y": 0, "w": 20, "h": 20, "role": "prototype"},
]


def parse(svg):
    return ET.fromstring(svg.encode())


def test_geometry_ids_and_layers_survive_a_round_trip_through_an_independent_xml_parser():
    root = parse(build_svg(BOXES, {"w": 800, "h": 600}, {"rule": "top-right inset 12"}))
    rects = {r.get("id"): r for r in root.iterfind(".//s:rect", NS)}
    assert set(rects) == {"card", "badge", "proto"}
    assert (rects["badge"].get("x"), rects["badge"].get("width")) == ("356.5", "20")
    assert [g.get("id") for g in root.iterfind("s:g", NS)] == [
        "layer_card",
        "layer_prototype",
        "layer_badge",
    ]
    assert root.get("viewBox") == "0 0 800 600"


def test_provenance_is_embedded_and_no_active_content_is_possible():
    svg = build_svg(
        BOXES,
        {"w": 800, "h": 600},
        {"rule": "x</oa:rule><script>alert(1)</script>", "model_used": "none"},
    )
    root = parse(svg)
    assert root.find(".//oa:model_used", NS).text == "none"
    assert "<script" not in svg.lower() and root.find(".//s:script", NS) is None
    assert root.find(".//oa:rule", NS).text.startswith(
        "x</oa:rule><script>"
    )  # escaped text, not markup


def test_hostile_ids_are_sanitised_and_kept_unique():
    assert safe_id('a" onload="x') == "a__onload__x" and safe_id("9lives").startswith("n_")
    root = parse(
        build_svg(
            [
                {"id": "a b", "x": 0, "y": 0, "w": 1, "h": 1, "role": "x"},
                {"id": "a_b", "x": 0, "y": 0, "w": 1, "h": 1},
            ],
            {"w": 10, "h": 10},
            {},
        )
    )
    ids = [r.get("id") for r in root.iterfind(".//s:rect", NS)]
    assert len(ids) == len(set(ids)) == 2
