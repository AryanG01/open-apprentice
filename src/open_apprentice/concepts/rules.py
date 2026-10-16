"""Pure rule language (spec 7.4) and its CONCRETE evaluator.

A rule maps public world geometry of an ordered selection to desired targets. It has no tools, no I/O,
no environment access; its only output primitive is `emit_target`, a pure collector (nothing mutates).

Inputs : objects = ordered list of {id,x,y,w,h}; canvas = {w,h}.
Numbers: exact rationals (Fraction). Floats are rejected so concrete and symbolic semantics coincide.
Output : {key: {x,y,w,h}} for every selected object (unemitted properties keep their input value) plus
         every emitted clone_place symbol (clone keeps its prototype size unless w/h are given).

Statements: let | if | for_each(over objects) | emit_target.
Expressions: int literal | {"rat":"a/b"} | {"ref":...} | {"op":..., "args":[...]}.
Ops: add sub mul div min max lt le gt ge eq ne and or not get len by_id.
Objects may also carry `kind`, `role` and `attached` (id of the confirmed anchor); `get` reads them as strings,
eq/ne compare two strings, `by_id` looks an object up by its id (so a label can read its anchor). The symbolic compiler
reports all of these as Unsupported.
The concrete evaluator accepts variable*variable (`mul`); the SYMBOLIC compiler rejects it as unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

MAX_STATEMENTS = 64
MAX_DEPTH = 8  # was 4: a nested for_each (obstacle scan) inside for_each > if needs 5
MAX_STEPS = (
    300_000  # statements executed per run: nested loops over 20+ objects otherwise never finish
)
MAX_OBJECTS = 32  # was 8: label-placement documents hold up to 16 movable labels + their nodes
MAX_EXPR_NODES = 500
FIELDS = ("x", "y", "w", "h")
BIN_ARITH = {"add", "sub", "mul", "div", "min", "max"}
CMP = {"lt", "le", "gt", "ge", "eq", "ne"}
BOOL = {"and", "or", "not"}
EMIT_KINDS = {
    "move_existing": ({"x", "y"}, {"x", "y"}),
    "resize_existing": ({"w", "h"}, {"w", "h"}),
    "clone_place": ({"x", "y"}, {"x", "y", "w", "h"}),  # (required, allowed)
}
_FORBIDDEN = {"__proto__", "constructor", "prototype"}


class RuleError(Exception):
    """Malformed or unsupported rule/program. Never silently repaired."""


def parse_rational(s: str) -> Fraction:
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError) as e:
        raise RuleError(f"bad rational {s!r}") from e


def validate_rule(body: list) -> None:
    """Static validation shared (syntax only) by the concrete and symbolic evaluators."""
    nodes = 0

    def expr(e: Any, depth: int = 0) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_EXPR_NODES:
            raise RuleError("rule too large")
        if isinstance(e, bool):
            return
        if isinstance(e, int):
            return
        if isinstance(e, float):
            raise RuleError("floats are not allowed; use ints or {'rat': 'a/b'}")
        if isinstance(e, str):
            return  # string literal (ids / field names)
        if not isinstance(e, dict) or _FORBIDDEN & e.keys():
            raise RuleError("bad expression")
        if "rat" in e:
            parse_rational(e["rat"])
        elif "ref" in e:
            ref = e["ref"]
            if not isinstance(ref, str) or _FORBIDDEN & set(ref.split(".")):
                raise RuleError(f"bad ref {ref!r}")
            head = ref.split(".")[0]
            if head not in ("objects", "canvas", "locals"):
                raise RuleError(f"bad ref root {head!r}")
        elif "op" in e:
            op, args = e["op"], e.get("args", [])
            if op not in BIN_ARITH | CMP | BOOL | {"get", "len", "by_id"}:
                raise RuleError(f"unknown op {op!r}")
            fixed = {"not": 1, "len": 1, "get": 2, "by_id": 1}
            fixed.update({o: 2 for o in (BIN_ARITH - {"min", "max"}) | CMP})
            if op in fixed and len(args) != fixed[op]:
                raise RuleError(f"{op}: wrong arity")
            if op in ("min", "max", "and", "or") and not args:
                raise RuleError(f"{op}: needs arguments")
            for a in args:
                expr(a, depth + 1)
        else:
            raise RuleError("expression must have rat/ref/op")

    def block(stmts: Any, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise RuleError("nesting too deep")
        if not isinstance(stmts, list):
            raise RuleError("block must be a list")
        for s in stmts:
            if not isinstance(s, dict) or _FORBIDDEN & s.keys():
                raise RuleError("bad statement")
            op = s.get("op")
            if op == "let":
                if not isinstance(s.get("name"), str):
                    raise RuleError("let needs a name")
                expr(s.get("value"))
            elif op == "if":
                expr(s.get("cond"))
                block(s.get("then", []), depth + 1)
                block(s.get("else", []), depth + 1)
            elif op == "for_each":
                if (
                    s.get("over") != {"ref": "objects"}
                    or not isinstance(s.get("var"), str)
                    or not isinstance(s.get("index_var", ""), str)
                ):
                    raise RuleError("for_each iterates over {'ref':'objects'} with a var name")
                block(s.get("body"), depth + 1)
            elif op == "emit_target":
                kind = s.get("kind")
                if kind not in EMIT_KINDS:
                    raise RuleError(f"unknown emit kind {kind!r}")
                required, allowed = EMIT_KINDS[kind]
                present = {k for k in FIELDS if k in s}
                if not required <= present or not present <= allowed:
                    raise RuleError(
                        f"{kind}: properties must include {sorted(required)} within {sorted(allowed)}"
                    )
                head = "proto" if kind == "clone_place" else "target"
                if head not in s:
                    raise RuleError(
                        f"{kind} needs a '{head}' key"
                        + (" (not 'target')" if kind == "clone_place" else "")
                    )
                expr(s[head])
                if kind == "clone_place" and not isinstance(s.get("symbol"), str):
                    raise RuleError("clone_place needs a symbol")
                for k in present:
                    expr(s[k])
            else:
                raise RuleError(f"unknown statement {op!r}")

    def count_stmts(stmts: list) -> int:
        n = 0
        for s in stmts:
            n += 1
            if isinstance(s, dict):
                n += sum(count_stmts(s.get(k, []) or []) for k in ("then", "else", "body"))
        return n

    block(body, 1)
    if count_stmts(body) > MAX_STATEMENTS:
        raise RuleError("too many statements")


@dataclass(frozen=True)
class Obj:
    id: str
    x: Fraction
    y: Fraction
    w: Fraction
    h: Fraction
    kind: str = ""
    role: str = ""
    attached: str = ""

    def get(self, f: str) -> Any:
        if f in ("id", "kind", "role", "attached"):
            return getattr(self, f)
        if f in FIELDS:
            return getattr(self, f)
        raise RuleError(f"no field {f!r}")


def to_obj(d: dict) -> Obj:
    return Obj(
        d["id"],
        *(Fraction(d[k]) for k in FIELDS),
        kind=d.get("kind", ""),
        role=d.get("role", ""),
        attached=d.get("attached", ""),
    )


def _num(v: Any) -> Fraction:
    if isinstance(v, bool) or not isinstance(v, Fraction):
        raise RuleError(f"number expected, got {type(v).__name__}")
    return v


def _bool(v: Any) -> bool:
    if not isinstance(v, bool):
        raise RuleError("boolean expected")
    return v


class _Run:
    def __init__(self, objects: list[Obj], canvas: dict) -> None:
        self.objects = objects
        self.canvas = {"w": Fraction(canvas["w"]), "h": Fraction(canvas["h"])}
        self.locals: dict[str, Any] = {}
        self.steps = 0
        self.state: dict[str, dict[str, Fraction]] = {
            o.id: {f: getattr(o, f) for f in FIELDS} for o in objects
        }

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
                    return list(self.objects)
                if len(rest) != 1 or not rest[0].isdigit() or int(rest[0]) >= len(self.objects):
                    raise RuleError(f"bad object ref {e['ref']!r}")
                return self.objects[int(rest[0])]
            if head == "canvas":
                if len(rest) != 1 or rest[0] not in self.canvas:
                    raise RuleError(f"bad canvas ref {e['ref']!r}")
                return self.canvas[rest[0]]
            if head != "locals" or len(rest) != 1 or rest[0] not in self.locals:
                raise RuleError(f"unbound local {e['ref']!r}")
            return self.locals[rest[0]]
        op, a = e["op"], e.get("args", [])
        if op in ("min", "max"):
            vals = [_num(self.ev(x)) for x in a]
            if not vals:
                raise RuleError(f"{op} of nothing")
            return min(vals) if op == "min" else max(vals)
        if op == "len":
            v = self.ev(a[0])
            if not isinstance(v, list):
                raise RuleError("len needs the objects list")
            return Fraction(len(v))
        if op == "by_id":
            ident = self.ev(a[0])
            for o in self.objects:
                if o.id == ident:
                    return o
            raise RuleError(f"no object with id {ident!r}")
        if op == "get":
            o, f = self.ev(a[0]), a[1]
            if not isinstance(o, Obj) or not isinstance(f, str):
                raise RuleError("get needs (object, field-name)")
            return o.get(f)
        if op == "not":
            return not _bool(self.ev(a[0]))
        if op in ("and", "or"):
            vals = [_bool(self.ev(x)) for x in a]
            return all(vals) if op == "and" else any(vals)
        x, y = self.ev(a[0]), self.ev(a[1])
        if op in CMP:
            if op in ("eq", "ne") and isinstance(x, str) and isinstance(y, str):
                return (x == y) if op == "eq" else (x != y)
            if op in ("eq", "ne") and not (isinstance(x, Fraction) and isinstance(y, Fraction)):
                raise RuleError("eq/ne compare two numbers or two strings")
            x, y = _num(x), _num(y)
            return {
                "lt": x < y,
                "le": x <= y,
                "gt": x > y,
                "ge": x >= y,
                "eq": x == y,
                "ne": x != y,
            }[op]
        x, y = _num(x), _num(y)
        if op == "add":
            return x + y
        if op == "sub":
            return x - y
        if op == "mul":
            return x * y
        if op == "div":
            if y == 0:
                raise RuleError("division by zero")
            return x / y
        raise RuleError(f"unknown op {op!r}")

    def block(self, stmts: list) -> None:
        for s in stmts:
            self.steps += 1
            if self.steps > MAX_STEPS:
                raise RuleError("rule takes too many steps (nested loops over too many objects)")
            op = s["op"]
            if op == "let":
                self.locals[s["name"]] = self.ev(s["value"])
            elif op == "if":
                self.block(s.get("then", []) if _bool(self.ev(s["cond"])) else s.get("else", []))
            elif op == "for_each":
                for o in list(self.objects):
                    self.locals[s["var"]] = o
                    if "index_var" in s:
                        self.locals[s["index_var"]] = Fraction(self.objects.index(o))
                    self.block(s["body"])
            elif op == "emit_target":
                self.emit(s)

    def emit(self, s: dict) -> None:
        kind = s["kind"]
        vals = {k: _num(self.ev(s[k])) for k in FIELDS if k in s}
        if kind == "clone_place":
            proto = self.ev(s["proto"])
            if not isinstance(proto, Obj):
                raise RuleError("clone_place proto must be an object")
            cur = self.state.setdefault(s["symbol"], {"w": proto.w, "h": proto.h})
            cur.update(vals)
        else:
            t = self.ev(s["target"])
            if not isinstance(t, Obj) or t.id not in self.state:
                raise RuleError("emit target must be a selected object")
            self.state[t.id].update(vals)


def evaluate_rule_counted(
    body: list, objects: list[dict], canvas: dict
) -> tuple[dict[str, dict[str, Fraction]], int]:
    """Run a rule and report how many statements it executed (the probe search's evaluation budget). A RuleError raised
    while running carries `.steps`, the statements executed before the failure."""
    validate_rule(body)
    if not 1 <= len(objects) <= MAX_OBJECTS:
        raise RuleError("object count out of range")
    run = _Run([to_obj(o) for o in objects], canvas)
    try:
        run.block(body)
    except RuleError as e:
        e.steps = run.steps  # type: ignore[attr-defined]
        raise
    return run.state, run.steps


def evaluate_rule(body: list, objects: list[dict], canvas: dict) -> dict[str, dict[str, Fraction]]:
    """Run a rule on concrete rational geometry. Validates first."""
    return evaluate_rule_counted(body, objects, canvas)[0]
