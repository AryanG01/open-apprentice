"""The counted correction turn in candidate generation: when NO candidate fits, the host sends the concrete numeric
discrepancy once. It is a shared mechanism (every model-based method), it is charged, and it never loops."""

import json
from fractions import Fraction as F


from open_apprentice.budget import Ledger, Limits
from open_apprentice.concepts.hypotheses import Constraint, generate_candidates
from open_apprentice.concepts.rules import evaluate_rule
from open_apprentice.providers.mock import MockProvider
from tests.fixtures_rules import CONST_MARGIN

CANVAS = {"w": F(800), "h": F(600)}
OBJS = [
    {"id": "card0", "x": F(100), "y": F(100), "w": F(150), "h": F(80)},
    {"id": "proto", "x": F(0), "y": F(0), "w": F(20), "h": F(20)},
]
SCENE = {"objects": OBJS, "canvas": CANVAS}
DEMO = Constraint(
    "positive", SCENE, evaluate_rule(CONST_MARGIN, OBJS, CANVAS), source="demonstration"
)  # badge inset 12
GOOD = "let m = 12\nclone proto as badge at (card0.x + card0.w - m - proto.w, card0.y + m)"
WRONG = "let m = 30\nclone proto as badge at (card0.x + card0.w - m - proto.w, card0.y + m)"
BROKEN = "let m = 12\nclone proto as badge at (card0.x + card0.w - m - proto.w card0.y + m)"


def reply(*texts):
    return {"candidates": [{"summary": f"c{i}", "rule_text": t} for i, t in enumerate(texts)]}


async def gen(script, **kw):
    prov, led = MockProvider({"hypotheses": script}), Ledger(Limits(tokens=200_000, calls=20))
    rep = await generate_candidates(
        prov, led, [DEMO], rnd=1, rejected_summaries=[], object_counts=[2], **kw
    )
    return rep, prov, led


async def test_no_candidate_fits_then_one_correction_turn_with_real_numbers_recovers():
    rep, prov, led = await gen([reply(WRONG), reply(GOOD)])
    assert (
        [c.summary for c in rep.accepted] == ["c0"]
        and rep.model_calls == 2
        and rep.usage["correction_turn"] is True
    )
    assert led.snapshot()["consumed"]["calls"] == 2  # the extra turn is CHARGED
    feedback = json.loads(prov.calls[1][1][-1].content)
    prob = feedback["your_candidates_were_checked"][0]["problem"]
    assert (
        "your rule creates a new object at (x=200, y=130" in prob
        and "but the evidence shows (x=218, y=112" in prob
    )  # concrete numbers, both sides
    assert [r["stage"] for r in rep.rejected] == ["initial"]


async def test_syntax_errors_are_fed_back_with_their_line_numbers():
    rep, prov, _ = await gen([reply(BROKEN), reply(GOOD)])
    fb = json.loads(prov.calls[1][1][-1].content)["your_candidates_were_checked"][0]["problem"]
    assert fb.startswith("syntax: line 2:") and rep.accepted


async def test_no_correction_turn_when_something_already_fits_or_when_disabled():
    rep, prov, _ = await gen([reply(WRONG, GOOD)])
    assert len(prov.calls) == 1 and rep.model_calls == 1 and len(rep.accepted) == 1
    rep2, prov2, _ = await gen([reply(WRONG)], correction_turn=False)
    assert len(prov2.calls) == 1 and rep2.accepted == []


async def test_correction_turn_happens_at_most_once_and_failures_are_kept_not_hidden():
    rep, prov, _ = await gen([reply(WRONG), reply(WRONG.replace("30", "31"))])
    assert (
        len(prov.calls) == 2
        and rep.accepted == []
        and [r["stage"] for r in rep.rejected] == ["initial", "after_correction"]
    )


def test_fit_messages_contain_numbers_for_moved_objects_too():
    from open_apprentice.concepts.hypotheses import fits
    from tests.fixtures_rules import gap_rule

    objs = [
        {"id": f"c{i}", "x": F(10 * i), "y": F(300), "w": F(w), "h": F(50)}
        for i, w in enumerate((100, 60))
    ]
    demo = Constraint(
        "positive",
        {"objects": objs, "canvas": CANVAS},
        evaluate_rule(gap_rule(24, 80, 120), objs, CANVAS),
        source="demonstration",
    )
    ok, why = fits(gap_rule(30, 80, 120), demo)
    assert (
        not ok and "objects[1] your rule gives (x=210" in why and "the evidence shows (x=204" in why
    )


async def test_a_malformed_candidate_is_rejected_individually_and_its_siblings_survive():
    """Live failure: ONE candidate with neither/both rule fields used to fail the whole reply (ModelFormatError)."""
    bad_reply = {
        "candidates": [
            {"summary": "no rule at all"},
            {
                "summary": "both",
                "rule": [{"op": "let", "name": "a", "value": 1}],
                "rule_text": "let a = 1",
            },
            {"summary": "good", "rule_text": GOOD},
            {"summary": "numbers", "rule": 5},
        ]
    }
    rep, prov, _ = await gen([bad_reply], correction_turn=False)
    assert [c.summary for c in rep.accepted] == ["good"] and len(prov.calls) == 1
    assert sum("give the rule as rule_text" in r["reason"] for r in rep.rejected) >= 2


async def test_rule_text_placed_in_the_rule_field_is_understood():
    rep, _, _ = await gen(
        [{"candidates": [{"summary": "text in rule", "rule": GOOD}]}], correction_turn=False
    )
    assert len(rep.accepted) == 1
