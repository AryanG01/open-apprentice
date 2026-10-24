import base64

import pytest

from open_apprentice.campaign.imageinfo import ImageError, data_url_bytes, image_size
from tests.pngs import jpeg_url, png_bytes, png_url


def test_png_and_jpeg_sizes_come_from_their_headers():
    assert image_size(png_url(1280, 720)) == ("png", 1280, 720)
    assert image_size(jpeg_url(640, 360)) == ("jpeg", 640, 360)


@pytest.mark.parametrize(
    "url,needle",
    [
        ("https://x.example/a.png", "data URL"),
        ("data:image/svg+xml;base64,PHN2Zz4=", "PNG or JPEG"),
        ("data:image/png;base64,!!!", "base64"),
        ("data:image/png;base64," + base64.b64encode(b"GIF89a....").decode(), "PNG"),
        ("data:image/png;base64," + base64.b64encode(png_bytes(4, 4)[:20]).decode(), "truncated"),
        ("data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xd9").decode(), "JPEG"),
    ],
)
def test_anything_that_is_not_a_well_formed_png_or_jpeg_is_refused_with_a_reason(url, needle):
    with pytest.raises(ImageError, match=needle):
        image_size(url)


def test_the_label_must_match_the_bytes_and_a_zero_or_huge_size_is_refused():
    with pytest.raises(ImageError, match="does not match"):
        image_size("data:image/jpeg;base64," + base64.b64encode(png_bytes(8, 8)).decode())
    with pytest.raises(ImageError, match="size"):
        image_size(png_url(0, 5))
    with pytest.raises(ImageError, match="size"):
        image_size(png_url(100_000, 5))


def test_decoded_bytes_are_capped_before_any_parsing():
    big = "data:image/png;base64," + base64.b64encode(png_bytes(8, 8) + bytes(2_000_000)).decode()
    with pytest.raises(ImageError, match="larger than"):
        data_url_bytes(big, max_bytes=1_000_000)
