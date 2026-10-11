"""Text front-end for the restricted rule AST (deviation recorded in docs/decisions.md).

The model writes a few readable lines; this CLOSED-GRAMMAR parser compiles them to the same JSON AST that
rules.validate_rule / evaluate_rule / the Z3 compiler already accept. The AST remains the only stored, hashed and
executed artifact. There is no eval/exec and no name lookup outside the grammar. Errors carry line numbers so they can
be fed back to the model.

  let m = min(24, max(8, 0.08 * objects[0].w))
  clone objects[1] as badge at (objects[0].x + objects[0].w - m - objects[1].w, objects[0].y + m)
  for o in objects with i { move o to (80 + i * 40, 120) }
  if objects[0].w > 150 { ... } else { ... }
  resize objects[0] to (w, h)        # also: clone ... size (w, h)

Numbers: integers and exact decimals (0.08 = 2/25). Operators: + - * / ( ) unary -, < <= > >= == !=, and or not,
min(...) max(...), len(objects). Fields: x y w h. canvas.w / canvas.h. Multiply/divide by constants only (checked later).
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any, Optional

from open_apprentice.concepts.rules import RuleError

_TOKEN = re.compile(
    r"""[ \t\r]*(?:
    (?P<num>\d+\.\d+|\d+)|
    (?P<op><=|>=|==|!=|[-+*/(),.\[\]{}<>=;])|
    (?P<name>[A-Za-z_][A-Za-z_0-9]*)|
    (?P<nl>\n)|
    (?P<comment>\#[^\n]*)
)""",
    re.X,
)
KEYWORDS = {
    "let",
    "move",
    "resize",
    "clone",
    "as",
    "at",
    "size",
    "to",
    "for",
    "in",
    "with",
    "if",
    "else",
    "and",
    "or",
    "not",
}
FIELDS = {"x", "y", "w", "h"}
MAX_CHARS = 4000


class RuleSyntaxError(RuleError):
    pass


class _Tok:
    def __init__(self, kind: str, text: str, line: int) -> None:
        self.kind, self.text, self.line = kind, text, line


CONTINUES = {
    "+",
    "-",
    "*",
    "/",
    ",",
    "(",
    "[",
    "=",
    "<",
    ">",
    "<=",
    ">=",
    "==",
    "!=",
    "and",
    "or",
    "not",
}


def _lex(src: str) -> list[_Tok]:
    if len(src) > MAX_CHARS:
        raise RuleSyntaxError("rule text too long")
    toks: list[_Tok] = []
    pos, line, depth = 0, 1, 0
    src = src.replace("\r\n", "\n")
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m or m.end() == pos:
            if src[pos:].strip() == "":
                break
            raise RuleSyntaxError(f"line {line}: unexpected character {src[pos:pos + 1]!r}")
        pos = m.end()
        k = m.lastgroup
        if k == "nl":
            # a newline ends a statement unless we are inside ()/[] or the previous token expects more
            if depth == 0 and not (toks and toks[-1].text in CONTINUES):
                toks.append(_Tok("nl", "\n", line))
            line += 1
        elif k == "comment":
            continue
        elif k:
            if k == "op":
                depth += (m.group(k) in "([") - (m.group(k) in ")]")
                depth = max(depth, 0)
            toks.append(_Tok(k, m.group(k), line))
    toks.append(_Tok("eof", "", line))
    return toks


def _dec(text: str) -> Any:
    f = Fraction(text)
    return int(f) if f.denominator == 1 else {"rat": f"{f.numerator}/{f.denominator}"}


class _Parser:
    def __init__(self, toks: list[_Tok], aliases: Optional[dict[str, int]] = None) -> None:
        self.t, self.i = toks, 0
        self.aliases = aliases or {}  # demonstration object id -> position; resolved to objects[K]
        self.scope: set[str] = (
            set()
        )  # let-names and loop vars in scope (for early, specific errors)

    # ---- token helpers
    @property
    def cur(self) -> _Tok:
        return self.t[self.i]

    def err(self, msg: str) -> RuleSyntaxError:
        return RuleSyntaxError(f"line {self.cur.line}: {msg} (near {self.cur.text!r})")

    def skip_nl(self) -> None:
        while self.cur.kind == "nl" or self.cur.text == ";":
            self.i += 1

    def accept(self, text: str) -> bool:
        if self.cur.text == text and self.cur.kind in ("op", "name"):
            self.i += 1
            return True
        return False

    def expect(self, text: str, what: str = "") -> None:
        if not self.accept(text):
            raise self.err(f"expected {text!r}" + (f" {what}" if what else ""))

    def name(self, what: str) -> str:
        if self.cur.kind != "name" or self.cur.text in KEYWORDS:
            raise self.err(f"expected a name for {what}")
        n = self.cur.text
        self.i += 1
        return n

    # ---- statements
    def block(self) -> list[dict]:
        out = []
        self.skip_nl()
        while self.cur.kind != "eof" and self.cur.text != "}":
            out.append(self.stmt())
            self.skip_nl()
        return out

    def braces(self) -> list[dict]:
        self.expect("{", "to open a block")
        body = self.block()
        self.expect("}", "to close the block")
        return body

    def stmt(self) -> dict:
        w = self.cur.text
        if w == "let":
            self.i += 1
            n = self.name("let")
            self.expect("=")
            v = self.expr()
            self.scope.add(n)
            return {"op": "let", "name": n, "value": v}
        if w in ("move", "resize"):
            self.i += 1
            target = self.ref(allow_bare=True)
            self.expect("to", f"after the {w} target")
            self.expect("(")
            a = self.expr()
            self.expect(",")
            b = self.expr()
            self.expect(")")
            ka, kb = ("x", "y") if w == "move" else ("w", "h")
            return {
                "op": "emit_target",
                "kind": "move_existing" if w == "move" else "resize_existing",
                "target": target,
                ka: a,
                kb: b,
            }
        if w == "clone":
            self.i += 1
            proto = self.ref(allow_bare=True)
            self.expect("as", "after the clone prototype")
            sym = self.name("clone symbol")
            self.expect("at", "after the clone symbol")
            self.expect("(")
            x = self.expr()
            self.expect(",")
            y = self.expr()
            self.expect(")")
            node = {
                "op": "emit_target",
                "kind": "clone_place",
                "proto": proto,
                "symbol": sym,
                "x": x,
                "y": y,
            }
            if self.accept("size"):
                self.expect("(")
                node["w"] = self.expr()
                self.expect(",")
                node["h"] = self.expr()
                self.expect(")")
            return node
        if w == "for":
            self.i += 1
            var = self.name("loop variable")
            self.expect("in")
            self.expect("objects", "(only 'objects' can be iterated)")
            idx = self.name("index variable") if self.accept("with") else None
            self.scope.add(var)
            if idx:
                self.scope.add(idx)
            node = {"op": "for_each", "var": var, "over": {"ref": "objects"}, "body": self.braces()}
            if idx:
                node["index_var"] = idx
            return node
        if w == "if":
            self.i += 1
            cond = self.expr()
            then = self.braces()
            els = []
            self.skip_nl()
            if self.accept("else"):
                els = self.braces()
            return {"op": "if", "cond": cond, "then": then, "else": els}
        raise self.err("expected a statement (let / move / resize / clone / for / if)")

    # ---- references and expressions
    def ref(self, allow_bare: bool = False) -> dict:
        if self.cur.text == "objects":
            self.i += 1
            self.expect("[", "after 'objects' (write objects[0], objects[1], ...)")
            if self.cur.kind != "num" or "." in self.cur.text:
                raise self.err("object index must be a whole number")
            k = self.cur.text
            self.i += 1
            self.expect("]")
            return {"ref": f"objects.{k}"}
        if allow_bare and self.cur.kind == "name" and self.cur.text not in KEYWORDS:
            n = self.name("object")
            if n not in self.scope and n in self.aliases:
                return {"ref": f"objects.{self.aliases[n]}"}
            if n not in self.scope:
                raise self.err(f"unknown name {n!r}; define it with let or a for loop first")
            return {"ref": f"locals.{n}"}
        raise self.err("expected an object: objects[K] or a loop variable")

    def expr(self) -> Any:
        return self.p_or()

    def p_or(self) -> Any:
        a = self.p_and()
        while self.accept("or"):
            a = {"op": "or", "args": [a, self.p_and()]}
        return a

    def p_and(self) -> Any:
        a = self.p_not()
        while self.accept("and"):
            a = {"op": "and", "args": [a, self.p_not()]}
        return a

    def p_not(self) -> Any:
        if self.accept("not"):
            return {"op": "not", "args": [self.p_not()]}
        return self.p_cmp()

    def p_cmp(self) -> Any:
        a = self.p_add()
        ops = {"<": "lt", "<=": "le", ">": "gt", ">=": "ge", "==": "eq", "!=": "ne"}
        if self.cur.kind == "op" and self.cur.text in ops:
            o = ops[self.cur.text]
            self.i += 1
            a = {"op": o, "args": [a, self.p_add()]}
        return a

    def p_add(self) -> Any:
        a = self.p_mul()
        while self.cur.kind == "op" and self.cur.text in ("+", "-"):
            o = "add" if self.cur.text == "+" else "sub"
            self.i += 1
            a = {"op": o, "args": [a, self.p_mul()]}
        return a

    def p_mul(self) -> Any:
        a = self.p_unary()
        while self.cur.kind == "op" and self.cur.text in ("*", "/"):
            o = "mul" if self.cur.text == "*" else "div"
            self.i += 1
            a = {"op": o, "args": [a, self.p_unary()]}
        return a

    def p_unary(self) -> Any:
        if self.cur.kind == "op" and self.cur.text == "-":
            self.i += 1
            return {"op": "sub", "args": [0, self.p_unary()]}
        return self.p_primary()

    def p_primary(self) -> Any:
        c = self.cur
        if c.kind == "num":
            self.i += 1
            return _dec(c.text)
        if c.text == "(":
            self.i += 1
            e = self.expr()
            self.expect(")")
            return e
        if c.text in ("min", "max"):
            self.i += 1
            self.expect("(")
            args = [self.expr()]
            while self.accept(","):
                args.append(self.expr())
            self.expect(")")
            return {"op": c.text, "args": args}
        if c.text == "len":
            self.i += 1
            self.expect("(")
            self.expect("objects")
            self.expect(")")
            return {"op": "len", "args": [{"ref": "objects"}]}
        if c.text == "canvas":
            self.i += 1
            self.expect(".")
            f = self.cur.text
            if f not in ("w", "h"):
                raise self.err("canvas has only .w and .h")
            self.i += 1
            return {"ref": f"canvas.{f}"}
        if c.text == "objects" or (c.kind == "name" and c.text not in KEYWORDS):
            if c.text == "objects":
                o = self.ref()
            else:
                n = self.name("value")
                if n not in self.scope and n in self.aliases:
                    o = {"ref": f"objects.{self.aliases[n]}"}
                elif n not in self.scope:
                    raise self.err(f"unknown name {n!r}; define it with let or a for loop first")
                else:
                    o = {"ref": f"locals.{n}"}
            if self.accept("."):
                if self.cur.text not in FIELDS:
                    raise self.err("a field must be one of x, y, w, h")
                f = self.cur.text
                self.i += 1
                return {"op": "get", "args": [o, f]}
            return o
        raise self.err("expected a number, name, objects[K].field, canvas.w/h, min/max(...) or '('")


def parse_rule_text(src: str, aliases: Optional[dict[str, int]] = None) -> list[dict]:
    """Compile rule text to the restricted AST (not yet validated: callers run rules.validate_rule).

    `aliases` maps the demonstration scene's object ids to their list positions so a model that writes `proto` or `card0`
    is understood; the compiled rule is positional (objects[K]) and so generalises like any other.
    """
    p = _Parser(_lex(src), aliases)
    body = p.block()
    if p.cur.kind != "eof":
        raise p.err("unexpected closing brace or trailing text")
    if not body:
        raise RuleSyntaxError("empty rule")
    return body
