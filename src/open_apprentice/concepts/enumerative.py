"""Bounded enumerative symbolic reference learner (spec 21.11 'Non-LLM reference').

No model. It enumerates rules from a DECLARED small grammar, keeps those that fit EVERY teaching
constraint, collapses behaviourally identical candidates (simplest wins), and hands the survivors to the
same TeachingSession machinery (same questions, same Neither handling, same ledger checks).

Declared grammar (constants pool is generic - nothing is derived from any private teacher rule):
  badge family : corner in {top-left, top-right, bottom-left, bottom-right} x margin expression of card width w
      round 1: c | w*r | min(w*r,c) | max(w*r,c) | min(c2, max(c1, w*r))
      round 2: round 1 plus the affine form w*r + c   (a deeper grammar, tried only after 'Neither')
  gap family   : equal EDGE gap g | equal CENTER pitch p, with g/p/left/top read from the demonstration geometry
A target outside this grammar is reported as not expressible (coverage), never faked.
"""

from __future__ import annotations

import asyncio

import time
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import product
from typing import Any, Iterator, Optional

from open_apprentice.concepts.hypotheses import Candidate, Constraint, GenerationReport, fits
from open_apprentice.concepts.query_selection import sample_scenes
from open_apprentice.concepts.rules import RuleError, evaluate_rule, validate_rule
from open_apprentice.concepts.schemas import sha
from open_apprentice.concepts.domain import DomainManifest

POOL = tuple(Fraction(c) for c in (0, 1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64))
SIGNED_POOL = tuple(sorted({*POOL, *(-c for c in POOL)}))
RATIOS = tuple(Fraction(k, 100) for k in (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25))
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
SEARCH_LIMIT = 200_000
BEHAVIOUR_PROBE_SEEDS = 12


def _lit(f: Fraction) -> Any:
    return int(f) if f.denominator == 1 else {"rat": f"{f.numerator}/{f.denominator}"}


def _op(name: str, *args: Any) -> dict:
    return {"op": name, "args": list(args)}


W = _op("get", {"ref": "objects.0"}, "w")


def _margin_exprs(rnd: int) -> Iterator[tuple[int, str, Any]]:
    for c in POOL:
        yield 1, f"{c}", _lit(c)
    for r in RATIOS:
        yield 2, f"{r}*w", _op("mul", W, _lit(r))
    for r in RATIOS:
        for c in POOL:
            yield 3, f"min({r}*w,{c})", _op("min", _op("mul", W, _lit(r)), _lit(c))
            yield 3, f"max({r}*w,{c})", _op("max", _op("mul", W, _lit(r)), _lit(c))
    for r in RATIOS:
        for lo, hi in product(POOL, POOL):
            if lo < hi:
                yield 4, f"clamp({r}*w,{lo},{hi})", _op(
                    "min", _lit(hi), _op("max", _lit(lo), _op("mul", W, _lit(r)))
                )
    if rnd >= 2:
        for r in RATIOS:
            for c in SIGNED_POOL:
                if c:
                    yield 3, f"{r}*w{c:+}", _op("add", _op("mul", W, _lit(r)), _lit(c))


def _badge_rule(corner: str, margin: Any) -> list:
    card, proto = {"ref": "objects.0"}, {"ref": "objects.1"}
    gx, gy = lambda o, f: _op("get", o, f), lambda o, f: _op("get", o, f)
    m = {"ref": "locals.m"}
    right = corner.endswith("right")
    bottom = corner.startswith("bottom")
    x = (
        _op("sub", _op("add", gx(card, "x"), gx(card, "w")), _op("add", m, gx(proto, "w")))
        if right
        else _op("add", gx(card, "x"), m)
    )
    y = (
        _op("sub", _op("add", gy(card, "y"), gy(card, "h")), _op("add", m, gy(proto, "h")))
        if bottom
        else _op("add", gy(card, "y"), m)
    )
    return [
        {"op": "let", "name": "m", "value": margin},
        {
            "op": "emit_target",
            "kind": "clone_place",
            "proto": proto,
            "symbol": "badge",
            "x": x,
            "y": y,
        },
    ]


