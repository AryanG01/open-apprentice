"""Deterministic benchmark teacher (D10, spec 8.6/10.3).

Owns a latent rule. It answers ONLY with an accepted option id, 'neither', or (as a counted extra
interaction) the corrected output geometry for a scene. It never returns the formula, parameters, or a
solution program. Answers are recorded with source=benchmark_teacher - NOT a user study.
"""

from __future__ import annotations

from fractions import Fraction

from open_apprentice.concepts.query_selection import differs
from open_apprentice.concepts.rules import evaluate_rule

TEACHER_TOL = Fraction(1, 2)


class BenchmarkTeacher:
    source = "benchmark_teacher"

    def __init__(self, latent_rule: list) -> None:
        self._rule = latent_rule  # private: nothing exposes it
        self.interactions: list[str] = []

    def answer(self, view: dict) -> str:
        """`view` is the public query view (scene + neutral options). Returns 'A'..'D' or 'neither'."""
        truth = evaluate_rule(
            self._rule, view["input_scene"]["objects"], view["input_scene"]["canvas"]
        )
        self.interactions.append("answer")
        for oid, out in view["options"].items():
            if not differs(truth, out, TEACHER_TOL):
                return oid
        return "neither"

    def corrected_example(self, scene: dict) -> dict:
        """The correct output geometry for `scene` - one extra counted teacher interaction."""
        self.interactions.append("corrected_example")
        return evaluate_rule(self._rule, scene["objects"], scene["canvas"])

    def __repr__(self) -> str:
        return "BenchmarkTeacher(<latent rule hidden>)"
