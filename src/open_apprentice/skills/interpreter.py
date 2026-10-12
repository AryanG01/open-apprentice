"""Restricted JSON-AST interpreter (spec 7.2).

No eval/exec/imports. Statements: let, call, for_each, if, assert, return.
Expressions: literals, refs, finite arithmetic, len/min/max, comparisons, and/or/not.
Hard limits: 64 static statements, nesting depth 4, loops <= 16 elements, 500 evaluated
expressions, 100 primitive actions (expanded loop operations counted).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping

MAX_STATEMENTS = 64
MAX_DEPTH = 8  # spec 7.2 says 4; raised (decisions #34): real bindings nest for_each > if/else-if chains > if. Other caps still bound execution.
MAX_LOOP = 16
MAX_EXPRS = 500
MAX_ACTIONS = 100
MAX_STR = 1000
MAX_ARRAY = 256
_FORBIDDEN_KEYS = frozenset({"__proto__", "constructor", "prototype"})
_REF_ROOTS = ("inputs", "locals")


class ProgramError(Exception):
    """Static or runtime rejection. Never silently repaired."""


class AssertionRejected(ProgramError):
    """An `assert` statement failed: the procedure attempt is rejected."""


def _finite(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        try:
            finite = math.isfinite(v)
        except OverflowError:  # an int too large to convert to float
            finite = False
        if not finite:
            raise ProgramError("non-finite number")
    elif isinstance(v, str):
        if len(v) > MAX_STR:
            raise ProgramError("string too long")
    elif isinstance(v, (list, tuple)):
        if len(v) > MAX_ARRAY:
            raise ProgramError("array too large")
    return v


def validate_program(program: list, allowed_tools: frozenset[str]) -> int:
    """Static validation. Returns the static statement count."""
    count = 0

    def walk(stmts: Any, depth: int) -> None:
        nonlocal count
        if depth > MAX_DEPTH:
            raise ProgramError("nesting too deep")
        if not isinstance(stmts, list):
            raise ProgramError("block must be a list")
        for s in stmts:
            count += 1
            if count > MAX_STATEMENTS:
                raise ProgramError("too many statements")
            if not isinstance(s, dict) or _FORBIDDEN_KEYS & s.keys():
                raise ProgramError(
                    f"bad statement (each statement must be an object with an 'op'): {str(s)[:70]}"
                )
            op = s.get("op")
            if op == "call":
                if s.get("tool") not in allowed_tools:
                    raise ProgramError(f"tool not allowlisted: {s.get('tool')!r}")
            elif op == "for_each":
                walk(s.get("body"), depth + 1)
            elif op == "if":
                walk(s.get("then"), depth + 1)
                walk(s.get("else", []), depth + 1)
            elif op not in ("let", "assert", "return"):
                raise ProgramError(f"unknown statement op: {op!r}")

    walk(program, 1)
    return count


@dataclass
class _State:
    inputs: Mapping[str, Any]
    locals: dict[str, Any]
    tools: Mapping[str, Callable[..., Any]]
    exprs: int = 0
    actions: int = 0


class _Return(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


def _ref(path: str, st: _State) -> Any:
    root, *rest = path.split(".")
    if root not in _REF_ROOTS or _FORBIDDEN_KEYS & set(rest):
        raise ProgramError(f"bad reference: {path!r}")
    cur: Any = st.inputs if root == "inputs" else st.locals
    for part in rest:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            raise ProgramError(f"unresolved reference: {path!r}")
    return cur


_BIN = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "mul": lambda a, b: a * b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}


def evaluate(e: Any, st: _State) -> Any:
    st.exprs += 1
    if st.exprs > MAX_EXPRS:
        raise ProgramError("expression budget exceeded")
    if not isinstance(e, dict):
        return _finite(e)  # literal
    if _FORBIDDEN_KEYS & e.keys():
        raise ProgramError("forbidden key")
    if "ref" in e:
        return _finite(_ref(e["ref"], st))
    if "lit" in e:
        return _finite(e["lit"])
    op = e.get("op")
    a = e.get("args", [])
    if op in _BIN:
        if len(a) != 2:
            raise ProgramError(f"{op} takes 2 args")
        x, y = evaluate(a[0], st), evaluate(a[1], st)
        if op in ("add", "sub", "mul", "lt", "le", "gt", "ge") and not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y)
        ):
            raise ProgramError(f"{op} needs numbers")
        return _finite(_BIN[op](x, y))
    if op == "div":
        x, y = evaluate(a[0], st), evaluate(a[1], st)
        if y == 0:
            raise ProgramError("division by zero")
        return _finite(x / y)
    if op in ("min", "max"):
        vals = [evaluate(x, st) for x in a]
        if not vals:
            raise ProgramError(f"{op} of nothing")
        return min(vals) if op == "min" else max(vals)
    if op == "name":
        parts = [evaluate(x, st) for x in a]
        if (
            len(parts) != 2
            or not all(isinstance(x, str) for x in parts)
            or len(parts[0]) + len(parts[1]) > 100
        ):
            raise ProgramError("name needs two strings (<=100 chars total)")
        return parts[0] + parts[1]
    if op == "list":
        if len(a) > MAX_LOOP:
            raise ProgramError("list literal longer than 16 elements")
        return [evaluate(x, st) for x in a]
    if op == "len":
        v = evaluate(a[0], st)
        if not isinstance(v, (list, str)):
            raise ProgramError("len needs list or string")
        return len(v)
    if op == "index":
        seq, i = evaluate(a[0], st), evaluate(a[1], st)
        if (
            not isinstance(seq, list)
            or not isinstance(i, int)
            or isinstance(i, bool)
            or not 0 <= i < len(seq)
        ):
            raise ProgramError("bad index")
        return seq[i]
    if op == "get":
        obj, key = evaluate(a[0], st), a[1]
        if (
            not isinstance(obj, dict)
            or not isinstance(key, str)
            or key in _FORBIDDEN_KEYS
            or key not in obj
        ):
            raise ProgramError(
                f"bad field access .{key!r}: "
                + (
                    f"object has {sorted(obj)[:8]}"
                    if isinstance(obj, dict)
                    else f"get needs an object, got {type(obj).__name__} (use index for lists)"
                )
            )
        return obj[key]
    if op == "and":
        return all(bool(evaluate(x, st)) for x in a)
    if op == "or":
        return any(bool(evaluate(x, st)) for x in a)
    if op == "not":
        return not bool(evaluate(a[0], st))
    raise ProgramError(
        f'unknown expression op {op!r} in {str(e)[:70]}; an expression is a number/string, {{"ref":..}} or {{"op":..,"args":[..]}} with op in add sub mul div min max lt le gt ge eq ne and or not len index get list name'
    )


def _run(block: list, st: _State) -> None:
    for s in block:
        op = s["op"]
        if op == "let":
            st.locals[s["name"]] = evaluate(s["value"], st)
        elif op == "call":
            st.actions += 1
            if st.actions > MAX_ACTIONS:
                raise ProgramError("primitive action budget exceeded")
            args = {k: evaluate(v, st) for k, v in s.get("args", {}).items()}
            res = st.tools[s["tool"]](**args)
            if "bind" in s:
                st.locals[s["bind"]] = res
        elif op == "for_each":
            items = evaluate(s["over"], st)
            if not isinstance(items, list) or len(items) > MAX_LOOP:
                raise ProgramError("loop collection invalid or > 16 elements")
            for item in items:
                st.locals[s["var"]] = item
                _run(s["body"], st)
        elif op == "if":
            _run(s["then"] if evaluate(s["cond"], st) else s.get("else", []), st)
        elif op == "assert":
            if not evaluate(s["cond"], st):
                raise AssertionRejected(s.get("message", "assertion failed"))
        elif op == "return":
            raise _Return(evaluate(s["value"], st))


def run_program(
    program: list,
    inputs: Mapping[str, Any],
    tools: Mapping[str, Callable[..., Any]],
) -> tuple[Any, dict[str, int]]:
    """Validate then execute. Returns (result, {'exprs','actions'}). `tools` is the allowlist."""
    validate_program(program, frozenset(tools))
    st = _State(inputs=inputs, locals={}, tools=tools)
    try:
        _run(program, st)
    except _Return as r:
        return r.value, {"exprs": st.exprs, "actions": st.actions}
    return None, {"exprs": st.exprs, "actions": st.actions}