def _gap_rules(demo: Constraint) -> list[tuple[int, str, list]]:
    exp, objs = demo.expected, demo.scene["objects"]
    ids = [o["id"] for o in objs]
    if len(ids) < 2 or any(i not in exp for i in ids):
        return []
    left, top = exp[ids[0]]["x"], exp[ids[0]]["y"]
    if any(exp[i]["y"] != top for i in ids):
        return []  # not a top-aligned row: outside this grammar
    gaps = {exp[b]["x"] - (exp[a]["x"] + exp[a]["w"]) for a, b in zip(ids, ids[1:])}
    centers = {
        (exp[b]["x"] + exp[b]["w"] / 2) - (exp[a]["x"] + exp[a]["w"] / 2)
        for a, b in zip(ids, ids[1:])
    }
    out = []
    R = lambda p: {"ref": p}
    O = lambda *a: _op(*a)
    if len(gaps) == 1:
        g = next(iter(gaps))
        out.append(
            (
                1,
                f"equal edge gap {g}",
                [
                    {"op": "let", "name": "cursor", "value": _lit(left)},
                    {
                        "op": "for_each",
                        "var": "o",
                        "over": R("objects"),
                        "body": [
                            {
                                "op": "emit_target",
                                "kind": "move_existing",
                                "target": R("locals.o"),
                                "x": R("locals.cursor"),
                                "y": _lit(top),
                            },
                            {
                                "op": "let",
                                "name": "cursor",
                                "value": O(
                                    "add",
                                    R("locals.cursor"),
                                    O("add", O("get", R("locals.o"), "w"), _lit(g)),
                                ),
                            },
                        ],
                    },
                ],
            )
        )
    if len(centers) == 1:
        p = next(iter(centers))
        out.append(
            (
                1,
                f"equal center pitch {p}",
                [
                    {
                        "op": "let",
                        "name": "c",
                        "value": O("add", _lit(left), O("div", O("get", R("objects.0"), "w"), 2)),
                    },
                    {
                        "op": "for_each",
                        "var": "o",
                        "over": R("objects"),
                        "body": [
                            {
                                "op": "emit_target",
                                "kind": "move_existing",
                                "target": R("locals.o"),
                                "x": O(
                                    "sub", R("locals.c"), O("div", O("get", R("locals.o"), "w"), 2)
                                ),
                                "y": _lit(top),
                            },
                            {"op": "let", "name": "c", "value": O("add", R("locals.c"), _lit(p))},
                        ],
                    },
                ],
            )
        )
    return out


@dataclass
class EnumerativeSource:
    dom: DomainManifest
    object_counts: list[int]
    max_candidates: int = 4
    stats: list[dict] = field(default_factory=list)

    def _behaviour_key(self, rule: list) -> Optional[str]:
        sig = []
        for sc in sample_scenes(self.dom, self.object_counts, BEHAVIOUR_PROBE_SEEDS, seed=7):
            try:
                out = evaluate_rule(rule, sc["objects"], sc["canvas"])
            except RuleError:
                return None
            sig.append({k: {f: str(v) for f, v in p.items()} for k, p in sorted(out.items())})
        return sha(sig)

    async def __call__(
        self, constraints: list[Constraint], rnd: int, rejected: list[str]
    ) -> GenerationReport:
        # CPU-heavy enumeration runs in a worker thread so it never stalls the server for other visitors.
        return await asyncio.to_thread(self._enumerate, constraints, rnd, rejected)

    def _enumerate(
        self, constraints: list[Constraint], rnd: int, rejected: list[str]
    ) -> GenerationReport:
        t0, evaluated = time.process_time(), 0
        rep = GenerationReport(rnd)
        demo = next(c for c in constraints if c.source == "demonstration")
        creates = any(k not in {o["id"] for o in demo.scene["objects"]} for k in demo.expected)
        pool: list[tuple[int, str, list]] = []
        if creates:
            for (size, label, expr), corner in product(_margin_exprs(rnd), CORNERS):
                pool.append((size, f"{corner} inset {label}", _badge_rule(corner, expr)))
        else:
            pool = _gap_rules(demo)
        pool.sort(key=lambda t: (t[0], t[1]))
        seen_behaviour: set[str] = set()
        exhausted = False
        for size, label, rule in pool:
            evaluated += 1
            if evaluated > SEARCH_LIMIT:
                exhausted = True
                break
            if not all(fits(rule, c)[0] for c in constraints):
                continue
            key = self._behaviour_key(rule)
            if key is None or key in seen_behaviour:
                continue
            seen_behaviour.add(key)
            validate_rule(rule)
            rep.accepted.append(Candidate(label, rule, sha(rule), "supported"))
            if len(rep.accepted) >= self.max_candidates:
                break
        rep.usage = {
            "label": "ENUMERATIVE",
            "grammar_round": rnd,
            "enumerated": evaluated,
            "search_limit": SEARCH_LIMIT,
            "limit_hit": exhausted,
            "cpu_seconds": round(time.process_time() - t0, 4),
            "expressible": bool(rep.accepted),
            "pool_size": len(pool),
        }
        self.stats.append(rep.usage)
        if not rep.accepted:
            rep.rejected.append(
                {
                    "summary": "(enumeration)",
                    "reason": "no rule in the declared grammar fits all teaching evidence",
                }
            )
        return rep
