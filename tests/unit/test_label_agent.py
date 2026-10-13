"""The same-model baseline loop with a SCRIPTED agent (MOCK, not model evidence): asking, exact commit feedback, attempt limits,
invalid asks, abstention and malformed replies."""

import json

from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.label_agent import MAX_COMMITS, run_agent
from open_apprentice.evaluation.label_episodes import agent_visible, build_manifest
from open_apprentice.providers.mock import MockProvider

RIGHT = (
    'for o in objects {\n if o.kind == "label" {\n  let a = object(o.attached)\n'
    "  move o to (a.x + a.w + 12, a.y + (a.h - o.h) / 2)\n }\n}"
)
BAD = 'for o in objects {\n if o.kind == "label" {\n  move o to (0, 0)\n }\n}'


def setup():
    ep = next(e for e in build_manifest("development") if e.kind == "ambiguous")
    v = agent_visible(ep)
    return ep, [(d["before"], d["after"]) for d in v["demonstrations"]], v["batch"]


def led():
    return Ledger(Limits(tokens=10**7, calls=1000))


async def drive(script):
    ep, demos, batch = setup()
    prov = MockProvider({"agent": [json.dumps(x) for x in script]})
    res = await run_agent(prov, led(), demos, batch, ep.teacher_answer)
    return res, prov


async def test_an_ask_returns_the_teacher_result_and_counts():
    res, prov = await drive(
        [{"action": "ask", "batch_index": 0}, {"action": "abstain", "reason": "x"}]
    )
    assert len(res.questions) == 1
    follow_up = json.loads(prov.calls[1][1][-1].content)
    assert follow_up["teacher_shows_for_batch_index"] == 0 and follow_up["asks_left"] == 2


async def test_a_repeated_or_out_of_range_ask_is_refused_without_a_teacher_answer():
    res, prov = await drive(
        [
            {"action": "ask", "batch_index": 0},
            {"action": "ask", "batch_index": 0},
            {"action": "ask", "batch_index": 99},
            {"action": "abstain", "reason": "x"},
        ]
    )
    assert len(res.questions) == 1
    assert "error" in json.loads(prov.calls[2][1][-1].content) and "error" in json.loads(
        prov.calls[3][1][-1].content
    )


async def test_a_wrong_commit_gets_exact_feedback_and_attempts_are_limited():
    res, prov = await drive([{"action": "commit", "rule_text": BAD}] * MAX_COMMITS)
    assert res.status == "abstained" and "commit attempts used up" in res.reason
    fb = json.loads(prov.calls[1][1][-1].content)["commit_rejected"]
    assert "evidence shows" in fb  # concrete numbers, not just 'wrong'


async def test_a_syntax_error_is_fed_back_not_fatal():
    res, prov = await drive(
        [
            {"action": "commit", "rule_text": "move nothing"},
            {"action": "abstain", "reason": "gave up"},
        ]
    )
    assert (
        "syntax" in json.loads(prov.calls[1][1][-1].content)["commit_rejected"]
        and res.reason == "gave up"
    )


async def test_a_fitting_commit_is_accepted_and_labelled_unverified():
    # find an episode whose demonstrations the generic right-of-anchor rule fits, so the commit gate passes
    from open_apprentice.concepts.hypotheses import Constraint, fits
    from open_apprentice.concepts.label_teaching import to_state
    from open_apprentice.concepts.rule_text import parse_rule_text

    rule = parse_rule_text(RIGHT)
    for ep in build_manifest("development"):
        if ep.kind in ("unambiguous", "ambiguous") and all(
            fits(rule, Constraint("positive", b, to_state(a)))[0] for b, a in ep.demos
        ):
            v = agent_visible(ep)
            prov = MockProvider({"agent": [json.dumps({"action": "commit", "rule_text": RIGHT})]})
            res = await run_agent(
                prov,
                led(),
                [(d["before"], d["after"]) for d in v["demonstrations"]],
                v["batch"],
                ep.teacher_answer,
            )
            assert res.status == "committed" and res.scope == "agent_unverified"
            return
    raise AssertionError("no development episode is fitted by the plain right-of-anchor rule")


async def test_malformed_replies_twice_in_a_row_stop_the_run_without_a_commit():
    res, _ = await drive(["not json", "still not json", "nope", "nope"])
    assert res.status == "abstained"
