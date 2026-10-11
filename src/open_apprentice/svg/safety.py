"""Validate an uploaded SVG BEFORE it is parsed for editing or rendered. Incompatible assets are REJECTED with a reason, never silently sanitised
(spec 6.8): the user must know what was not accepted."""

from __future__ import annotations

import re
import xml.parsers.expat as expat
from dataclasses import dataclass, field

SVG_NS = "http://www.w3.org/2000/svg"
MAX_BYTES = 200_000
MAX_ELEMENTS = 2000
MAX_DEPTH = 24

ALLOWED_TAGS = {
    "svg", "g", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text", "tspan", "title", "desc", "defs",
    "linearGradient", "radialGradient", "stop", "clipPath",
}  # fmt: skip
FORBIDDEN_REASON = {
    "script": "scripts are active content", "foreignObject": "embedded documents are not supported", "iframe": "embedded documents are not supported",
    "object": "embedded documents are not supported", "embed": "embedded documents are not supported", "image": "images may reference external resources",
    "style": "shared style rules are not editable in this lane and may import resources", "animate": "animation can change geometry at render time",
    "set": "animation can change geometry at render time", "animateTransform": "animation can change geometry at render time", "a": "links are active content",
    "use": "references between elements are not supported yet", "symbol": "references between elements are not supported yet",
    "pattern": "patterns can reference external resources", "filter": "filters are not supported", "mask": "masks are not supported", "marker": "markers are not supported",
}  # fmt: skip
_URL = re.compile(r"url\(\s*['\"]?\s*([^)'\"\s]*)", re.I)


class SvgRejected(ValueError):
    """The document was refused; the message says why, in plain language."""


@dataclass
class Checked:
    elements: int = 0
    ids: set[str] = field(default_factory=set)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def validate_svg(text: str) -> Checked:
    raw = text.encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise SvgRejected(f"document is {len(raw)} bytes; the limit is {MAX_BYTES}")
    low = text.lower()
    if "<!doctype" in low or "<!entity" in low:
        raise SvgRejected(
            "DOCTYPE and entity declarations are not accepted (entity expansion attacks)"
        )
    if "<?xml-stylesheet" in low:
        raise SvgRejected("external stylesheets are not accepted")
    out, depth, stack = Checked(), 0, []

    def start(name: str, attrs: dict) -> None:
        nonlocal depth
        depth += 1
        out.elements += 1
        t = local(name)
        if not stack and t != "svg":
            raise SvgRejected("the root element must be <svg>")
        if out.elements > MAX_ELEMENTS or depth > MAX_DEPTH:
            raise SvgRejected("document is too large or too deeply nested")
        ns = name.rsplit("}", 1)[0].lstrip("{") if "}" in name else ""
        if ns and ns != SVG_NS:
            raise SvgRejected(f"elements from the namespace {ns!r} are not accepted")
        if t in FORBIDDEN_REASON:
            raise SvgRejected(f"<{t}> is not accepted: {FORBIDDEN_REASON[t]}")
        if t not in ALLOWED_TAGS:
            raise SvgRejected(f"<{t}> is not a supported element")
        for k, v in attrs.items():
            kl = local(k).lower()
            if kl.startswith("on"):
                raise SvgRejected(f"event-handler attribute {k!r} is active content")
            if kl == "href":
                if not v.startswith("#"):
                    raise SvgRejected(
                        "external references are not accepted (href must be a local #id)"
                    )
            if "javascript:" in v.lower() or "data:" in v.lower() or "@import" in v.lower():
                raise SvgRejected(f"attribute {k!r} contains an unsupported or active value")
            for m in _URL.finditer(v):
                if not m.group(1).startswith("#"):
                    raise SvgRejected(f"attribute {k!r} references an external resource")
            if kl == "id":
                if v in out.ids:
                    raise SvgRejected(f"duplicate id {v!r}")
                out.ids.add(v)
        stack.append(t)

    def end(_name: str) -> None:
        nonlocal depth
        depth -= 1
        stack.pop()

    p = expat.ParserCreate(namespace_separator="}")
    p.StartElementHandler = start
    p.EndElementHandler = end
    try:
        p.Parse(raw, True)
    except expat.ExpatError as e:
        raise SvgRejected(
            f"not well-formed XML ({expat.ErrorString(e.code)} at line {e.lineno})"
        ) from e
    if out.elements == 0:
        raise SvgRejected("empty document")
    return out
