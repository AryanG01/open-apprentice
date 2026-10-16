"""System B (spec 4, 7): the same model acting freely, with the teacher request types as tools. B chooses its own
questions and its stopping point; only the SHARED commit checks apply (valid program, consistent with all active evidence,
>= 1 approved preview of its output, no unresolved rejection). Budgets are A's (spec 3.7), and every model turn is one
provider attempt reserved at worst case in the durable ledger. Everything B does is recorded in the session log, through
the same request validation and response handling as A."""

from __future__ import annotations

import json
import pathlib
import uuid
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable, Optional

from pydantic import BaseModel, model_validator

from open_apprentice.concepts.label_teaching import describe_compact
from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.concepts.rules import RuleError, validate_rule
from open_apprentice.learner import synthetic_render
from open_apprentice.providers.base import ModelFormatError
from open_apprentice.providers.teaching_adapter import _call
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger, OverBudget
from open_apprentice.teaching.constraints import derive
from open_apprentice.teaching.events import SessionLog
from open_apprentice.teaching.executor import TRANSIENT, Executor, failure_kind
from open_apprentice.teaching.probes import Probe, ProbeResult, probe_to_json
from open_apprentice.teaching.step import (
    AskTeacher,
    CommitVersion,
    PresentPreview,
    StepConfig,
    _filter,
    candidate_pool,
    run_output,
)
from open_apprentice.teaching.teacher import (
    ChooseOutput,
    ConfirmPreview,
    ProtocolError,
    RequestDemonstration,
    Teacher,
    response_from_json,
    validate_request,
)

PROMPTS = pathlib.Path(__file__).resolve().parents[3] / "prompts"
MAX_OBJECTS = 32
NODE_FIELDS = ("x", "y", "w", "h")
ROLE = "agent_b"


@dataclass(frozen=True)
class AgentBudgets:
    max_choose: int = 3
    max_demos: int = 1
    max_previews: int = 1
    max_preview_items: int = 3
    max_attempts: int = 8
    max_tokens: int = 6000


class ToolCall(BaseModel):
    model_config = {"extra": "forbid"}
    tool: str
    args: dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def _flat_args(cls, d: Any) -> Any:
        """Calibration (2026-10-16): the model often writes {"tool": ..., "rules_text": ...} without the `args` wrapper.
        Any other top-level key is read as an argument (`args` wins on a clash); unknown arguments are ignored.
        """
        if isinstance(d, dict) and set(d) - {"tool", "args"}:
            extra = {k: v for k, v in d.items() if k not in ("tool", "args")}
            args = d.get("args") if isinstance(d.get("args"), dict) else {}
            return {"tool": d.get("tool"), "args": {**extra, **args}}
        return d


class BadCall(Exception):
    """A tool call that cannot be read (unknown tool, missing or mistyped arguments): a parse failure."""


def build_prompt() -> str:
    """agent_b.md with the grammar documentation and examples taken verbatim from hypotheses_labels.md."""
    shared = (PROMPTS / "hypotheses_labels.md").read_text()
    grammar = shared[shared.index("THE EVIDENCE.") : shared.index("HOW TO CHOOSE DIFFERENT")]
    return (PROMPTS / "agent_b.md").read_text().replace("{{SHARED_GRAMMAR}}", grammar.strip())


class _NoProposer:
    def propose(self, *a: Any) -> Any:
        raise RuntimeError("system B proposes through its own tool calls")


def _parse(text: str) -> list:
    rule = parse_rule_text(text)
    validate_rule(rule)
    return rule


