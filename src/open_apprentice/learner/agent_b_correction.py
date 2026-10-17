"""System B's own correction cycle (spec 7: propose_scope, affected-example approval, revision preview, commit through
the same safety checks). Option protocol, as in B's learning cycle: each turn B picks one of its legal next steps. The
requests are built by the shared correction policy pieces (`correction_step`) and performed by the shared
`CorrectionExecutor`, so validation, the ledger, the commit predicate and activation are A's. Only the choices are B's.

Budget (ruling, Plan 6): every B turn is a provider call, so B's correction gets the spec's 4 attempts plus whatever its
learning cycle left unused, never more than the 12 an acquisition-plus-correction episode allows."""

from __future__ import annotations

import uuid
from fractions import Fraction
from itertools import combinations
from typing import Any, Callable, Optional

from open_apprentice.learner.agent_b import BadCall, ToolCall, build_prompt
from open_apprentice.providers.base import ModelFormatError
from open_apprentice.providers.teaching_adapter import _call
from open_apprentice.storage.store import Store
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger, OverBudget
from open_apprentice.teaching.correction_executor import CorrectionExecutor, ScopeProposer
from open_apprentice.teaching.correction_step import (
    CommitCorrection,
    CorrectionConfig,
    admissible_candidates,
    affected_request,
    commit_or_reason,
    inside_scope,
    revision_request,
    scope_request,
)
from open_apprentice.teaching.corrections import derive_draft
from open_apprentice.teaching.events import SessionLog
from open_apprentice.teaching.executor import TRANSIENT, failure_kind
from open_apprentice.teaching.scope import members
from open_apprentice.teaching.step import (
    AskTeacher,
    PresentPreview,
    RequestModelProposal,
    _aid,
    _groups,
    _usable,
)
from open_apprentice.teaching.teacher import ChooseOutput, Teacher

ROLE = "agent_b_correction"


