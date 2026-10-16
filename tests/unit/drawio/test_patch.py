from fractions import Fraction as F

import pytest

from open_apprentice.drawio.parse import DrawioRefused, load_drawio
from open_apprentice.drawio.patch import Edit, apply_edits, plan_edits, round_half_up
from tests.unit.drawio.fixtures import drawio, label, model, node

M = model([node("n1", 40, 40), label("l1", 50, 100), label("l2", None, None)])


def test_round_half_up_matches_the_renderer():
    got = [round_half_up(F(v)) for v in ("0.5", "1.5", "37.25", "37.5", "37.75", "-0.5")]
    assert got == [1, 2, 37, 38, 38, 0]


def test_plan_subtracts_the_offset_and_keeps_exact_serialized_and_old_separate():
    page = load_drawio(drawio(M)).pages[0]
    (e,) = plan_edits(page, {"l1": (F(2), F(3))}, {"l1": (F(201, 2), F(140))})
    assert e.exact == (F(197, 2), F(137)) and e.serialized == (99, 137)
    assert e.expected_old == ("50", "100")


def test_uncompressed_patch_changes_only_the_geometry_tag():
    f = load_drawio(drawio(M))
    out = apply_edits(f, 0, [Edit("l1", (F(99), F(137)), (99, 137), ("50", "100"))], f.doc_hash)
    assert f.raw.split(b'x="50" y="100"') == out.split(b'x="99" y="137"')


def test_missing_coordinates_are_inserted():
    f = load_drawio(drawio(M))
    out = apply_edits(f, 0, [Edit("l2", (F(5), F(6)), (5, 6), (None, None))], f.doc_hash)
    cell = {c.id: c for c in load_drawio(out).pages[0].cells}["l2"]
    assert (cell.geometry["x"], cell.geometry["y"]) == ("5", "6")


def test_compressed_page_is_written_uncompressed_and_other_pages_keep_their_bytes():
    other = model([node("z", 1, 1)])
    f = load_drawio(drawio(M, other, compressed=(True, True)))
    out = apply_edits(f, 0, [Edit("l1", (F(99), F(137)), (99, 137), ("50", "100"))], f.doc_hash)
    g = load_drawio(out)
    assert not g.pages[0].compressed and g.pages[1].compressed
    s1, e1 = g.pages[1].content_span
    s0, e0 = f.pages[1].content_span
    assert out[s1:e1] == f.raw[s0:e0]
    assert {c.id: c for c in g.pages[0].cells}["l1"].geometry["x"] == "99"


def test_stale_source_is_refused():
    f = load_drawio(drawio(M))
    with pytest.raises(DrawioRefused, match="changed"):
        apply_edits(f, 0, [Edit("l1", (F(9), F(9)), (9, 9), ("50", "100"))], "0" * 64)
    with pytest.raises(DrawioRefused, match="expected"):
        apply_edits(f, 0, [Edit("l1", (F(9), F(9)), (9, 9), ("51", "100"))], f.doc_hash)


def test_edits_apply_from_the_end_backwards():
    f = load_drawio(drawio(M))
    edits = [
        Edit("l1", (F(1), F(2)), (1, 2), ("50", "100")),
        Edit("l2", (F(3), F(4)), (3, 4), (None, None)),
    ]
    cells = {c.id: c for c in load_drawio(apply_edits(f, 0, edits, f.doc_hash)).pages[0].cells}
    assert (cells["l1"].geometry["x"], cells["l2"].geometry["y"]) == ("1", "4")
