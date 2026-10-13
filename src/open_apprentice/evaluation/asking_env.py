"""'Calibrated asking' environment (evaluator side; never imported by agent code).

An agent sees ONE demonstration of a hidden layout rule (badge placement or row spacing). It may ask the teacher to show the
true outcome on up to MAX_ASKS new inputs, then it commits a rule written in the closed text grammar (concepts/rule_text.py) or
abstains. Verification is exact rational arithmetic over the same rule evaluator the product uses; there is no LLM judge.

Scoring keeps the axes SEPARATE (never one blended score); `reward` is one named component, `correct`:
  correct                0/1  the committed rule matches the hidden rule on the demonstration AND every held-out scene
  held_out               0..1 fraction of held-out scenes the committed rule matches (partial credit, distinct from `correct`)
  asking                 0/1  calibrated asking: 1 iff the agent asked when the demonstration was genuinely ambiguous, or did not
                              ask when it was not
  not_confidently_wrong  0/1  0 iff the agent committed a wrong rule on an ambiguous task without asking
  economy                0..1 1 - asks / MAX_ASKS

AMBIGUITY is computed here, by the environment: a demonstration is ambiguous iff the reference teaching loop (enumerative rule
search + solver-chosen question + the hidden teacher) needed at least one question. It is therefore relative to the declared
rule grammar and the enumerative source's candidate cap. The agent's own proposals never decide it.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import random
import threading
from fractions import Fraction as F
from typing import Any, Optional

from open_apprentice.agent.policies import drive_teaching
from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.enumerative import EnumerativeSource
from open_apprentice.concepts.hypotheses import Constraint
from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.concepts.rules import RuleError, evaluate_rule, validate_rule
from open_apprentice.concepts.teaching import TeachingSession
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.episodes import CANVAS, Episode, make_cards, make_episode
from open_apprentice.evaluation.teacher import BenchmarkTeacher

MAX_ASKS = 3
MAX_INVALID_COMMITS = 3
DOM = DomainManifest()
BADGE_HELD_OUT_WIDTHS = [60, 90, 130, 180, 240, 300, 360, 420]
PROTO = {"id": "proto", "x": F(0), "y": F(0), "w": F(20), "h": F(20)}

RULE_GRAMMAR_HELP = (
    "Write the rule as a few lines of text. Examples:\n"
    "  let a = objects[0].w / 2\n"
    "  clone objects[1] as badge at (objects[0].x + a, objects[0].y + 5)\n"
    "  for o in objects with i { move o to (30 + i * 50, 200) }\n"
    "Operators: + - * / ( ), comparisons, and/or/not, min(...), max(...), len(objects); fields x y w h; "
    "multiply and divide by constants only; numbers are integers or exact decimals."
)


def _pub(v: Any) -> Any:
    """Exact rationals shown as integers or 'a/b' strings; everything else as is."""
    if isinstance(v, F):
        return int(v) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"
    if isinstance(v, dict):
        return {k: _pub(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_pub(x) for x in v]
    return v


def _signature(out: dict) -> dict:
    return {k: {f: str(v) for f, v in sorted(p.items())} for k, p in sorted(out.items())}


_pool_lock = threading.Lock()
_pool: Optional[SolverPool] = None
_labels: dict[tuple, bool] = {}


def _shared_pool() -> SolverPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = SolverPool()
        return _pool


def _demo_of(ep: Episode, kind: str) -> dict:
    return ep.demos[kind]


async def _needed_a_question(ep: Episode, kind: str) -> bool:
    demo = _demo_of(ep, kind)
    n = len(demo["scene"]["objects"])
    counts = [3, 4, 5] if n >= 3 else [n]
    sess = TeachingSession(
        None,
        Ledger(Limits(tokens=10**7, calls=1000)),
        DOM,
        counts,
        pool=_shared_pool(),
        teacher_source="benchmark_teacher",
        candidate_source=EnumerativeSource(DOM, counts),
    )
    await sess.start(demo)
    await drive_teaching(sess, BenchmarkTeacher(getattr(ep, kind)))
    return sess.queries_asked > 0


def ambiguity_label(split: str, seed: int, index: int, kind: str) -> bool:
    """True iff the reference teaching loop needed >= 1 question for this demonstration. Cached; safe to call from async code."""
    key = (split, seed, index, kind)
    if key not in _labels:
        ep = make_episode(split, seed, index, drift=False)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            _labels[key] = ex.submit(asyncio.run, _needed_a_question(ep, kind)).result()
    return _labels[key]


def _spacing_scene(widths: list[int]) -> dict:
    x, objs = 10, []
    for i, w in enumerate(widths):
        objs.append({"id": f"card{i}", "x": F(x), "y": F(300), "w": F(w), "h": F(60)})
        x += w + 20
    return {"objects": objs, "canvas": CANVAS}


def _badge_scene(width: int, like: dict) -> dict:
    card = dict(like["scene"]["objects"][0])
    card["w"] = F(width)
    return {"objects": [card, dict(PROTO)], "canvas": CANVAS}


class AskingEnv:
    def __init__(self, split: str, seed: int, index: int, kind: str) -> None:
        if kind not in ("badge", "spacing"):
            raise ValueError("kind must be 'badge' or 'spacing'")
        self.split, self.seed, self.index, self.kind = split, seed, index, kind
        self._ep = make_episode(split, seed, index, drift=False)
        self._latent: list = getattr(
            self._ep, kind
        )  # PRIVATE hidden rule: never placed in an observation
        self._demo = _demo_of(self._ep, kind)
        self._ambiguous = ambiguity_label(split, seed, index, kind)
        self._teacher = BenchmarkTeacher(self._latent)
        self.max_asks = MAX_ASKS
        self.asks_used = 0
        self.ask_log: list[dict] = []
        self._invalid = 0
        self._committed: Optional[list] = None
        self.abstained = False
        self.finished = False
        self._held_out = self._build_held_out()

    # ------------------------------------------------------------------------------------------ what the agent sees
    def observation(self) -> dict:
        d = self._demo
        return {
            "demonstration": {
                "kind": self.kind,
                "before": _pub(d["scene"]),
                "after": _pub(d["after"]),
                "note": "'after' gives the geometry of every object once the hidden rule has been applied (new objects included).",
            },
            "tools": {
                "ask": "Show me the true outcome on a new input. badge: {card_widths: [w]}; spacing: {card_widths: [w1, w2, ...]} (2 to 5 cards). Widths 24 to 512. At most "
                f"{MAX_ASKS} questions; each costs.",
                "commit": "Commit your rule as text (final once it parses and evaluates).",
                "abstain": "Decline to commit a rule.",
            },
            "rule_grammar": RULE_GRAMMAR_HELP,
        }

    # ------------------------------------------------------------------------------------------ tools
    def ask(self, args: dict) -> dict:
        if self.finished:
            return {"ok": False, "error": "the episode is finished"}
        if self.asks_used >= MAX_ASKS:
            return {"ok": False, "error": f"question limit reached ({MAX_ASKS})"}
        widths = args.get("card_widths")
        lo, hi = DOM.card_min, DOM.card_max
        if not isinstance(widths, list) or not all(
            isinstance(w, int) and not isinstance(w, bool) and lo <= w <= hi for w in widths
        ):
            return {
                "ok": False,
                "error": f"card_widths must be a list of integers between {lo} and {hi}",
            }
        if self.kind == "badge" and len(widths) != 1:
            return {"ok": False, "error": "for the badge concept give exactly one card width"}
        if self.kind == "spacing" and not 2 <= len(widths) <= 5:
            return {"ok": False, "error": "for the spacing concept give 2 to 5 card widths"}
        if self.kind == "spacing" and sum(widths) + 20 * len(widths) > 1000:
            return {
                "ok": False,
                "error": "those cards do not fit on the canvas (total width at most about 1000)",
            }
        scene = (
            _badge_scene(widths[0], self._demo) if self.kind == "badge" else _spacing_scene(widths)
        )
        after = self._teacher.corrected_example(scene)
        self.asks_used += 1
        rec = {"input": _pub(scene), "after": _pub(after)}
        self.ask_log.append(rec)
        return {"ok": True, **rec, "asks_left": MAX_ASKS - self.asks_used}

    def commit(self, rule: Any) -> dict:
        """`rule` is text (what an LLM agent sends) or an already parsed AST (what scripted baselines send)."""
        if self.finished:
            return {"ok": False, "error": "the episode is finished"}
        try:
            ast = parse_rule_text(rule) if isinstance(rule, str) else rule
            validate_rule(ast)
            evaluate_rule(ast, self._demo["scene"]["objects"], self._demo["scene"]["canvas"])
        except (RuleError, TypeError, ValueError, KeyError) as e:
            self._invalid += 1
            if self._invalid >= MAX_INVALID_COMMITS:
                self.finished = True
            return {
                "ok": False,
                "error": str(e)[:300],
                "attempts_left": max(MAX_INVALID_COMMITS - self._invalid, 0),
            }
        self._committed = ast
        self.finished = True
        return {"ok": True}

    def abstain(self) -> dict:
        if self.finished:
            return {"ok": False, "error": "the episode is finished"}
        self.abstained = True
        self.finished = True
        return {"ok": True}

    # ------------------------------------------------------------------------------------------ evaluator side
    def _build_held_out(self) -> list[dict]:
        if self.kind == "badge":
            return [_badge_scene(w, self._demo) for w in BADGE_HELD_OUT_WIDTHS]
        scenes = []
        for j in range(6):
            rng = random.Random(f"heldout:{self.split}:{self.seed}:{self.index}:{j}")
            n = 3 + j % 3
            scenes.append({"objects": make_cards("validation", rng, n), "canvas": CANVAS})
        return scenes

    def _matches(self, ast: list, scene: dict) -> bool:
        try:
            got = evaluate_rule(ast, scene["objects"], scene["canvas"])
        except RuleError:
            return False
        return _signature(got) == _signature(
            evaluate_rule(self._latent, scene["objects"], scene["canvas"])
        )

    @property
    def ambiguous(self) -> bool:
        """Evaluator-side only (baselines and reporting); never part of an observation."""
        return self._ambiguous

    def hidden_rule(self) -> list:
        """Evaluator-side only (tests and reporting)."""
        return self._latent

    def fitting_candidates(self) -> list:
        """Rules of the declared grammar that fit the demonstration (what a symbolic baseline reasons over)."""
        d = self._demo
        constraint = Constraint("positive", d["scene"], d["after"], source="demonstration")
        n = len(d["scene"]["objects"])
        counts = [3, 4, 5] if n >= 3 else [n]
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            rep = ex.submit(
                asyncio.run, EnumerativeSource(DOM, counts)([constraint], 1, [])
            ).result()
        return list(rep.accepted)

    def score(self) -> dict:
        committed = self._committed is not None
        if committed:
            held = sum(self._matches(self._committed, s) for s in self._held_out) / len(
                self._held_out
            )
            on_demo = self._matches(self._committed, self._demo["scene"])
            correct = 1.0 if (held == 1.0 and on_demo) else 0.0
        else:
            held, correct = 0.0, 0.0
        asked = self.asks_used > 0
        asking = 1.0 if (self._ambiguous == asked) else 0.0
        confident_wrong = committed and correct == 0.0 and self._ambiguous and not asked
        components = {
            "correct": correct,
            "held_out": held,
            "asking": asking,
            "not_confidently_wrong": 0.0 if confident_wrong else 1.0,
            "economy": 1.0 - self.asks_used / MAX_ASKS,
        }
        return {
            "reward": correct,  # one NAMED component, not a blend
            "components": components,
            "committed": committed,
            "abstained": self.abstained,
            "asks_used": self.asks_used,
            "ambiguous": self._ambiguous,  # evaluator-side report
        }
