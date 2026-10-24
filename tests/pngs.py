"""Real (tiny) PNG and JPEG-header bytes for tests, standard library only."""

import base64
import struct
import zlib


def png_bytes(w: int, h: int, rgb=(200, 80, 40)) -> bytes:
    def chunk(tag: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(tag + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", crc)

    row = b"\x00" + bytes(rgb) * w
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * h))
        + chunk(b"IEND", b"")
    )


def png_url(w: int, h: int, rgb=(200, 80, 40)) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes(w, h, rgb)).decode()


def jpeg_header_bytes(w: int, h: int) -> bytes:
    """SOI + a baseline SOF0 segment: enough for a header parser (not decodable)."""
    sof = b"\x08" + struct.pack(">HH", h, w) + b"\x03" + b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    return (
        b"\xff\xd8"
        + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + b"\xff\xc0"
        + struct.pack(">H", len(sof) + 2)
        + sof
        + b"\xff\xd9"
    )


def jpeg_url(w: int, h: int) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_header_bytes(w, h)).decode()
