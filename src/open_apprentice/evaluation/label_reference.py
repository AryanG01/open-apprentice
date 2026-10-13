"""Symbolic reference for label placement: NO model. It enumerates the DECLARED catalogue (the same hypothesis space the task
generator draws from), keeps the behaviours that fit every piece of evidence, and hands them to the same teaching loop.

ORACLE-ASSISTED BY CONSTRUCTION: because its grammar is the generator's catalogue, it cannot be surprised by an in-catalogue
task; it bounds what a perfect in-catalogue learner achieves and shows nothing about learning outside it. It reads only the
evidence the learner sees (the messages), never the episode.
"""

from __future__ import annotations

import json
from fractions import Fraction

from open_apprentice.concepts.hypotheses import Constraint, fits
from open_apprentice.evaluation.label_episodes import CATALOGUE, behaviour_class
from open_apprentice.evaluation.labels import rule_for_spec
from open_apprentice.providers.mock import MockProvider

_REPS = {}
for _s in CATALOGUE:
    _REPS.setdefault(behaviour_class(_s), _s)
REPRESENTATIVES = list(_REPS.values())


def _constraints(evidence: list[dict]) -> list[Constraint]:
    out = []
    for item in evidence:
        exp = {
            k: {f: Fraction(str(v[f])) for f in ("x", "y", "w", "h")}
            for k, v in item["resulting_geometry"].items()
        }
        out.append(Constraint("positive", item["scene"], exp, source=item["evidence"]))
    return out


def reference_reply(messages) -> dict:
    user = json.loads(
        messages[-1].content if "teaching_evidence" in messages[-1].content else messages[1].content
    )
    cons = _constraints(user["teaching_evidence"])
    cands = []
    for spec in REPRESENTATIVES:
        rule = rule_for_spec(spec)
        if all(fits(rule, c)[0] for c in cons):
            cands.append(
                {"summary": f"{spec.primary}/{spec.fallback}/{spec.scope}/{spec.gap}", "rule": rule}
            )
    return {"candidates": cands}


class ReferenceProvider(MockProvider):
    label = "SYMBOLIC REFERENCE (catalogue, no model)"

    def __init__(self) -> None:
        super().__init__({}, model="symbolic-reference", functions={"hypotheses": reference_reply})
