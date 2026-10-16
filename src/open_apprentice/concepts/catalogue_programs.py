"""System C's candidate source (spec 7): the 24 declared catalogue behaviours as rule programs, written in the rule text
language and parsed here. Built independently of the evaluator (which this package may not import): side in
{right, below} x fallback in {none, the other side} x scope in {all, notes} x gap in {8, 12, 16}.

A fallback is taken when the primary pose leaves the canvas or overlaps any object other than the label and its node.
Abstaining on behaviours outside the catalogue is legitimate for this system."""

from __future__ import annotations

from fractions import Fraction
from itertools import product
from typing import Optional

from open_apprentice.concepts.label_enumerative import _f, _fits, _out, _scene
from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.concepts.rules import validate_rule

OTHER = {"right": "below", "below": "right"}
POSE = {
    "right": ("a.x + a.w + {g}", "a.y + (a.h - o.h) / 2"),
    "below": ("a.x + (a.w - o.w) / 2", "a.y + a.h + {g}"),
}


def _move(side: str, gap: int) -> str:
    x, y = (p.format(g=gap) for p in POSE[side])
    return f"move o to ({x}, {y})"


def program_text(side: str, fallback: Optional[str], scope: str, gap: int, extra: str = "") -> str:
    """`extra` is an additional label condition (a correction scope selector)."""
    if fallback is None:
        body = [_move(side, gap)]
    else:
        px, py = (p.format(g=gap) for p in POSE[side])
        hit = (
            "p.id != o.id and p.id != a.id and px < p.x + p.w and p.x < px + o.w "
            "and py < p.y + p.h and p.y < py + o.h"
        )
        body = [
            f"let px = {px}",
            f"let py = {py}",
            "let blocked = px < 0 or py < 0 or px + o.w > canvas.w or py + o.h > canvas.h",
            "for p in objects {",
            f"  let blocked = blocked or ({hit})",
            "}",
            "if blocked {",
            f"  {_move(fallback, gap)}",
            "} else {",
            "  move o to (px, py)",
            "}",
        ]
    body = ["let a = object(o.attached)", *body]
    for cond in (c for c in (extra, 'o.role == "note"' if scope == "notes" else "") if c):
        body = [f"if {cond} {{", *("  " + b for b in body), "}"]
    lines = ["for o in objects {", '  if o.kind == "label" {', *("    " + b for b in body)]
    return "\n".join([*lines, "  }", "}"])


def _parse(text: str) -> list:
    rule = parse_rule_text(text)
    validate_rule(rule)
    return rule


SPECS = tuple(
    (side, OTHER[side] if fb else None, scope, gap)
    for side, fb, scope, gap in product(
        ("right", "below"), (False, True), ("all", "notes"), (8, 12, 16)
    )
)
CATALOGUE: tuple[tuple[str, list], ...] = tuple(
    (f"{s}/{fb or 'none'}/{sc}/{g}", _parse(program_text(s, fb, sc, g))) for s, fb, sc, g in SPECS
)


def _items(evidence: list[dict]) -> list[tuple[list[dict], dict, dict]]:
    items = []
    for it in evidence:
        objs, canvas = _scene(it["scene"]["objects"], it["scene"]["canvas"])
        moves = {k: (_f(v[0]), _f(v[1])) for k, v in it.get("labels_moved_to", {}).items()}
        items.append((objs, canvas, moves))
    return items


class CatalogueProposer:
    """Proposer (learning) and ScopeProposer (corrections) over the catalogue only."""

    def propose(
        self, evidence_json: dict, round_kind: str, feedback: tuple[str, ...]
    ) -> tuple[list[dict], dict, Fraction]:
        items = _items(evidence_json.get("teaching_evidence", []))
        out = [
            {"rule": rule, "summary": name, "text": program_text(*spec)}
            for (name, rule), spec in zip(CATALOGUE, SPECS)
            if items and all(_fits(_out(rule, objs, cv), objs, mv, True) for objs, cv, mv in items)
        ]
        return out, {"source": "catalogue", "evaluated": len(CATALOGUE)}, Fraction(0)

    def propose_scope(
        self, evidence_json: dict, round_kind: str
    ) -> tuple[list[dict], dict, Fraction]:
        """A catalogue behaviour applied inside a role selector (or to every label), after the base program."""
        objs, canvas = _scene(evidence_json["corrected_scene_objects"], evidence_json["canvas"])
        moves = {k: (_f(v[0]), _f(v[1])) for k, v in evidence_json["corrected_output"].items()}
        base = list(evidence_json.get("base_program", {}).get("rule") or [])
        by_id = {o["id"]: o for o in objs}
        roles = sorted({by_id[k]["role"] for k in moves if k in by_id and by_id[k]["role"]})
        out = []
        for selector in [*(f'o.role == "{r}"' for r in roles), 'o.kind == "label"']:
            for s, fb, sc, g in SPECS:
                if sc != "all":
                    continue
                combined = base + _parse(program_text(s, fb, sc, g, extra=selector))
                if _fits(_out(combined, objs, canvas), objs, moves, False):
                    out.append(
                        {
                            "rule": combined,
                            "selector": selector,
                            "summary": f"labels with {selector}: {s}/{fb or 'none'}/{g}",
                        }
                    )
        return out, {"source": "catalogue", "evaluated": 12 * (len(roles) + 1)}, Fraction(0)
