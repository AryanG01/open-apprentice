"""Learn the base story layout from one teaching pair (spec 7.4). A deterministic search candidate, plus optional model
candidates; every candidate must reproduce the teaching pair exactly through the exact rule interpreter."""

from __future__ import annotations

import copy
import json
import pathlib
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from open_apprentice.budget import Ledger
from open_apprentice.campaign.layout_rule import evaluate_layout, objects_for_rule, wrap_learned
from open_apprentice.campaign.scene import role_map
from open_apprentice.concepts.rules import RuleError, validate_rule
from open_apprentice.providers.base import CallContext, Message, Provider, StrictModel

PROMPT = pathlib.Path(__file__).resolve().parents[3] / "prompts" / "campaign_layout.md"
FACTS = {"output_format": "9:16", "overflows": False}
MAX_MODEL_CANDIDATES = 3


class CandidateOut(StrictModel):
    rule: list[Any]
    summary: str


class CandidateSet(StrictModel):
    candidates: list[CandidateOut]


@dataclass
class CandidateReport:
    origin: str
    rule: list
    reproduces: bool
    reason: str = ""


@dataclass
class Learned:
    rule: list
    origin: str
    candidates: list[CandidateReport] = field(default_factory=list)
    interpretation: str = "fixed"  # how the product image generalises: see interpretations()


class LearnError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _board(scene: dict, fmt: str | None = None) -> str:
    boards = [
        n
        for n in scene["nodes"]
        if n["type"] == "artboard" and (fmt is None or n.get("format") == fmt)
    ]
    if len(boards) != 1:
        raise LearnError(
            f"expected exactly one {fmt or ''} artboard, found {len(boards)}".replace("  ", " ")
        )
    return boards[0]["id"]


def _lit(v: Any) -> Any:
    f = Fraction(str(v))
    return int(f) if f.denominator == 1 else {"rat": f"{f.numerator}/{f.denominator}"}


def _expected(before: dict, after: dict) -> dict[str, dict]:
    """Role -> what the taught story says: box, z, font size, corner radius (per role, so it compares across ids)."""
    b_nodes = {n["id"]: n for n in before["nodes"]}
    a_nodes = {n["id"]: n for n in after["nodes"]}
    out = {}
    for o in objects_for_rule(after, _board(after, "9:16")):
        n = a_nodes[o["id"]]
        src = b_nodes.get(o["id"], {})
        out[o["role"]] = {
            "box": (o["x"], o["y"], o["w"], o["h"]),
            "z": n.get("z"),
            "image": n["type"] == "image",
            "fontSize": Fraction(str(n["fontSize"])) if "fontSize" in n else None,
            "fontSize_changed": "fontSize" in n and n["fontSize"] != src.get("fontSize"),
            "cornerRadius": Fraction(str(n["cornerRadius"])) if n["type"] == "shape" else None,
            "cornerRadius_changed": n["type"] == "shape"
            and n.get("cornerRadius") != src.get("cornerRadius"),
        }
    return out


def _scaled(me: dict, field_: str, k: Fraction) -> dict:
    return {"op": "mul", "args": [{"op": "get", "args": [me, field_]}, _lit(k)]}