class AgentB:
    def __init__(
        self,
        provider_factory: Callable[[], Any],
        log: SessionLog,
        teacher: Teacher,
        ledger: Ledger,
        budgets: AgentBudgets,
        worst_usd: Fraction,
        probe_renderer: Callable[[Probe], ProbeResult] = synthetic_render,
        skill_id: str = "skill",
    ) -> None:
        self.factory, self.log, self.ledger, self.b, self.worst = (
            provider_factory,
            log,
            ledger,
            budgets,
            worst_usd,
        )
        self.ex = Executor(
            log.store,
            log,
            _NoProposer(),
            teacher,
            ledger,
            StepConfig(),
            worst_usd=worst_usd,
            skill_id=skill_id,
            probe_renderer=probe_renderer,
        )
        self.history: list[dict] = []
        self.prompt = build_prompt()

    # ---- state shown to the model
    def _programs(self) -> list[dict]:
        pool = candidate_pool(self.log.events())
        ev = derive(self.log.events())
        out = []
        for i, c in enumerate(pool, 1):
            kept, why = _filter([c], ev)
            out.append(
                {
                    "id": f"P{i}",
                    "hash": c["hash"],
                    "rule": c["rule"],
                    "summary": c["summary"],
                    "fits": bool(kept),
                    "problem": "; ".join(why)[:300] if why else "",
                }
            )
        return out

    def _requests(self, kind: str) -> int:
        return sum(
            1
            for e in self.log.events()
            if e.type == "RequestIssued" and e.payload["request"]["type"] == kind
        )

    def _state(self, turns_left: int) -> dict:
        ev = derive(self.log.events())
        docs = {
            sid: {"role": role, "scene": codec.loads(codec.dumps(ev.scenes[sid]))}
            for sid, role in sorted(ev.roles.items())
            if role != "demo"
        }
        return {
            "evidence": describe_compact(ev.positives),
            "documents": docs,
            "programs": [
                {k: p[k] for k in ("id", "summary", "fits", "problem")} for p in self._programs()
            ],
            "budget": {
                "turns_left": turns_left,
                "ask_choose_left": self.b.max_choose - self._requests("ChooseOutput"),
                "preview_left": self.b.max_previews - self._requests("ConfirmPreview"),
                "request_demo_left": self.b.max_demos - self._requests("RequestDemonstration"),
            },
            "history": self.history[-8:],
        }

    # ---- tools
    def _program(self, pid: Any) -> dict:
        progs = {p["id"]: p for p in self._programs()}
        if not isinstance(pid, str) or pid not in progs:
            raise BadCall(f"unknown program {pid!r}")
        return progs[pid]

    def _scene(self, sid: Any) -> tuple[dict, str]:
        ev = derive(self.log.events())
        if not isinstance(sid, str) or sid not in ev.scenes:
            raise BadCall(f"unknown document {sid!r}")
        return ev.scenes[sid], ev.scene_hashes[sid]

    def _answer(self, request_id: str) -> Optional[Any]:
        for e in self.log.events():
            if e.type == "ResponseRecorded":
                r = response_from_json(e.payload["response"])
                if r.request_id == request_id:
                    return r
        return None

    def _ask(self, aid: str, request: Any, preview_hash: Optional[str] = None) -> Optional[str]:
        try:
            validate_request(request, derive(self.log.events()).scene_hashes)
        except ProtocolError as e:
            return f"refused: {e}"
        if preview_hash is None:
            self.ex._ask(AskTeacher(aid, request))
        else:
            self.ex._ask(PresentPreview(aid, request, preview_hash))
        return None

    def t_propose(self, aid: str, args: dict) -> str:
        texts = args.get("rules_text")
        if not isinstance(texts, list) or not 1 <= len(texts) <= 4:
            raise BadCall("rules_text must be a list of 1-4 rules")
        cands, problems = [], []
        for t in texts:
            if not isinstance(t, str):
                raise BadCall("each rule must be a string")
            try:
                cands.append({"rule": _parse(t), "summary": t.splitlines()[0][:80], "text": t})
            except RuleError as e:
                problems.append(f"does not parse: {str(e)[:160]}")
        before = {p["hash"] for p in self._programs() if p["fits"]}
        self.log.append(
            "ModelProposalReturned",
            "model",
            # the turn's tokens are counted once, on its AgentTurn event
            {
                "action_id": aid,
                "candidates": cands,
                "malformed": len(problems),
                "usage": {"source": ROLE},
            },
        )
        known = {p["hash"]: p for p in self._programs()}
        again = [
            known[h]["id"]
            for h in dict.fromkeys(codec.digest(c["rule"]) for c in cands)
            if h in before
        ]
        lines = [
            f"{known[codec.digest(c['rule'])]['id']}: "
            + ("fits the evidence" if known[codec.digest(c["rule"])]["fits"] else "rejected -- ")
            + known[codec.digest(c["rule"])]["problem"]
            for c in cands
        ]
        if again:
            problems.append(
                f"{', '.join(again)} already proposed and still fits: proposing it again changes nothing -- "
                "ask about it, or preview it and then commit"
            )
        return "; ".join(lines + problems)

    def t_register_probe(self, aid: str, args: dict) -> str:
        scene, _ = self._scene(args.get("source"))
        edits = args.get("edits") or {}
        if not isinstance(edits, dict):
            raise BadCall("edits must map node ids to fields")
        objs = [dict(o) for o in scene["objects"]]
        by_id = {o["id"]: o for o in objs}
        changed: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        try:
            for cid, fields in sorted(edits.items()):
                o = by_id.get(cid)
                if o is None or o["kind"] != "node" or not isinstance(fields, dict):
                    return f"refused: {cid} is not a node of {args.get('source')}"
                if set(fields) - set(NODE_FIELDS):
                    return "refused: only x, y, w and h of nodes can change"
                for k, v in fields.items():
                    o[k] = Fraction(str(v))
                changed.append((cid, tuple((k, str(o[k])) for k in sorted(fields))))
            canvas = dict(scene["canvas"])
            if args.get("canvas_w") is not None:
                canvas["w"] = Fraction(str(args["canvas_w"]))
        except (ValueError, ZeroDivisionError):
            raise BadCall("edit values must be numbers")
        if not changed and canvas == scene["canvas"]:
            return "refused: the probe changes nothing"
        if len(objs) > MAX_OBJECTS or any(o["w"] <= 0 or o["h"] <= 0 for o in objs):
            return "refused: sizes must be positive and a document holds at most 32 objects"
        if any(
            o["x"] < 0
            or o["y"] < 0
            or o["x"] + o["w"] > canvas["w"]
            or o["y"] + o["h"] > canvas["h"]
            for o in objs
        ):
            return "refused: every object must stay inside the canvas"
        new = {"objects": objs, "canvas": canvas}
        n = sum(1 for e in self.log.events() if e.type == "ProbeRendered") + 1
        probe = Probe(
            f"p{n}",
            args["source"],
            "agent_edit",
            tuple(changed),
            str(canvas["w"]) if canvas != scene["canvas"] else None,
            new,
            sum(len(a) for _, a in changed) + (canvas != scene["canvas"]),
        )
        self.ex._issue(aid, "RenderProbe", {"probe": probe_to_json(probe)})
        self.ex._render_probe(aid, probe)
        ok = any(
            e.type == "ProbeRendered" and e.payload.get("action_id") == aid and e.payload["ok"]
            for e in self.log.events()
        )
        return (
            f"registered document {probe.probe_id}" if ok else "refused: the probe did not render"
        )

    def t_ask_choose(self, aid: str, args: dict) -> str:
        if self._requests("ChooseOutput") >= self.b.max_choose:
            return "refused: the ask_choose budget is used up"
        scene, h = self._scene(args.get("scene_id"))
        pids = args.get("programs")
        if not isinstance(pids, list) or not 2 <= len(pids) <= 4:
            raise BadCall("programs must list 2-4 program ids")
        progs = [self._program(p) for p in pids]
        outs = [run_output(p["rule"], scene) for p in progs]
        if any(o is None for o in outs):
            return "refused: a program fails on this document"
        alts = tuple((chr(65 + k), o) for k, o in enumerate(outs) if o is not None)
        req = ChooseOutput(f"q-{aid}", args["scene_id"], h, alts)
        refused = self._ask(aid, req)
        if refused:
            return refused
        r = self._answer(req.request_id)
        if r is None:
            return "no answer"
        if r.kind == "choose" and r.selected is not None:
            return f"the person chose the output of {pids[ord(r.selected) - 65]}"
        return f"the person answered {r.kind}"

    def t_preview(self, aid: str, args: dict) -> str:
        if self._requests("ConfirmPreview") >= self.b.max_previews:
            return "refused: the preview budget is used up"
        ids = args.get("doc_ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= self.b.max_preview_items:
            raise BadCall(f"doc_ids must list 1-{self.b.max_preview_items} documents")
        prog = self._program(args.get("program"))
        ev = derive(self.log.events())
        items = []
        for k, sid in enumerate(ids):
            scene, h = self._scene(sid)
            if ev.roles.get(sid) == "demo":
                return f"refused: {sid} is a demonstration"
            out = run_output(prog["rule"], scene)
            if out is None:
                return f"refused: the program fails on {sid}"
            items.append((f"i{k}", sid, h, out))
        req = ConfirmPreview(f"p-{aid}", "learning_preview", tuple(items))
        refused = self._ask(aid, req, prog["hash"])
        if refused:
            return refused
        r = self._answer(req.request_id)
        verdicts = dict(r.per_item) if r is not None else {}
        return "; ".join(f"{sid}: {verdicts.get(i, 'no answer')}" for i, sid, _, _ in items)

    def t_request_demo(self, aid: str, args: dict) -> str:
        if self._requests("RequestDemonstration") >= self.b.max_demos:
            return "refused: the request_demo budget is used up"
        _, h = self._scene(args.get("scene_id"))
        req = RequestDemonstration(f"d-{aid}", args["scene_id"], h)
        refused = self._ask(aid, req)
        if refused:
            return refused
        r = self._answer(req.request_id)
        return (
            "the person placed the labels (now in the evidence)" if r is not None else "no answer"
        )

    def t_commit(self, aid: str, args: dict) -> str:
        prog = self._program(args.get("program"))
        ev = derive(self.log.events())
        kept, why = _filter([prog], ev)
        if not kept:
            return "refused: " + "; ".join(why)[:300]
        approvals = [
            sid
            for sid, out in ev.preview_approved.items()
            if run_output(prog["rule"], ev.scenes[sid]) == out
        ]
        rejected = any(
            run_output(prog["rule"], ev.scenes[s]) in outs for s, outs in ev.rejected.items()
        )
        if not approvals:
            return "refused: no approved preview of this program's output"
        if rejected:
            return "refused: the person rejected an output of this program"
        claim = (
            f"consistent with all evidence; approved on {len(approvals)} previewed document(s); "
            "committed by the agent's own decision (no disagreement search)"
        )
        self.ex._perform(CommitVersion(aid, prog["hash"], prog["rule"], prog["summary"], claim))
        return "committed"

    def t_abstain(self, aid: str, args: dict) -> str:
        reason = args.get("reason")
        if not isinstance(reason, str):
            raise BadCall("abstain needs a reason")
        self.log.append(
            "Abstained", "system", {"action_id": aid, "reason": f"agent: {reason}"[:300]}
        )
        return "abstained"

    # ---- loop
    def status(self) -> Optional[str]:
        types = {e.type for e in self.log.events()}
        for t, s in (
            ("VersionStored", "committed"),
            ("Abstained", "abstained"),
            ("Errored", "error"),
        ):
            if t in types:
                return s
        return None

    def _turn(self, aid: str, call: ToolCall) -> str:
        tools = {
            "register_probe": self.t_register_probe,
            "ask_choose": self.t_ask_choose,
            "preview": self.t_preview,
            "request_demo": self.t_request_demo,
            "commit": self.t_commit,
            "abstain": self.t_abstain,
        }
        sub = f"{aid}-{call.tool}"
        if call.tool == "propose":
            return self.t_propose(sub, call.args)
        if call.tool not in tools:
            raise BadCall(f"unknown tool {call.tool!r}")
        return tools[call.tool](sub, call.args)

    def run(self) -> str:
        for turn in range(self.b.max_attempts):
            if self.status():
                break
            aid = f"turn-{turn}"
            self.ex._issue(aid, "AgentTurn")
            user = self._state(self.b.max_attempts - turn)
            attempt = uuid.uuid4().hex
            try:
                self.ledger.reserve(attempt, aid, self.worst)
            except OverBudget as e:
                self.log.append("Abstained", "system", {"action_id": aid, "reason": f"budget: {e}"})
                break
            self.ledger.dispatched(attempt)
            record: dict[str, Any] = {"action_id": aid, "turn": turn}
            try:
                done, usage, cost = _call(
                    self.factory, self.prompt, ROLE, user, ToolCall, self.b.max_tokens
                )
            except ModelFormatError as e:
                self.ledger.mark_unknown(attempt)
                record |= {
                    "parse_failure": True,
                    "result": f"not a valid tool call: {str(e)[:200]}",
                }
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
                record |= {"tool": call.tool, "args": call.args, "usage": usage}
                try:
                    record["result"] = self._turn(aid, call)
                except BadCall as e:
                    record |= {"parse_failure": True, "result": f"not a valid tool call: {e}"}
            self.log.append("AgentTurn", "system", codec.loads(codec.dumps(record)))
            self.history.append(
                {k: record.get(k) for k in ("turn", "tool", "args", "result") if k in record}
            )
        if not self.status():
            self.log.append(
                "Abstained",
                "system",
                {
                    "action_id": "budget",
                    "reason": f"budget exhausted: {self.b.max_attempts} provider attempts",
                },
            )
        return self.status() or "error"


def run_agent_b(
    provider_factory: Callable[[], Any],
    log: SessionLog,
    teacher: Teacher,
    ledger: Ledger,
    budgets: AgentBudgets,
    worst_usd: Fraction,
    probe_renderer: Callable[[Probe], ProbeResult] = synthetic_render,
) -> str:
    return AgentB(provider_factory, log, teacher, ledger, budgets, worst_usd, probe_renderer).run()


def scripted_policy(messages: list) -> dict:
    """The offline FIXTURE stand-in for B's model (mock mode only; never reported as a model result): propose the
    offline enumerator's rules, preview the first fitting one on up to three documents, commit it if approved, else
    abstain. Deterministic from the message alone."""
    from open_apprentice.concepts.label_enumerative import LabelEnumerator

    state = json.loads(messages[1].content)
    progs = state["programs"]
    fitting = [p for p in progs if p["fits"]]
    tools = [h.get("tool") for h in state["history"]]
    if not progs:
        cands, _, _ = LabelEnumerator().propose(
            {"teaching_evidence": state["evidence"]}, "initial", ()
        )
        if not cands:
            return {"tool": "abstain", "args": {"reason": "no template rule fits the evidence"}}
        return {"tool": "propose", "args": {"rules_text": [c["text"] for c in cands[:4]]}}
    if not fitting:
        return {"tool": "abstain", "args": {"reason": "no proposed rule fits the evidence"}}
    docs = [d for d, v in state["documents"].items() if v["role"] == "batch"][:3]
    if "preview" not in tools and docs and state["budget"]["preview_left"] > 0:
        return {"tool": "preview", "args": {"doc_ids": docs, "program": fitting[0]["id"]}}
    last = next((h for h in reversed(state["history"]) if h.get("tool") == "preview"), None)
    if last and "reject" not in str(last.get("result")) and "approve" in str(last.get("result")):
        return {"tool": "commit", "args": {"program": last["args"]["program"]}}
    return {"tool": "abstain", "args": {"reason": "no approved rule"}}
