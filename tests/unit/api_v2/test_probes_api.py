import dataclasses
from fractions import Fraction as F

from open_apprentice.concepts.rule_text import parse_rule_text
from tests.unit.api_v2.conftest import start_session
from tests.unit.drawio.fixtures import drawio, label, model, node

RIGHT = parse_rule_text(
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n    move o to (a.x + a.w + 12, a.y + (a.h - o.h) / 2)\n  }\n}'
)
PLUS112 = parse_rule_text(
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n    move o to (a.x + 112, a.y + (a.h - o.h) / 2)\n  }\n}'
)


class TwoRules:
    """Two rules that agree while every node is 100 wide: only a probe that resizes a node can tell them apart."""

    def propose(self, evidence_json, round_kind, feedback):
        if round_kind != "initial":
            return [], {}, F(0)
        return (
            [
                {"rule": RIGHT, "summary": "right", "text": ""},
                {"rule": PLUS112, "summary": "x + 112", "text": ""},
            ],
            {},
            F(0),
        )


# a batch document whose nodes are also 100 wide
BATCH = drawio(
    model(
        [
            node("m1", 60, 200, 100, 60),
            node("m2", 330, 120, 100, 40),
            label("k1", 70, 280),
            label("k2", 340, 200),
        ]
    )
)


def test_probe_document_is_asked_about_and_owned(client, v2, doc_bytes):
    v2.proposer = TwoRules()
    sid = start_session(client, v2, doc_bytes, BATCH, key="probe")
    s = client.get(f"/api/v2/sessions/{sid}").json()
    q = s["outstanding"]
    assert q and q["request"]["type"] == "ChooseOutput", s
    probe_doc = q["request"]["scene_id"].split(":")[0]
    assert client.get(f"/api/v2/documents/{probe_doc}").json()["probe_of"]["sid"] == sid
    item = f"/api/v2/sessions/{sid}/requests/{q['request_id']}/items/{q['item_ids'][0]}.png"
    assert client.get(item).status_code == 200
    client.cookies.clear()  # another owner
    assert client.get(f"/api/v2/documents/{probe_doc}").status_code == 404
    assert client.get(item).status_code == 404


def test_a_probe_whose_render_differs_is_never_shown(client, v2, doc_bytes):
    v2.proposer = TwoRules()
    real = v2.render
    renders = {"n": 0}

    def off_by_three(page):
        r = real(page)
        renders["n"] += 1
        if renders["n"] <= 2:  # the two imported documents render honestly
            return r
        nodes = {k: (dataclasses.replace(b, x=b.x + 3), e, st) for k, (b, e, st) in r.nodes.items()}
        return dataclasses.replace(r, nodes=nodes)

    v2.render = off_by_three
    sid = start_session(client, v2, doc_bytes, BATCH, key="mismatch")
    s = client.get(f"/api/v2/sessions/{sid}").json()
    q = s["outstanding"]
    assert not (
        q and q["request"]["type"] == "ChooseOutput"
    ), s  # no question on a probe that did not render as selected
    from open_apprentice.teaching.events import SessionLog

    failed = [e.payload for e in SessionLog(v2.store, sid).events() if e.type == "ProbeRendered"]
    assert failed and not any(f["ok"] for f in failed) and "differs" in failed[0]["reason"]
