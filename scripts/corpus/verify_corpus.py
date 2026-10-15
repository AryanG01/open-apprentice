"""Check authored .drawio files against their design (scripts/corpus/author_drawio.mjs --spec): every box and label at its
designed geometry with its text, every designed connector present with source and target, page sizes, page count, and
compression. Usage: python scripts/corpus/verify_corpus.py SPEC_JSON FILE=ID [FILE=ID ...]"""

import base64
import json
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zlib


def pages(path: str) -> tuple[list[ET.Element], list[bool]]:
    root = ET.parse(path).getroot()
    models, compressed = [], []
    for d in root.findall("diagram"):
        m = d.find("mxGraphModel")
        if m is None:  # compressed page: base64 -> raw inflate -> URL-decode
            xml = urllib.parse.unquote(
                zlib.decompress(base64.b64decode(d.text.strip()), -15).decode("utf-8")
            )
            m = ET.fromstring(xml)
            compressed.append(True)
        else:
            compressed.append(False)
        models.append(m)
    return models, compressed


def check(path: str, spec: dict) -> list[str]:
    problems = []
    models, compressed = pages(path)
    if len(models) != len(spec["pages"]):
        problems.append(f"pages: {len(models)} != {len(spec['pages'])}")
    if bool(spec.get("compressed")) != any(compressed):
        problems.append(f"compressed: file {compressed} vs design {bool(spec.get('compressed'))}")
    for m, pg in zip(models, spec["pages"]):
        if (m.get("pageWidth"), m.get("pageHeight")) != tuple(str(v) for v in spec["page"]):
            problems.append(
                f"page size {m.get('pageWidth')}x{m.get('pageHeight')} != {spec['page']}"
            )
        cells = m.find("root").findall("mxCell")
        by_value = {}
        for c in cells:
            if c.get("vertex") == "1":
                g = c.find("mxGeometry")
                by_value[c.get("value")] = (
                    c.get("id"),
                    [float(g.get(k, "0")) for k in ("x", "y", "width", "height")],
                    c.get("style", ""),
                )
        for x, y, w, h, text in pg["nodes"]:
            got = by_value.get(text)
            if not got or got[1] != [x, y, w, h]:
                problems.append(f"node {text!r}: {got and got[1]} != {[x, y, w, h]}")
        for text, x, y, w in pg["labels"]:
            got = by_value.get(text)
            if not got or got[1] != [x, y, w, 20] or not got[2].startswith("text;"):
                problems.append(f"label {text!r}: {got and got[1:]} != {[x, y, w, 20]}")
        ids = {t: by_value[t][0] for _, _, _, _, t in pg["nodes"] if t in by_value}
        edges = {(c.get("source"), c.get("target")) for c in cells if c.get("edge") == "1"}
        for a, b in pg["edges"]:
            if (ids.get(pg["nodes"][a][4]), ids.get(pg["nodes"][b][4])) not in edges:
                problems.append(f"edge {pg['nodes'][a][4]} -> {pg['nodes'][b][4]} missing")
        extra = (
            len([c for c in cells if c.get("vertex") == "1"]) - len(pg["nodes"]) - len(pg["labels"])
        )
        if extra:
            problems.append(f"{extra} unexpected vertices")
    return problems


def main() -> None:
    spec = json.load(open(sys.argv[1]))
    bad = 0
    for arg in sys.argv[2:]:
        path, i = arg.rsplit("=", 1)
        problems = check(path, spec[i])
        bad += bool(problems)
        print(f"{i} {path.split('/')[-1]}: {'OK' if not problems else problems}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
