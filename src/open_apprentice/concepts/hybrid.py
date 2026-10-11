"""Hybrid candidate source: the model's proposals UNIONED with the bounded symbolic search over a declared grammar.

Why: the audit experiment (decisions #44) showed the failure is omission, a wrong rule that fits every answer because the true rule never entered the candidate
set. The enumerator guarantees coverage inside its grammar; the model covers rules the grammar cannot express. Both feed the SAME teaching loop, so
every disagreement is still resolved by the teacher's answer (never by the model's own opinion), and every candidate still has to fit all the evidence.

Candidates are tagged `[model]` or `[search]` so the interface can say where the final rule came from. A failing model call degrades to search-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from open_apprentice.budget import BudgetExhausted, Ledger
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.enumerative import EnumerativeSource
from open_apprentice.concepts.hypotheses import (
    Candidate,
    Constraint,
    GenerationReport,
    generate_candidates,
)
from open_apprentice.providers.base import Provider, ProviderError

MAX_UNION = (
    6  # a question shows at most four outcomes; the union is trimmed after behavioural dedupe
)


@dataclass
class HybridSource:
    provider: Optional[Provider]
    ledger: Ledger
    dom: DomainManifest
    object_counts: list[int]
    completion_cap: int = 6000
    max_union: int = MAX_UNION
    origins: dict[str, str] = field(default_factory=dict)  # candidate hash -> "model" | "search"
    model_errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.search = EnumerativeSource(self.dom, self.object_counts)

    async def __call__(
        self, constraints: list[Constraint], rnd: int, rejected: list[str]
    ) -> GenerationReport:
        rep = GenerationReport(rnd)
        found = await self.search(constraints, rnd, rejected)
        model = GenerationReport(rnd)
        if self.provider is not None:
            try:
                model = await generate_candidates(
                    self.provider, self.ledger, constraints, rnd=rnd, rejected_summaries=rejected,
                    object_counts=self.object_counts, max_tokens=self.completion_cap,
                )  # fmt: skip
            except BudgetExhausted:
                raise
            except (
                ProviderError
            ) as e:  # truncation, timeout, format: keep the search results, record why
                self.model_errors.append(e.code)
        seen: dict[str, str] = {}
        merged: list[Candidate] = []
        for origin, cands in (("model", model.accepted), ("search", found.accepted)):
            for c in cands:
                key = (
                    self.search._behaviour_key(c.rule) or c.hash
                )  # behaviourally identical rules count once; the first origin wins
                if key in seen:
                    continue
                seen[key] = origin
                tagged = Candidate(f"[{origin}] {c.summary}", c.rule, c.hash, c.symbolic, c.text)
                self.origins[tagged.hash] = origin
                merged.append(tagged)
        rep.accepted = merged[: self.max_union]
        rep.rejected = model.rejected + found.rejected
        rep.model_calls = model.model_calls
        rep.usage = {
            "label": "HYBRID", "from_model": sum(1 for c in rep.accepted if self.origins.get(c.hash) == "model"),
            "from_search": sum(1 for c in rep.accepted if self.origins.get(c.hash) == "search"),
            "model_error": self.model_errors[-1] if self.model_errors else None, "model_usage": model.usage, "search_usage": found.usage,
        }  # fmt: skip
        return rep
