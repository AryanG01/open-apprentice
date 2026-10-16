"""Small hand-written draw.io pages for unit and round-trip tests. Real draw.io output shape: mxfile > diagram > mxGraphModel > root."""

from __future__ import annotations

from open_apprentice.drawio.parse import compress_page_xml

LABEL = "text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align={align};verticalAlign=middle;rounded=0;"
NODE = "rounded=0;whiteSpace=wrap;html=1;"


def node(cid: str, x: int, y: int, w: int = 120, h: int = 50, value: str = "Node") -> str:
    return (
        f'<mxCell id="{cid}" value="{value}" style="{NODE}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def label(
    cid: str,
    x: int | None,
    y: int | None,
    value: str = "note",
    align: str = "center",
    w: int = 80,
    style: str | None = None,
) -> str:
    xy = (f' x="{x}"' if x is not None else "") + (f' y="{y}"' if y is not None else "")
    st = style if style is not None else LABEL.format(align=align)
    return (
        f'<mxCell id="{cid}" value="{value}" style="{st}" vertex="1" parent="1">'
        f'<mxGeometry{xy} width="{w}" height="20" as="geometry"/></mxCell>'
    )


def model(cells: list[str], w: int = 600, h: int = 400, extra: str = "") -> str:
    return (
        f'<mxGraphModel grid="1" page="1" pageScale="1" pageWidth="{w}" pageHeight="{h}"{extra}><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) + "</root></mxGraphModel>"
    )


def drawio(*pages: str, compressed: tuple[bool, ...] = ()) -> bytes:
    out = []
    for i, m in enumerate(pages):
        packed = compressed[i] if i < len(compressed) else False
        body = compress_page_xml(m.encode()) if packed else m
        out.append(f'<diagram id="p{i}" name="Page-{i + 1}">{body}</diagram>')
    return ('<mxfile host="test">' + "".join(out) + "</mxfile>").encode()
