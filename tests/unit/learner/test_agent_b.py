from fractions import Fraction as F
from functools import lru_cache

from open_apprentice.concepts.catalogue_programs import program_text
from open_apprentice.evaluation.battery_v2 import build_battery, learner_view
from open_apprentice.evaluation.teacher_sim import teacher_for
from open_apprentice.learner.agent_b import AgentBudgets, build_prompt, run_agent_b
from open_apprentice.providers.mock import MockProvider
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.events import SessionLog
from open_apprentice.teaching import codec
from open_apprentice.teaching.constraints import scene_from_payload


@lru_cache(maxsize=None)
def _dev():
    return tuple(build_battery("dev"))


def _clarify():
    return next(e for e in _dev() if e.stratum == "catalogue" and e.clarification_required)


def _text(ep):
    s = ep.spec.params[0]
    return program_text(s.primary, s.fallback, s.scope, int(s.gap))


def _start(tmp_path, ep):
    store = LocalStore(tmp_path)
    log = SessionLog(store, "learn")
    log.create(owner="t")
    view = learner_view(ep)
    demo_ids = {d["scene_id"] for d in view["demonstrations"]}
    for sid in [*sorted(demo_ids), *view["batch"]]:
        sc = scene_from_payload(view["scenes"][sid])
        log.append("SceneRegistered", "system", {"scene_id": sid, "scene_hash": codec.digest(sc),
                   "scene": codec.loads(codec.dumps(sc)), "role": "demo" if sid in demo_ids else "batch"})  # fmt: skip
    for d in view["demonstrations"]:
        out = {o["id"]: [o["x"], o["y"]] for o in d["after"]["objects"] if o["kind"] == "label"}
        log.append("DemonstrationRecorded", "human", {"scene_id": d["scene_id"], "output": out})
    return store, log


def _run(tmp_path, ep, replies):
    store, log = _start(tmp_path, ep)
    mock = MockProvider({"agent_b": list(replies)})
    status = run_agent_b(
        lambda: mock, log, teacher_for(ep), Ledger(store, F(0)), AgentBudgets(), F(0)
    )
    turns = [e.payload for e in log.events() if e.type == "AgentTurn"]
    return status, log, turns, mock


def test_prompt_shares_the_grammar_text_with_the_hypothesis_prompt():
    from pathlib import Path

    shared = Path("prompts/hypotheses_labels.md").read_text()
    start, end = shared.index("THE EVIDENCE."), shared.index("HOW TO CHOOSE DIFFERENT")
    assert shared[start:end].strip() in build_prompt()


def test_b_commits_an_approved_program_without_the_question_policy(tmp_path):
    ep = _clarify()
    replies = [
        {"tool": "propose", "args": {"rules_text": [_text(ep)]}},
        {"tool": "preview", "args": {"doc_ids": ["b0", "b1"], "program": "P1"}},
        {"tool": "commit", "args": {"program": "P1"}},
    ]
    status, log, turns, _ = _run(tmp_path, ep, replies)
    types = [e.type for e in log.events()]
    assert status == "committed", turns
    assert types.count("VersionStored") == 1
    asked = [e.payload["request"]["type"] for e in log.events() if e.type == "RequestIssued"]
    assert asked == ["ConfirmPreview"]  # no ChooseOutput: B decides its own questions


def test_a_commit_failing_the_shared_checks_is_refused_with_feedback(tmp_path):
    ep = _clarify()
    replies = [
        {"tool": "propose", "args": {"rules_text": [_text(ep)]}},
        {"tool": "commit", "args": {"program": "P1"}},
        {"tool": "abstain", "args": {"reason": "gave up"}},
    ]
    status, log, turns, _ = _run(tmp_path, ep, replies)
    assert status == "abstained"
    assert "refused" in turns[1]["result"] and "approved preview" in turns[1]["result"]
    assert "VersionStored" not in [e.type for e in log.events()]


def test_a_fourth_ask_is_refused(tmp_path):
    ep = _clarify()
    other = program_text("below", None, "all", 12)
    ask = {"tool": "ask_choose", "args": {"scene_id": "d0", "programs": ["P1", "P2"]}}
    replies = [{"tool": "propose", "args": {"rules_text": [_text(ep), other]}}, ask, ask, ask, ask]
    replies.append({"tool": "abstain", "args": {"reason": "done"}})
    status, log, turns, _ = _run(tmp_path, ep, replies)
    asked = [e for e in log.events() if e.type == "RequestIssued"]
    assert len(asked) == 3
    assert "budget" in turns[4]["result"]
    assert status == "abstained"


def test_malformed_tool_calls_are_parse_failures_not_crashes(tmp_path):
    ep = _clarify()
    replies = [
        "not json",
        "still not json",
        {"tool": "fly", "args": {}},
        {"tool": "abstain", "args": {"reason": "x"}},
    ]
    status, log, turns, _ = _run(tmp_path, ep, replies)
    assert status == "abstained"
    assert sum(1 for t in turns if t.get("parse_failure")) == 2


def test_the_attempt_budget_ends_the_run(tmp_path):
    ep = _clarify()
    replies = [{"tool": "propose", "args": {"rules_text": [_text(ep)]}}] * 12
    status, log, turns, _ = _run(tmp_path, ep, replies)
    assert status == "abstained" and len(turns) == 8
    assert "budget" in next(e.payload["reason"] for e in log.events() if e.type == "Abstained")
