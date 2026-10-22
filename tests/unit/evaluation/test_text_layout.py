import pytest

from open_apprentice.evaluation import text_layout
from open_apprentice.evaluation.text_layout import advance_width, fit, wrap


def test_short_headline_is_one_line():
    assert wrap("Silence the city.", 936, 72, True) == ["Silence the city."]


def test_wrap_breaks_at_spaces_and_keeps_every_word():
    lines = wrap("Hear only what matters.", 300, 72, True)
    assert len(lines) >= 3
    assert " ".join(lines) == "Hear only what matters."


def test_over_wide_compound_is_flagged():
    assert fit("Geräuschunterdrückungstechnologie", 300, 72, True, 1.1).word_too_wide


def test_height_is_lines_times_line_height():
    f = fit("Hear only what matters.", 300, 72, True, 1.1)
    assert f.height == pytest.approx(len(f.lines) * 72 * 1.1)


def test_bold_is_wider_than_regular():
    assert advance_width("Silence", 72, True) > advance_width("Silence", 72, False)


def test_tampered_font_hash_is_refused():
    with pytest.raises(ValueError, match="hash"):
        text_layout._load_font("LiberationSans-Regular.ttf", "0" * 64)
