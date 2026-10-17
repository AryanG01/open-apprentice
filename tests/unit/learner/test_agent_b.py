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


def test_tool_arguments_given_at_the_top_level_are_accepted(tmp_path):
    ep = _clarify()
    replies = [
        {"tool": "propose", "rules_text": [_text(ep)]},  # args flattened, as the live model did
        {"tool": "abstain", "reason": "stop", "turn": 1},  # plus a stray key
    ]
    status, log, turns, _ = _run(tmp_path, ep, replies)
    assert status == "abstained"
    assert not any(t.get("parse_failure") for t in turns)
    assert turns[0]["result"].startswith("P1: fits")


def test_re_proposing_a_fitting_program_points_to_preview(tmp_path):
    ep = _clarify()
    p = {"tool": "propose", "args": {"rules_text": [_text(ep)]}}
    status, log, turns, _ = _run(tmp_path, ep, [p, p, {"tool": "abstain", "args": {"reason": "x"}}])
    assert "already" in turns[1]["result"] and "preview" in turns[1]["result"]


def test_prompt_states_the_preview_then_commit_path_and_the_boolean_words():
    text = build_prompt()
    assert "preview" in text and "then commit" in text
    assert "`and`, `or`, `not`" in text and "&&" in text


def _options(log, store, ep, mock_replies=()):
    from open_apprentice.learner.agent_b import AgentB

    b = AgentB(lambda: MockProvider({"agent_b": list(mock_replies)}), log, teacher_for(ep),
               Ledger(store, F(0)), AgentBudgets(), F(0))  # fmt: skip
    return b, {o["id"] for o in b.options()}


def test_options_offer_preview_then_commit_only_when_commit_would_pass(tmp_path):
    ep = _clarify()
    replies = [
        {"choose": "propose", "rules_text": [_text(ep)]},
        {"choose": "preview:P1"},
        {"choose": "commit:P1"},
    ]
    status, log, turns, _ = _run(tmp_path, ep, replies)
    assert status == "committed", turns
    assert not any(t.get("parse_failure") for t in turns)


def test_commit_is_not_offered_before_an_approved_preview(tmp_path):
    ep = _clarify()
    store, log = _start(tmp_path, ep)
    b, ids = _options(log, store, ep)
    assert ids == {"propose", "abstain", "demo:b0"}
    b.t_propose("x", {"rules_text": [_text(ep)]})
    ids = {o["id"] for o in b.options()}
    assert "preview:P1" in ids and not any(i.startswith("commit") for i in ids)


def test_an_ask_option_names_programs_whose_outputs_are_separated(tmp_path):
    ep = _clarify()
    store, log = _start(tmp_path, ep)
    b, _ = _options(log, store, ep)
    demos = list(zip(ep.demo_scenes, ep.demo_outputs))
    from open_apprentice.evaluation.label_episodes import consistent_classes

    a, c = [v[0] for v in consistent_classes(demos).values()][:2]
    texts = [program_text(s.primary, s.fallback, s.scope, int(s.gap)) for s in (a, c)]
    b.t_propose("x", {"rules_text": texts})
    asks = [o for o in b.options() if o["tool"] == "ask_choose"]
    assert asks and all(o["args"]["programs"] == ["P1", "P2"] for o in asks)


def test_an_unknown_option_is_a_parse_failure(tmp_path):
    ep = _clarify()
    status, log, turns, _ = _run(
        tmp_path, ep, [{"choose": "commit:P9"}, {"choose": "abstain", "reason": "x"}]
    )
    assert turns[0]["parse_failure"] and status == "abstained"


class _CountingProposer:
    def __init__(self, texts):
        self.texts, self.calls = texts, []

    def propose(self, evidence_json, round_kind, feedback):
        from open_apprentice.concepts.rule_text import parse_rule_text

        self.calls.append((round_kind, len(evidence_json["teaching_evidence"]), tuple(feedback)))
        return (
            [{"rule": parse_rule_text(t), "summary": "s", "text": t} for t in self.texts],
            {"prompt_tokens": 7},
            F(0),
        )


def _run_with(tmp_path, ep, replies, proposer, budgets=None):
    store, log = _start(tmp_path, ep)
    mock = MockProvider({"agent_b": list(replies)})
    status = run_agent_b(lambda: mock, log, teacher_for(ep), Ledger(store, F(0)), budgets or AgentBudgets(), F(0),
                         proposer=proposer)  # fmt: skip
    return status, log, [e.payload for e in log.events() if e.type == "AgentTurn"]


def test_choosing_propose_without_rules_runs_the_shared_proposal_call(tmp_path):
    ep = _clarify()
    prop = _CountingProposer([_text(ep)])
    replies = [{"choose": "propose"}, {"choose": "preview:P1"}, {"choose": "commit:P1"}]
    status, log, turns = _run_with(tmp_path, ep, replies, prop)
    assert status == "committed" and prop.calls == [("initial", len(ep.demo_scenes), ())]
    assert turns[0]["result"].startswith("P1: fits")


def test_proposal_calls_count_against_the_attempt_budget(tmp_path):
    ep = _clarify()
    prop = _CountingProposer([_text(ep)])
    status, log, turns = _run_with(tmp_path, ep, [{"choose": "propose"}] * 10, prop)
    assert (
        status == "abstained" and len(turns) == 4 and len(prop.calls) == 4
    )  # 4 turns x 2 calls = 8 attempts
    assert [c[0] for c in prop.calls] == ["initial", "contrastive", "contrastive", "contrastive"]
