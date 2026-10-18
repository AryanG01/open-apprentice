import time
from fractions import Fraction

import pytest

from open_apprentice.api.v2.service import Conflict, _boxes
from open_apprentice.concepts.rules import RuleError, parse_rational
from open_apprentice.drawio.parse import DrawioRefused, compress_page_xml, load_drawio

MODEL = b'<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>'


def _file(pages: list[tuple[str, bytes]]) -> bytes:
    body = "".join(
        f'<diagram id="{pid}" name="p">{compress_page_xml(x)}</diagram>' for pid, x in pages
    )
    return f"<mxfile>{body}</mxfile>".encode()


def test_boxes_refuse_huge_exponents_fast():
    t = time.monotonic()
    with pytest.raises(Conflict):
        _boxes({"a": ["1e30000000", 0]})
    assert time.monotonic() - t < 1
    assert _boxes({"a": ["12.5", "-3"]}) == {"a": (Fraction(25, 2), Fraction(-3))}


def test_rational_rejects_exponents_but_keeps_fractions():
    with pytest.raises(RuleError):
        parse_rational("1e30000000")
    assert parse_rational("1/3") == Fraction(1, 3) and parse_rational("0.25") == Fraction(1, 4)


def test_rule_arithmetic_cannot_grow_numbers_without_bound():
    from open_apprentice.concepts.rules import _cap

    _cap(Fraction(2**200))
    with pytest.raises(RuleError):
        _cap(Fraction(2**400))


def test_many_pages_are_refused():
    big = b"<mxGraphModel><root>" + b"<!--" + b"a" * 3_000_000 + b"-->" + b"</root></mxGraphModel>"
    with pytest.raises(DrawioRefused):
        load_drawio(_file([(f"p{i}", big) for i in range(5)]))
    with pytest.raises(DrawioRefused):
        load_drawio(_file([(f"p{i}", MODEL) for i in range(40)]))


@pytest.mark.parametrize("pid", ["..", "a/../b", 'x"y', "a\nb"])
def test_unsafe_page_ids_are_refused(pid):
    with pytest.raises(DrawioRefused):
        load_drawio(_file([(pid.replace("\n", "&#10;").replace('"', "&quot;"), MODEL)]))


def test_duplicate_page_ids_are_refused():
    with pytest.raises(DrawioRefused):
        load_drawio(_file([("same", MODEL), ("same", MODEL)]))
