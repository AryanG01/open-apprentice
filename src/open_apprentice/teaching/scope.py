"""Correction scope selectors: one boolean rule-language expression over the label `o` (and `object(o.attached)`).
Membership is computed by running a tiny marker program through the existing evaluator on the ORIGINAL input with the
fixed mapping, so the candidate program never influences its own scope. Spec 5."""

from __future__ import annotations

import re

from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.concepts.rules import RuleError
from open_apprentice.teaching.step import run_output

MAX_LEN = 300
FORBIDDEN = re.compile(r"[{}\n\r;]|\b(objects|for|let|move|resize|clone)\b")
MARK = 1  # members are moved by one unit in the marker program


class SelectorError(Exception):
    pass


def parse_selector(text: str) -> list:
    if len(text) > MAX_LEN or FORBIDDEN.search(text):
        raise SelectorError("a selector is one expression over o and object(o.attached)")
    # nested ifs: the rule language evaluates both sides of `and`, so the selector must only run on labels
    src = (
        f'for o in objects {{\n  if o.kind == "label" {{\n    if {text} {{\n'
        f"      move o to (o.x + {MARK}, o.y)\n    }}\n  }}\n}}"
    )
    try:
        return parse_rule_text(src)
    except RuleError as e:
        raise SelectorError(f"selector does not parse: {e}") from e


def members(selector_text: str, scene: dict) -> frozenset[str]:
    out = run_output(parse_selector(selector_text), scene)
    if out is None:
        raise SelectorError("selector fails to evaluate on this document")
    labels = {o["id"]: o for o in scene["objects"] if o["kind"] == "label"}
    return frozenset(k for k, (x, _) in out.items() if x != labels[k]["x"])
