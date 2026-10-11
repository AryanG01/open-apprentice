"""Small controlled batteries (spec 21.11). Both run in DISPOSABLE scenes with an evaluator-controlled artificial
intervention and must never be presented as deployment behaviour or as natural rates.

1. Grounding ablation: the same policy with and without native confirmation, on episodes that contain the
   abstraction-gap (tool change). The final independent evaluator and all budgets are unchanged.
2. Target omission: the FIRST-round candidate set is a labelled fixture that omits the true rule. The only extra
   evidence any method gets is a COUNTED corrected output example. This shows the Neither path, not how often
   natural generation omits the target.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from open_apprentice.agent.policies import CountingTeacher, drive_teaching
from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.domain import DomainManifest
from open_apprentice.concepts.enumerative import EnumerativeSource
from open_apprentice.concepts.hypotheses import Candidate, GenerationReport
from open_apprentice.concepts.query_selection import sample_scenes
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.concepts.schemas import sha
from open_apprentice.concepts.teaching import State, TeachingSession
from open_apprentice.concepts.witness import SolverPool
from open_apprentice.evaluation.teacher import BenchmarkTeacher
from open_apprentice.providers.base import Provider, RawCompletion


def heldout_equal(
    rule: list, latent: list, dom: DomainManifest, counts: list[int], k: int = 24, seed: int = 99
) -> bool:
    """Independent intent check: the learned rule reproduces the private latent on held-out in-domain scenes."""
    for sc in sample_scenes(dom, counts, k, seed):
        if evaluate_rule(rule, sc["objects"], sc["canvas"]) != evaluate_rule(
            latent, sc["objects"], sc["canvas"]
        ):
            return False
    return True


@dataclass
class OmissionResult:
    method: str
    template: str
    state: str
    intent_state: str
    recovered: bool  # final rule matches the private latent on held-out scenes
    teacher_answers: int
    teacher_corrections: int
    rounds: int
    note: str = "FIXTURE first-round candidate set omits the true rule (artificial intervention)"


class FirstRoundFixtureProvider(Provider):
    """Wraps a provider: the FIRST 'hypotheses' reply is the labelled fixture; everything later is the real provider's."""

    def __init__(self, inner: Provider, fixture_reply: dict) -> None:
        self.inner, self._fixture, self._used = inner, fixture_reply, False
        self.label = inner.label
        self.requested_model = inner.requested_model

    async def _call(self, messages, *, max_tokens, ctx):
        if ctx.role == "hypotheses" and not self._used:
            import json

            self._used = True
            return RawCompletion(
                json.dumps(self._fixture),
                self.requested_model,
                "fixture",
                "stop",
                1,
                1,
                0.0,
                usd=0.0,
            )
        return await self.inner._call(messages, max_tokens=max_tokens, ctx=ctx)


class FirstRoundFixtureSource:
    """Same idea for the enumerative reference: round 1 is the fixture set, later rounds use the real enumerator."""

    def __init__(self, inner: EnumerativeSource, fixture_rules: list[tuple[str, list]]) -> None:
        self.inner, self.fixture = inner, fixture_rules

    async def __call__(self, constraints, rnd, rejected) -> GenerationReport:
        if rnd == 1:
            rep = GenerationReport(1)
            from open_apprentice.concepts.hypotheses import fits

            for summary, rule in self.fixture:
                if all(fits(rule, c)[0] for c in constraints):
                    rep.accepted.append(Candidate(summary, rule, sha(rule), "supported"))
                else:
                    rep.rejected.append(
                        {
                            "summary": summary,
                            "reason": "fixture candidate does not fit the demonstration",
                        }
                    )
            rep.usage = {"label": "FIXTURE", "grammar_round": 1}
            return rep
        return await self.inner(constraints, rnd, rejected)


async def run_omission_case(
    method: str,
    template: str,
    latent: list,
    demo: dict,
    dom: DomainManifest,
    counts: list[int],
    pool: SolverPool,
    *,
    provider: Optional[Provider] = None,
    source: Any = None,
) -> OmissionResult:
    teacher = CountingTeacher(BenchmarkTeacher(latent))
    sess = TeachingSession(
        provider,
        Ledger(Limits(tokens=200_000, calls=64)),
        dom,
        counts,
        pool=pool,
        teacher_source="benchmark_teacher",
        candidate_source=source,
    )
    await sess.start(demo)
    await drive_teaching(sess, teacher)
    ok = sess.state == State.INTENT_READY and heldout_equal(
        sess.finalize().rule, latent, dom, counts
    )
    return OmissionResult(
        method,
        template,
        sess.state.value,
        sess.intent_state.value,
        ok,
        teacher.answers,
        teacher.corrections,
        sess.rounds,
    )
