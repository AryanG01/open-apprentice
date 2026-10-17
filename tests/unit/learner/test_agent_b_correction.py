from fractions import Fraction as F
from functools import lru_cache

from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.evaluation.battery_v2 import build_battery, learner_view
from open_apprentice.evaluation.labels import rule_for_spec
from open_apprentice.evaluation.teacher_sim import teacher_for
from open_apprentice.learner.agent_b_correction import CorrectionAgentB
from open_apprentice.providers.mock import MockProvider
from open_apprentice.skills.versions import SkillStore
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching import codec
from open_apprentice.teaching.accounting import Ledger
from open_apprentice.teaching.constraints import scene_from_payload
from open_apprentice.teaching.correction_executor import start_correction
from open_apprentice.teaching.step import run_output

WARN_BELOW = """for o in objects {{
  if o.kind == "label" {{
    let a = object(o.attached)
    if o.role == "warning" {{
      move o to (a.x + (a.w - o.w) / 2, a.y + a.h + {g})
    }} else {{
      move o to (a.x + a.w + {g}, a.y + (a.h - o.h) / 2)
    }}
  }}
}}"""


@lru_cache(maxsize=None)
def _dev():
    return tuple(build_battery("dev"))


def _ep(kind):
    return next(
        e
        for e in _dev()
        if e.stratum == "sequential"
        and e.correction["kind"] == kind
        and e.correction["template"] == "warn_below"
    )


class Scope:
    def __init__(self, cands):
        self.cands, self.calls = cands, 0

    def propose_scope(self, evidence, round_kind):
        self.calls += 1
        return list(self.cands), {"prompt_tokens": 1}, F(0)


def _start(tmp_path, ep):
    store = LocalStore(tmp_path)
    base = rule_for_spec(ep.spec.params[0])
    skills = SkillStore(store)
    v = skills.store_version("skill", {"skill_id": "skill", "program": {"rule": base, "summary": "right"},
                                       "evidence": [], "superseded": {}, "retention_report": {},
                                       "parent_version": None, "created_by_session": "t"})  # fmt: skip
    skills.activate("skill", v, None, "t", "t")
    view = learner_view(ep)
    c = view["correction"]
    scenes = {k: scene_from_payload(s) for k, s in view["scenes"].items()}
    produced = run_output(base, scenes["c0"])
    edit = {k: (codec.frac(x), codec.frac(y)) for k, (x, y) in c["corrected_output"].items()}
    log = start_correction(store, "c", "skill", "c0", scenes["c0"], {**produced, **edit}, c["mask"],
                           {k: s for k, s in scenes.items() if k != "c0"})  # fmt: skip
    return store, log


def _agent(tmp_path, ep, replies, cands, max_attempts=8):
    store, log = _start(tmp_path, ep)
    g = int(ep.spec.params[0].gap)
    scope = Scope(cands(g))
    mock = MockProvider({"agent_b_correction": list(replies)})
    a = CorrectionAgentB(lambda: mock, store, log, teacher_for(ep), Ledger(store, F(0)), scope, F(0),
                         max_attempts=max_attempts)  # fmt: skip
    return a, scope, log


def _right(g):
    return [
        {
            "rule": parse_rule_text(WARN_BELOW.format(g=g)),
            "selector": 'o.role == "warning"',
            "summary": "w",
        }
    ]


def test_b_revises_through_scope_and_revision_preview_then_commits(tmp_path):
    ep = _ep("compatible")
    replies = [{"choose": "propose_scope"}, {"choose": "ask_scope:S1"}, {"choose": "affected:S1"},
               {"choose": "revision_preview:S1"}, {"choose": "commit:S1"}]  # fmt: skip
    a, scope, log = _agent(tmp_path, ep, replies, _right)
    for r in list(replies):
        ids = {o["id"] for o in a.options()}
        if r["choose"] not in ids and r["choose"].startswith("affected"):
            continue  # no affected example for this episode: the option is simply not offered
        assert r["choose"] in ids, (r, ids)
        assert a.turn(r) not in (None,)
    assert a.status() == "activated", [e.type for e in log.events()]
    assert scope.calls == 1


def test_commit_is_never_offered_before_an_approved_revision_preview(tmp_path):
    ep = _ep("compatible")
    a, _, _ = _agent(tmp_path, ep, [], _right)
    a.turn({"choose": "propose_scope"})
    a.turn({"choose": "ask_scope:S1"})
    ids = {o["id"] for o in a.options()}
    assert not any(i.startswith("commit") for i in ids)
    assert any(i.startswith("revision_preview") or i.startswith("affected") for i in ids)


class NoneToScope:
    def __init__(self, inner):
        self.inner = inner

    def ask(self, req):
        from open_apprentice.teaching.teacher import ConfirmCorrectionScope, Response

        if isinstance(req, ConfirmCorrectionScope):
            return Response(req.request_id, "none", source="deterministic_simulator")
        return self.inner.ask(req)


def test_a_third_clarification_is_not_offered(tmp_path):
    ep = _ep("compatible")
    a, _, _ = _agent(tmp_path, ep, [], _right, max_attempts=12)
    a.cx.teacher = NoneToScope(a.cx.teacher)
    for _ in range(2):
        a.turn({"choose": "propose_scope"})
        a.turn({"choose": "ask_scope:S1"})  # the teacher answers none
    assert not any(o["id"].startswith("ask") for o in a.options())


def test_propose_scope_runs_the_shared_proposer_and_counts_as_an_attempt(tmp_path):
    ep = _ep("compatible")
    a, scope, _ = _agent(tmp_path, ep, [], _right)
    a.turn({"choose": "propose_scope"})
    assert (
        scope.calls == 1 and a.attempts == 1
    )  # turn() itself is not a model call; run() adds one per turn


def test_the_teachers_override_is_recorded_without_a_b_turn(tmp_path):
    ep = _ep("override")
    a, _, log = _agent(tmp_path, ep, [], lambda g: [])  # nothing explains a one-off nudge
    a.turn({"choose": "propose_scope"})
    a.turn({"choose": "ask_scope"})
    turns = sum(1 for e in log.events() if e.type == "AgentTurn")
    assert a.settle() == "override"
    assert sum(1 for e in log.events() if e.type == "AgentTurn") == turns


def test_the_loop_runs_scripted_choices_to_activation(tmp_path):
    ep = _ep("compatible")
    replies = [{"choose": "propose_scope"}, {"choose": "ask_scope:S1"}, {"choose": "revision_preview:S1"},
               {"choose": "commit:S1"}]  # fmt: skip
    a, _, log = _agent(tmp_path, ep, replies, _right, max_attempts=10)
    assert a.run() == "activated"


def test_the_scripted_fixture_policy_completes_a_correction_offline(tmp_path):
    from open_apprentice.learner.agent_b_correction import scripted_correction_policy

    ep = _ep("compatible")
    store, log = _start(tmp_path, ep)
    mock = MockProvider({}, functions={"agent_b_correction": scripted_correction_policy})
    a = CorrectionAgentB(lambda: mock, store, log, teacher_for(ep), Ledger(store, F(0)),
                         Scope(_right(int(ep.spec.params[0].gap))), F(0), max_attempts=8)  # fmt: skip
    assert a.run() == "activated"
