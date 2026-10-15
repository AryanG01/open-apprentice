"""Spike: move one label cell by (dx, dy) by editing its <mxGeometry x/y> structurally, bytes elsewhere unchanged.
Usage: python scripts/spikes/drawio_patch.py IN.drawio OUT.drawio CELL_ID DX DY"""

import sys
import xml.parsers.expat
from fractions import Fraction


def geometry_span(raw: bytes, cell_id: str) -> tuple[int, int, dict[str, str]]:
    """Byte span [start, end) of the <mxGeometry ...> start tag inside the mxCell with this id, plus its attributes."""
    stack: list[str] = []
    found: list[tuple[int, int, dict[str, str]]] = []
    p = xml.parsers.expat.ParserCreate()

    def start(name: str, attrs: dict[str, str]) -> None:
        if name == "mxGeometry" and stack and stack[-1] == cell_id and attrs.get("as") == "geometry":
            s = p.CurrentByteIndex
            e = raw.index(b">", s) + 1
            found.append((s, e, attrs))
        stack.append(attrs.get("id", "") if name == "mxCell" else (stack[-1] if stack else ""))

    p.StartElementHandler = start
    p.EndElementHandler = lambda name: stack.pop()
    p.Parse(raw, True)
    if len(found) != 1:
        raise SystemExit(f"expected one geometry for {cell_id}, found {len(found)}")
    return found[0]


def fmt(v: Fraction) -> str:
    q = round(v * 64) / Fraction(64)  # nearest 1/64; Python round() uses ties-to-even
    return str(int(q)) if q.denominator == 1 else f"{float(q):.6f}".rstrip("0").rstrip(".")


def main() -> None:
    src, dst, cell, dx, dy = sys.argv[1:6]
    raw = open(src, "rb").read()
    s, e, attrs = geometry_span(raw, cell)
    tag = raw[s:e].decode("utf-8")
    for key, delta in (("x", Fraction(dx)), ("y", Fraction(dy))):
        old = Fraction(attrs.get(key, "0"))
        new = fmt(old + delta)
        if key in attrs:
            tag = tag.replace(f' {key}="{attrs[key]}"', f' {key}="{new}"', 1)
        else:
            tag = tag.replace("<mxGeometry", f'<mxGeometry {key}="{new}"', 1)
    out = raw[:s] + tag.encode("utf-8") + raw[e:]
    assert out[:s] == raw[:s] and out[s + len(tag.encode()) :] == raw[e:]
    open(dst, "wb").write(out)


if __name__ == "__main__":
    main()
