"""Header-only checks of an uploaded image (standard library, nothing is decoded): what it claims, what its bytes say, how big
it is. A banner can arrive as PNG or JPEG; only headers are read, so a decompression bomb never reaches an image decoder here."""

from __future__ import annotations

import base64
import binascii
import struct

PNG_SIG = b"\x89PNG\r\n\x1a\n"
MAX_DIM = 8192
_LABEL = {"image/png": "PNG", "image/jpeg": "JPEG"}
_SOF = {m for m in range(0xC0, 0xD0) if m not in (0xC4, 0xC8, 0xCC)}


class ImageError(ValueError):
    """A plain-language reason the image is refused."""


def data_url_bytes(
    url: str, *, max_bytes: int = 2_000_000, mimes: tuple[str, ...] = ("image/png", "image/jpeg")
) -> tuple[str, bytes]:
    if not isinstance(url, str) or not url.startswith("data:") or ";base64," not in url[:64]:
        raise ImageError("expected a base64 data URL")
    head, _, body = url.partition(";base64,")
    mime = head[5:].lower()
    if mime not in mimes:
        raise ImageError("only PNG or JPEG images are accepted")
    if len(body) > (max_bytes * 4) // 3 + 8:  # refuse before decoding
        raise ImageError(f"the image is larger than {max_bytes // 1000} KB")
    try:
        data = base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ImageError("the image is not valid base64") from e
    if len(data) > max_bytes:
        raise ImageError(f"the image is larger than {max_bytes // 1000} KB")
    return mime, data


def _png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 24:
        raise ImageError("the PNG is truncated")
    if data[12:16] != b"IHDR":
        raise ImageError("the PNG has no header block")
    return struct.unpack(">II", data[16:24])


def _jpeg_size(data: bytes) -> tuple[int, int]:
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
            i += 1 if marker == 0xFF else 2
            continue
        if marker == 0xD9:
            break
        (seg,) = struct.unpack(">H", data[i + 2 : i + 4])
        if marker in _SOF:
            if i + 9 > len(data):
                break
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        i += 2 + seg
    raise ImageError("no JPEG size found in the file")


def image_size(url: str, *, max_bytes: int = 2_000_000) -> tuple[str, int, int]:
    """("png"|"jpeg", width, height) from the header, after checking the label against the bytes."""
    mime, data = data_url_bytes(url, max_bytes=max_bytes)
    kind = "png" if data.startswith(PNG_SIG) else "jpeg" if data.startswith(b"\xff\xd8") else None
    if kind is None:
        raise ImageError(f"the bytes are not a {_LABEL[mime]}")
    if f"image/{kind}" != mime:
        raise ImageError("the image type does not match its contents")
    w, h = _png_size(data) if kind == "png" else _jpeg_size(data)
    if not (1 <= w <= MAX_DIM and 1 <= h <= MAX_DIM):
        raise ImageError(f"image size {w}x{h} is outside 1..{MAX_DIM} pixels")
    return kind, w, h
