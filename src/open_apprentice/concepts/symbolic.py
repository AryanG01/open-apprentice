"""AST -> Z3 compiler for the declared symbolic subset (spec 8.9, 12.5). Trusted, tiny, and strict.

Supported: axis-aligned rectangle geometry, fixed explicit selection/order (unrolled), exact rationals,
add/sub, multiplication or division by CONSTANTS, comparisons, bounded branches, min/max.
Rejected as Unsupported (never approximated): variable*variable, variable divisors, floats, unknown ops.
This is an independent implementation from rules._Run; tests assert they agree (12.5). An agreement
result is evidence about this translation only, not about native tools or user intent.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import z3

from open_apprentice.concepts.rules import (
    CMP,
    FIELDS,
    RuleError,
    parse_rational,
    validate_rule,
)


class Unsupported(Exception):
    """Outside the symbolic subset. Callers must report status=unsupported, never 'passed'."""


def _rv(f: Fraction) -> z3.ArithRef:
    return z3.RealVal(f"{f.numerator}/{f.denominator}")


def _z(v: Any) -> Any:
    if isinstance(v, bool):
        return z3.BoolVal(v)
    if isinstance(v, Fraction):
        return _rv(v)
    return v


def _is_const(v: Any) -> bool:
    return isinstance(v, (Fraction, bool))


class SymObj:
    def __init__(self, id_: str, fields: dict[str, Any]) -> None:
        self.id, self.fields = id_, fields


def make_inputs(n: int, prefix: str = "") -> tuple[list[SymObj], dict[str, Any], list[Any]]:
    """Fresh Real variables for n objects and the canvas, plus the supporting variable list."""
    objs, vars_ = [], []
    for i in range(n):
        f = {k: z3.Real(f"{prefix}{k}{i}") for k in FIELDS}
        vars_ += list(f.values())
        objs.append(SymObj(f"obj{i}", f))
    cv = {"w": z3.Real(f"{prefix}cw"), "h": z3.Real(f"{prefix}ch")}
    vars_ += list(cv.values())
    return objs, cv, vars_


def domain_constraints(objs: list[SymObj], cv: dict, dom) -> list[Any]:
    c = [
        cv["w"] >= dom.canvas_w_min,
        cv["w"] <= dom.canvas_w_max,
        cv["h"] >= dom.canvas_h_min,
        cv["h"] <= dom.canvas_h_max,
    ]
    for o in objs:
        f = o.fields
        c += [
            f["w"] >= dom.card_min,
            f["w"] <= dom.card_max,
            f["h"] >= dom.card_min,
            f["h"] <= dom.card_max,
            f["x"] >= 0,
            f["y"] >= 0,
            f["x"] + f["w"] <= cv["w"],
            f["y"] + f["h"] <= cv["h"],
        ]
    return c


class _Sym:
    def __init__(self, objs: list[SymObj], canvas: dict) -> None:
        self.objs, self.canvas = objs, canvas
        self.locals: dict[str, Any] = {}
        # key -> {"defined": bool|BoolRef, "x","y","w","h": Fraction|ArithRef}
        self.state: dict[str, dict[str, Any]] = {
            o.id: {"defined": True, **{k: o.fields[k] for k in FIELDS}} for o in objs
        }

    # ---- expressions
    def ev(self, e: Any) -> Any:
        if isinstance(e, bool):
            return e
        if isinstance(e, int):
            return Fraction(e)
        if isinstance(e, str):
            return e
        if "rat" in e:
            return parse_rational(e["rat"])
        if "ref" in e:
            parts = e["ref"].split(".")
            head, rest = parts[0], parts[1:]
            if head == "objects":
                if not rest:
                    return list(self.objs)
                if len(rest) != 1 or not rest[0].isdigit() or int(rest[0]) >= len(self.objs):
                    raise RuleError(f"bad object ref {e['ref']!r}")
                return self.objs[int(rest[0])]
            if head == "canvas":
                return self.canvas[rest[0]]
            if len(rest) != 1 or rest[0] not in self.locals:
                raise RuleError(f"unbound local {e['ref']!r}")
            return self.locals[rest[0]]
        op, a = e["op"], e.get("args", [])
        if op == "len":
            return Fraction(len(self.ev(a[0])))
        if op == "get":
            o, f = self.ev(a[0]), a[1]
            if not isinstance(o, SymObj):
                raise RuleError("get needs an object")
            if f == "id":
                return o.id
            return o.fields[f]
        if op == "not":
            v = self.ev(a[0])
            return (not v) if isinstance(v, bool) else z3.Not(v)
        if op in ("and", "or"):
            vals = [self.ev(x) for x in a]
            if all(isinstance(v, bool) for v in vals):
                return all(vals) if op == "and" else any(vals)
            zs = [_z(v) for v in vals]
            return z3.And(*zs) if op == "and" else z3.Or(*zs)
        if op in ("min", "max"):
            vals = [self.ev(x) for x in a]
            acc = vals[0]
            for v in vals[1:]:
                if _is_const(acc) and _is_const(v):
                    acc = min(acc, v) if op == "min" else max(acc, v)
                else:
                    za, zv = _z(acc), _z(v)
                    acc = z3.If(za <= zv, za, zv) if op == "min" else z3.If(za >= zv, za, zv)
            return acc
        x, y = self.ev(a[0]), self.ev(a[1])
        if op in CMP:
            if _is_const(x) and _is_const(y):
                return {
                    "lt": x < y,
                    "le": x <= y,
                    "gt": x > y,
                    "ge": x >= y,
                    "eq": x == y,
                    "ne": x != y,
                }[op]
            zx, zy = _z(x), _z(y)
            return {
                "lt": zx < zy,
                "le": zx <= zy,
                "gt": zx > zy,
                "ge": zx >= zy,
                "eq": zx == zy,
                "ne": zx != zy,
            }[op]
        if op == "mul":
            if not (isinstance(x, Fraction) or isinstance(y, Fraction)):
                raise Unsupported("variable*variable multiplication is outside the symbolic subset")
            return x * y if _is_const(x) and _is_const(y) else _z(x) * _z(y)
        if op == "div":
            if not isinstance(y, Fraction):
                raise Unsupported("variable divisor is outside the symbolic subset")
            if y == 0:
                raise RuleError("division by zero")
            return x / y if _is_const(x) else _z(x) / _z(y)
        if op in ("add", "sub"):
            if _is_const(x) and _is_const(y):
                return x + y if op == "add" else x - y
            return _z(x) + _z(y) if op == "add" else _z(x) - _z(y)
        raise RuleError(f"unknown op {op!r}")

    # ---- statements
    def block(self, stmts: list) -> None:
        for s in stmts:
            op = s["op"]
            if op == "let":
                self.locals[s["name"]] = self.ev(s["value"])
            elif op == "for_each":
                for i, o in enumerate(list(self.objs)):
                    self.locals[s["var"]] = o
                    if "index_var" in s:
                        self.locals[s["index_var"]] = Fraction(i)
                    self.block(s["body"])
            elif op == "if":
                self._if(s)
            elif op == "emit_target":
                self._emit(s)

    def _if(self, s: dict) -> None:
        c = self.ev(s["cond"])
        if isinstance(c, bool):
            self.block(s.get("then", []) if c else s.get("else", []))
            return
        base_locals = dict(self.locals)
        base_state = {k: dict(v) for k, v in self.state.items()}
        self.block(s.get("then", []))
        t_locals, t_state = self.locals, self.state
        self.locals, self.state = dict(base_locals), {k: dict(v) for k, v in base_state.items()}
        self.block(s.get("else", []))
        e_locals, e_state = self.locals, self.state
        zc = _z(c)
        self.locals = {}
        for name in sorted(set(t_locals) & set(e_locals)):
            tv, ev_ = t_locals[name], e_locals[name]
            if tv is ev_ or (_is_const(tv) and _is_const(ev_) and tv == ev_):
                self.locals[name] = tv
            elif (
                isinstance(tv, SymObj)
                or isinstance(ev_, SymObj)
                or isinstance(tv, str)
                or isinstance(ev_, str)
            ):
                raise Unsupported("branch-dependent object/string binding")
            else:
                self.locals[name] = z3.If(zc, _z(tv), _z(ev_))
        merged: dict[str, dict[str, Any]] = {}
        for key in sorted(set(t_state) | set(e_state)):
            t = t_state.get(key) or {**e_state[key], "defined": False}
            e = e_state.get(key) or {**t_state[key], "defined": False}
            merged[key] = {}
            for prop in ("defined", *FIELDS):
                tv, ev_ = t[prop], e[prop]
                if (_is_const(tv) and _is_const(ev_) and tv == ev_) or tv is ev_:
                    merged[key][prop] = tv
                else:
                    merged[key][prop] = z3.If(zc, _z(tv), _z(ev_))
        self.state = merged

    def _emit(self, s: dict) -> None:
        kind = s["kind"]
        vals = {k: self.ev(s[k]) for k in FIELDS if k in s}
        for v in vals.values():
            if isinstance(v, (bool, str, SymObj, list)):
                raise RuleError("emit properties must be numbers")
        if kind == "clone_place":
            proto = self.ev(s["proto"])
            if not isinstance(proto, SymObj):
                raise RuleError("clone_place proto must be an object")
            cur = self.state.get(s["symbol"])
            if cur is None:
                cur = self.state[s["symbol"]] = {
                    "defined": True,
                    "x": Fraction(0),
                    "y": Fraction(0),
                    "w": proto.fields["w"],
                    "h": proto.fields["h"],
                }
            else:
                # Symbol may exist on only SOME paths. Where it did not exist yet, size comes from
                # THIS proto (creation time); where it did, the earlier size is kept.
                d = cur["defined"]
                for f in ("w", "h"):
                    if d is True:
                        continue
                    cur[f] = (
                        proto.fields[f] if d is False else z3.If(_z(d), _z(cur[f]), proto.fields[f])
                    )
                cur["defined"] = True
            cur.update(vals)
        else:
            t = self.ev(s["target"])
            if not isinstance(t, SymObj):
                raise RuleError("emit target must be a selected object")
            self.state[t.id].update(vals)


def compile_rule(body: list, objs: list[SymObj], canvas: dict) -> dict[str, dict[str, Any]]:
    """Symbolic final state: key -> {defined, x, y, w, h}. Raises Unsupported outside the subset."""
    validate_rule(body)
    c = _Sym(objs, canvas)
    c.block(body)
    return c.state


def disagreement_formula(sa: dict, sb: dict, threshold: Fraction) -> Any:
    """Some key where definedness differs, or both defined and some property differs by > threshold."""
    thr = _rv(threshold)
    clauses = []
    for key in sorted(set(sa) | set(sb)):
        a = sa.get(key) or {"defined": False, **{f: Fraction(0) for f in FIELDS}}
        b = sb.get(key) or {"defined": False, **{f: Fraction(0) for f in FIELDS}}
        da, db = _z(a["defined"]), _z(b["defined"])
        diffs = []
        for f in FIELDS:
            va, vb = _z(a[f]), _z(b[f])
            diffs += [va - vb > thr, vb - va > thr]
        clauses.append(z3.Or(da != db, z3.And(da, db, z3.Or(*diffs))))
    return z3.Or(*clauses)


PUBLIC_CONSTRAINTS = ("preserve_sizes", "stay_on_canvas", "preserve_order")


def violation_formula(state: dict, objs: list[SymObj], canvas: dict, names: tuple[str, ...]) -> Any:
    """Some explicit PUBLIC requirement is violated by the rule's output on the selected objects.

    Only public requirements are encoded; the private teacher rule is never reachable from here.
    """
    bad = []
    for name in names:
        if name == "preserve_sizes":
            bad += [
                z3.Or(_z(state[o.id]["w"]) != o.fields["w"], _z(state[o.id]["h"]) != o.fields["h"])
                for o in objs
            ]
        elif name == "stay_on_canvas":
            for o in objs:
                st_ = state[o.id]
                x, y, w, h = (_z(st_[k]) for k in FIELDS)
                bad.append(z3.Or(x < 0, y < 0, x + w > canvas["w"], y + h > canvas["h"]))
        elif name == "preserve_order":
            bad += [_z(state[b.id]["x"]) < _z(state[a.id]["x"]) for a, b in zip(objs, objs[1:])]
        else:
            raise Unsupported(f"constraint {name!r} is not encoded")
    return z3.Or(*bad) if bad else z3.BoolVal(False)