def _search_rule(
    expected: dict[str, dict], product_src: tuple[Fraction, Fraction] | None = None
) -> list:
    """Constant boxes per role. With `product_src` (the taught banner's product width and height), the product image is
    instead scaled by the taught factor around the taught centre: the "relative" reading of the same example.
    """
    me = {"ref": "locals.o"}
    branches = []
    for role, e in expected.items():
        x, y, w, h = (_lit(v) for v in e["box"])
        if product_src is not None and role == "product_image":
            bx, by, bw, bh = e["box"]
            kw, kh = bw / product_src[0], bh / product_src[1]
            w, h = _scaled(me, "w", kw), _scaled(me, "h", kh)
            x = {"op": "sub", "args": [_lit(bx + bw / 2), _scaled(me, "w", kw / 2)]}
            y = {"op": "sub", "args": [_lit(by + bh / 2), _scaled(me, "h", kh / 2)]}
        emits = [
            {
                "op": "emit_target",
                "kind": "fit_image" if e["image"] else "place",
                "target": me,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
        ]
        if e["z"] is not None and not e["image"]:
            emits[0]["z"] = e["z"]
        if e["fontSize_changed"]:
            emits.append(
                {
                    "op": "emit_target",
                    "kind": "style",
                    "target": me,
                    "fontSize": _lit(e["fontSize"]),
                }
            )
        if e["cornerRadius_changed"]:
            emits.append(
                {
                    "op": "emit_target",
                    "kind": "style",
                    "target": me,
                    "cornerRadius": _lit(e["cornerRadius"]),
                }
            )
        cond = {"op": "eq", "args": [{"op": "get", "args": [me, "role"]}, role]}
        branches.append({"op": "if", "cond": cond, "then": emits})
    return [{"op": "for_each", "over": {"ref": "objects"}, "var": "o", "body": branches}]


def _asks(stmts: list) -> bool:
    return any(
        isinstance(s, dict)
        and (s.get("op") == "ask" or any(_asks(s.get(k) or []) for k in ("then", "else", "body")))
        for s in stmts
    )


def _check(rule: list, before: dict, expected: dict[str, dict]) -> tuple[bool, str]:
    if not isinstance(rule, list) or _asks(rule):
        return (
            False,
            "invalid rule: overflow questions are built in and cannot be part of a learned layout",
        )
    try:
        validate_rule(wrap_learned(rule), campaign=True)
        objs = objects_for_rule(before, _board(before))
        out = evaluate_layout(wrap_learned(rule), objs, FACTS)
    except (RuleError, LearnError) as e:
        return False, f"invalid rule: {e}"
    roles = {o["id"]: o["role"] for o in objs}
    src_font = {
        o["id"]: n.get("fontSize") for o in objs for n in before["nodes"] if n["id"] == o["id"]
    }
    got = {roles[t.node_id]: t for t in out.targets.values() if t.node_id in roles}
    for role, e in expected.items():
        t = got.get(role)
        if t is None or (t.x, t.y, t.w, t.h) != e["box"]:
            return False, f"{role}: box differs from the taught story"
        if not e["image"] and t.z != e["z"]:
            return False, f"{role}: stacking differs from the taught story"
        if e["fontSize"] is not None:
            size = t.font_size if t.font_size is not None else Fraction(str(src_font[t.node_id]))
            if size != e["fontSize"]:
                return False, f"{role}: font size differs from the taught story"
        if e["cornerRadius_changed"] and t.corner_radius != e["cornerRadius"]:
            return False, f"{role}: corner radius differs from the taught story"
    return True, ""


async def _model_candidates(
    provider: Provider, ledger: Ledger, expected: dict[str, dict]
) -> list[CandidateOut]:
    payload = {
        role: {k: (str(v) if isinstance(v, Fraction) else v) for k, v in e.items() if k != "box"}
        | {"box_after": [str(v) for v in e["box"]]}
        for role, e in expected.items()
    }
    comp = await provider.complete_json(
        messages=[Message("system", PROMPT.read_text()), Message("user", json.dumps(payload))],
        output_schema=CandidateSet,
        ctx=CallContext(role="campaign_layout", category="inference"),
        ledger=ledger,
        max_tokens=4000,
    )
    return comp.parsed.candidates[:MAX_MODEL_CANDIDATES]


READINGS = ("fixed", "relative")


def interpretations(before: dict, after: dict) -> dict[str, list]:
    """The two readings of one teaching pair for the product image: the same frame every time ("fixed"), or scaled by the
    factor the example used ("relative"). Both reproduce the pair exactly; they differ only on a banner whose product
    image is a different size, which is why the owner is asked (see probe_banner)."""
    role_map(before, _board(before))
    role_map(after, _board(after, "9:16"))
    expected = _expected(before, after)
    src = next(o for o in objects_for_rule(before, _board(before)) if o["role"] == "product_image")
    out = {
        "fixed": _search_rule(expected),
        "relative": _search_rule(expected, (src["w"], src["h"])),
    }
    for name, rule in out.items():
        ok, why = _check(rule, before, expected)
        if not ok:
            raise LearnError(f"the {name} reading does not reproduce the taught story: {why}")
    return out


PROBE_SCALE = Fraction(3, 5)


def probe_banner(before: dict) -> dict:
    """The teaching banner with its product image at 3/5 size around the same centre: an input on which the two readings
    disagree, so both can be shown to the owner. The teaching banner itself is not changed."""
    probe = copy.deepcopy(before)
    n = next(n for n in probe["nodes"] if n.get("role") == "product_image")
    w, h = Fraction(str(n["width"])), Fraction(str(n["height"]))
    nw, nh = w * PROBE_SCALE, h * PROBE_SCALE
    n["x"] = float(Fraction(str(n["x"])) + (w - nw) / 2)
    n["y"] = float(Fraction(str(n["y"])) + (h - nh) / 2)
    n["width"], n["height"] = float(nw), float(nh)
    return probe


async def learn_layout(
    before: dict,
    after: dict,
    *,
    provider: Provider | None = None,
    ledger: Ledger | None = None,
    interpretation: str = "fixed",
) -> Learned:
    if interpretation not in READINGS:
        raise LearnError(f"unknown reading {interpretation!r}")
    role_map(before, _board(before))  # a missing or doubled role stops here, before any model call
    role_map(after, _board(after, "9:16"))
    expected = _expected(before, after)
    search = interpretations(before, after)[interpretation]
    ok, why = _check(search, before, expected)
    reports = [CandidateReport("search", search, ok, why)]
    if provider is not None:
        for c in await _model_candidates(provider, ledger, expected):
            ok_m, why_m = _check(c.rule, before, expected)
            reports.append(CandidateReport("model", c.rule, ok_m, why_m))
    chosen = next((r for r in reports if r.reproduces), None)
    if chosen is None:
        raise LearnError(
            "no candidate reproduces the taught story: " + "; ".join(r.reason for r in reports)
        )
    return Learned(chosen.rule, chosen.origin, reports, interpretation)


def _value(v: Any) -> Fraction:
    return Fraction(v["rat"]) if isinstance(v, dict) else Fraction(v)


def _fmt(f: Fraction) -> str:
    return str(int(f)) if f.denominator == 1 else f"{float(f):.4g}"


def describe(rule: list) -> list[dict]:
    """A learned layout as rows a person can read: per role, where it goes, how big, stacking, and any restyle. Covers
    the shape _search_rule writes; anything else is summarised as "computed"."""
    rows = []
    for branch in rule[0].get("body", []) if rule and isinstance(rule[0], dict) else []:
        try:
            role = branch["cond"]["args"][1]
        except (KeyError, IndexError, TypeError):
            continue
        row = {"role": role, "position": "computed", "size": "computed", "z": None, "style": []}
        for e in branch.get("then", []):
            if e.get("kind") in ("place", "fit_image"):
                if isinstance(e["w"], dict) and "op" in e["w"]:
                    k = _value(e["w"]["args"][1])
                    cx, cy = _value(e["x"]["args"][0]), _value(e["y"]["args"][0])
                    row["size"] = f"scaled ×{float(k):.3g} from the banner's own"
                    row["position"] = f"centred on {_fmt(cx)}, {_fmt(cy)}"
                else:
                    x, y, w, h = (_value(e[k]) for k in ("x", "y", "w", "h"))
                    row["position"], row["size"] = f"{_fmt(x)}, {_fmt(y)}", f"{_fmt(w)} × {_fmt(h)}"
                if e["kind"] == "fit_image":
                    row["style"].append("image fitted inside, never cropped")
                row["z"] = e.get("z")
            elif e.get("kind") == "style":
                if "fontSize" in e:
                    row["style"].append(f"font {_fmt(_value(e['fontSize']))} px")
                if "cornerRadius" in e:
                    row["style"].append(f"corner radius {_fmt(_value(e['cornerRadius']))} px")
        rows.append(row)
    return rows