class CorrectionAgentB:
    def __init__(
        self,
        provider_factory: Callable[[], Any],
        store: Store,
        log: SessionLog,
        teacher: Teacher,
        ledger: Ledger,
        scope_proposer: ScopeProposer,
        worst_usd: Fraction,
        max_attempts: int = 4,
        config: CorrectionConfig = CorrectionConfig(),
        max_tokens: int = 6000,
    ) -> None:
        self.factory, self.log, self.ledger, self.worst = provider_factory, log, ledger, worst_usd
        self.max_attempts, self.max_tokens, self.attempts = max_attempts, max_tokens, 0
        self.config = CorrectionConfig(
            config.max_clarifications,
            max_attempts,
            config.max_affected,
            config.max_revision_preview,
        )
        self.cx = CorrectionExecutor(
            store, log, scope_proposer, teacher, ledger, self.config, worst_usd
        )
        self.history: list[dict] = []
        self.prompt = build_prompt("agent_b_correction.md")

    # ---- what B sees
    def _cands(self) -> dict[str, dict]:
        evs = self.log.events()
        return {f"S{k}": c for k, c in enumerate(admissible_candidates(evs, derive_draft(evs)), 1)}

    def status(self) -> Optional[str]:
        return self.cx._status()

    def settle(self) -> Optional[str]:
        """The teacher's override / accident / cancel is recorded by the shared policy, not chosen by B."""
        d = derive_draft(self.log.events())
        if self.status() is None and (d.override or d.dismissed or d.cancelled):
            self.cx.run(max_steps=3)
        return self.status()

    def options(self) -> list[dict]:
        evs = self.log.events()
        d = derive_draft(evs)
        cands = self._cands()
        opts: list[dict] = []
        if self.attempts < self.max_attempts:
            opts.append(
                {"id": "propose_scope", "what": "get candidate revisions with their scopes"}
            )
        clar_left = d.clarifications < self.config.max_clarifications
        if d.authorized is None:
            if (
                clar_left and d.rounds and not cands
            ):  # as in A's policy: only override / accidental to offer
                opts.append(
                    {
                        "id": "ask_scope",
                        "what": "ask whether the edit was a one-off override or an accident",
                    }
                )
            if clar_left and cands:
                ids = sorted(cands)
                pairs = [
                    (a, b) for a, b in combinations(ids, 2) if self._distinct(cands[a], cands[b], d)
                ]
                for sel in [(i,) for i in ids] + pairs:
                    opts.append({"id": "ask_scope:" + ",".join(sel),
                                 "what": "ask which scope was meant: " + " / ".join(cands[i]["selector"] for i in sel)})  # fmt: skip
        else:
            inside = {k: c for k, c in cands.items() if c in inside_scope(d, list(cands.values()))}
            if clar_left and len(inside) >= 2:
                for sid in sorted(d.scenes):
                    groups = _groups(list(inside.values()), d.scenes[sid])
                    if _usable(groups):
                        pick = [next(k for k, c in inside.items() if c is g[1][0]) for g in groups]
                        opts.append({"id": f"ask_choose:{sid}:{','.join(pick)}",
                                     "what": f"ask which output is right on {sid}"})  # fmt: skip
            for k, c in sorted(inside.items()):
                a = affected_request(evs, d, c, self.config)
                if isinstance(a, PresentPreview):
                    opts.append(
                        {"id": f"affected:{k}", "what": f"approve the earlier examples {k} changes"}
                    )
                    continue
                if a is not None:
                    continue  # an unapproved or too-large affected set: this candidate cannot proceed
                r = revision_request(evs, d, c, self.config)
                if isinstance(r, PresentPreview):
                    opts.append(
                        {"id": f"revision_preview:{k}", "what": f"preview {k} on up to 3 documents"}
                    )
                elif r is None and isinstance(commit_or_reason(evs, d, c), CommitCorrection):
                    opts.append({"id": f"commit:{k}", "what": f"save {k}"})
        opts.append({"id": "abstain", "what": 'stop; add "reason"'})
        return opts

    @staticmethod
    def _distinct(a: dict, b: dict, d: Any) -> bool:
        return any(
            members(a["selector"], sc) != members(b["selector"], sc) for sc in d.scenes.values()
        )

    def _state(self) -> dict:
        evs = self.log.events()
        d = derive_draft(evs)
        return {
            "corrected_document": codec.loads(codec.dumps(d.corrective.scene)),
            "labels_moved_by_the_person": codec.loads(
                codec.dumps(
                    {
                        k: list(v)
                        for k, v in (d.corrective.output or {}).items()
                        if k in d.corrective.mask
                    }
                )
            ),
            "saved_rule": d.base["program"].get("summary", ""),
            "candidates": [
                {"id": k, "scope": c["selector"], "summary": c.get("summary", ""),
                 "earlier_examples_changed": len(c.get("conflicts", []))}
                for k, c in self._cands().items()
            ],  # fmt: skip
            "authorized_scope": (d.authorized or {}).get("selector"),
            "budget": {
                "attempts_left": self.max_attempts - self.attempts,
                "clarifications_left": self.config.max_clarifications - d.clarifications,
                "affected_review_left": int(not d.affected_used),
                "revision_preview_left": int(not d.revision_preview_used),
            },
            "options": self.options(),
            "history": self.history[-8:],
        }

    # ---- doing what B chose (no model call here; run() makes the call)
    def turn(self, choice: dict) -> str:
        oid = choice.get("choose")
        if oid not in {o["id"] for o in self.options()}:
            raise BadCall(f"{oid!r} is not one of the offered options")
        evs = self.log.events()
        d = derive_draft(evs)
        cands = self._cands()
        kind, _, rest = oid.partition(":")
        if kind == "propose_scope":
            self.attempts += 1
            self.cx._propose(
                RequestModelProposal(
                    _aid(evs, "RequestModelProposal"), "scope" if not d.rounds else "revision"
                )
            )
            n = len(self._cands())
            return f"{n} candidate revision(s) available" if n else "no usable candidate revision"
        if kind == "abstain":
            reason = choice.get("reason") or "chose to stop"
            self.log.append("Abstained", "system", {"action_id": f"b-{uuid.uuid4().hex[:8]}",
                            "reason": f"agent: {reason}"[:300]})  # fmt: skip
            return "abstained; the saved rule is unchanged"
        if kind == "ask_scope":
            self.cx._ask(scope_request(evs, d, [cands[i] for i in rest.split(",") if i]))
            return self._answer()
        if kind == "ask_choose":
            sid, ids = rest.split(":")
            groups = _groups([cands[i] for i in ids.split(",")], d.scenes[sid])
            alts = tuple((chr(65 + k), out) for k, (out, _) in enumerate(groups))
            aid = _aid(evs, "AskTeacher")
            self.cx._ask(AskTeacher(aid, ChooseOutput(f"q-{aid}", sid, d.scene_hashes[sid], alts)))
            return self._answer()
        sel = cands[rest]
        if kind == "affected":
            self.cx._ask(affected_request(evs, d, sel, self.config))
            return self._answer()
        if kind == "revision_preview":
            self.cx._ask(revision_request(evs, d, sel, self.config))
            return self._answer()
        if kind == "commit":
            self.cx._commit(commit_or_reason(evs, d, sel))
            return f"saved: {self.status()}"
        raise BadCall(f"unknown option {oid!r}")

    def _answer(self) -> str:
        last = next(
            (e for e in reversed(self.log.events()) if e.type in ("ResponseRecorded", "Errored")),
            None,
        )
        if last is None:
            return "no answer"
        if last.type == "Errored":
            return f"error: {last.payload.get('reason')}"
        r = last.payload["response"]
        return (
            f"the person answered {r['kind']}"
            + (f" {r['selected']}" if r.get("selected") else "")
            + (f" {r['per_item']}" if r.get("per_item") else "")
        )

    # ---- the loop
    def run(self) -> str:
        turn = -1
        while self.attempts < self.max_attempts:
            if self.settle():
                return self.status() or "error"
            turn += 1
            aid = f"cturn-{turn}"
            attempt = uuid.uuid4().hex
            try:
                self.ledger.reserve(attempt, aid, self.worst)
            except OverBudget as e:
                self.log.append("Abstained", "system", {"action_id": aid, "reason": f"budget: {e}"})
                break
            self.ledger.dispatched(attempt)
            self.attempts += 1
            record: dict[str, Any] = {"action_id": aid, "turn": turn}
            try:
                done, usage, cost = _call(
                    self.factory, self.prompt, ROLE, self._state(), ToolCall, self.max_tokens
                )
            except ModelFormatError as e:
                self.ledger.mark_unknown(attempt)
                record |= {"parse_failure": True, "result": f"not a valid choice: {str(e)[:200]}"}
            except Exception as e:  # provider failure: cost unknown, kept at worst case
                self.ledger.mark_unknown(attempt)
                kind = failure_kind(e)
                record |= {"provider_failure": kind, "result": f"provider failure ({kind})"}
                if kind not in TRANSIENT:
                    self.log.append("AgentTurn", "system", record)
                    self.log.append(
                        "Errored", "system", {"action_id": aid, "reason": f"provider: {kind}"}
                    )
                    break
            else:
                self.ledger.settle(attempt, cost)
                call: ToolCall = done.parsed
                choice = {
                    "choose": call.args.get("option"),
                    **{k: v for k, v in call.args.items() if k != "option"},
                }
                record |= {"choice": choice, "usage": usage}
                try:
                    record["result"] = self.turn(choice)
                except BadCall as e:
                    record |= {"parse_failure": True, "result": f"not a valid choice: {e}"}
            self.log.append("AgentTurn", "system", codec.loads(codec.dumps(record)))
            self.history.append(
                {k: record.get(k) for k in ("turn", "choice", "result") if k in record}
            )
        if not self.settle():
            self.log.append(
                "Abstained",
                "system",
                {
                    "action_id": "budget",
                    "reason": f"budget exhausted: {self.max_attempts} provider attempts",
                },
            )
        return self.status() or "error"


def run_b_correction(
    provider_factory: Callable[[], Any],
    store: Store,
    log: SessionLog,
    teacher: Teacher,
    ledger: Ledger,
    scope_proposer: ScopeProposer,
    worst_usd: Fraction,
    max_attempts: int = 4,
) -> str:
    return CorrectionAgentB(
        provider_factory, store, log, teacher, ledger, scope_proposer, worst_usd, max_attempts
    ).run()


def scripted_correction_policy(messages: list) -> dict:
    """The offline FIXTURE stand-in for B's correction choices (mock mode only; never a model result): the furthest
    step on offer, in the order commit > revision preview > affected review > ask scope > propose > abstain.
    """
    import json

    ids = [o["id"] for o in json.loads(messages[1].content)["options"]]
    for prefix in ("commit:", "revision_preview:", "affected:", "ask_scope", "propose_scope"):
        hit = next((i for i in ids if i.startswith(prefix)), None)
        if hit:
            return {"choose": hit}
    return {"choose": "abstain", "reason": "nothing left to try"}
