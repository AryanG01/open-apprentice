"""Generated probes against the real engine: two rules that agree on every registered document are told apart by a
probe document that the locked engine renders and measures before the question is shown."""

import time
from fractions import Fraction as F

import pytest
from fastapi.testclient import TestClient

from open_apprentice.concepts.rule_text import parse_rule_text
from open_apprentice.teaching.events import SessionLog

D1 = "tests/fixtures/drawio_corpus/dev/d1.drawio"
OCTET = {"content-type": "application/octet-stream"}
HALF_WIDTH = parse_rule_text(
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n    move o to (a.x + (a.w - o.w) / 2, a.y + a.h + 8)\n  }\n}'
)
FIXED_60 = parse_rule_text(
    'for o in objects {\n  if o.kind == "label" {\n    let a = object(o.attached)\n    move o to (a.x + 60 - o.w / 2, a.y + a.h + 8)\n  }\n}'
)


class TwoRules:
    def propose(self, evidence_json, round_kind, feedback):
        if round_kind != "initial":
            return [], {}, F(0)
        return (
            [
                {"rule": HALF_WIDTH, "summary": "centred", "text": ""},
                {"rule": FIXED_60, "summary": "x + 60", "text": ""},
            ],
            {},
            F(0),
        )


@pytest.fixture
def api(engine_url, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_URL", engine_url)
    monkeypatch.setenv("EVALUATOR_TOKEN", "e2e-token")
    monkeypatch.setenv("OA_STORE_DIR", str(tmp_path / "store"))
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        c.app.state.v2.proposer = TwoRules()
        yield c


def imported(c, name):
    doc = c.post(
        f"/api/v2/documents?name={name}", content=open(D1, "rb").read(), headers=OCTET
    ).json()
    for _ in range(300):
        d = c.get(f"/api/v2/documents/{doc['doc_id']}").json()
        if d["render"] != "pending":
            break
        time.sleep(0.1)
    p = d["pages"][0]
    m = c.post(
        f"/api/v2/documents/{doc['doc_id']}/mapping",
        json={"page_id": p["page_id"], "labels": {}, "confirm": True},
    ).json()
    return {"doc_id": doc["doc_id"], "page_id": p["page_id"], "mapping_hash": m["mapping_hash"]}


def settled(c, sid):
    for _ in range(600):
        s = c.get(f"/api/v2/sessions/{sid}").json()
        if s["state"] not in ("teaching", "waiting_for_model"):
            return s
        time.sleep(0.1)
    raise AssertionError(s)


def test_probe_rendered_by_the_engine_separates_two_rules(api):
    c = api
    demo, batch = imported(c, "a.drawio"), imported(
        c, "b.drawio"
    )  # two copies of d1: all nodes 120 wide
    page = c.get(f"/api/v2/documents/{demo['doc_id']}").json()["pages"][0]
    sc = c.get(
        f"/api/v2/documents/{demo['doc_id']}/pages/{demo['page_id']}/scene",
        params={"mapping_hash": demo["mapping_hash"]},
    ).json()
    objs = {o["id"]: o for o in sc["objects"]}
    boxes = {}
    for lid, m in page["mapping"]["labels"].items():
        a, o = objs[m["node_id"]], objs[lid]
        boxes[lid] = [str(F(a["x"]) + (F(a["w"]) - F(o["w"])) / 2), str(F(a["y"]) + F(a["h"]) + 8)]
    body = {"documents": [demo, batch], "demonstrations": [{"document_ref": 0, "before_scene_hash": page["scene_hash"], "boxes": boxes}],
            "live": False, "idempotency_key": "probe"}  # fmt: skip
    sid = c.post("/api/v2/sessions", json=body).json()["session_id"]
    s = settled(c, sid)
    q = s["outstanding"]
    assert q and q["request"]["type"] == "ChooseOutput", s
    probe_doc = q["request"]["scene_id"].split(":")[0]
    assert (
        probe_doc not in (demo["doc_id"], batch["doc_id"])
        and c.get(f"/api/v2/documents/{probe_doc}").json()["probe_of"]
    )
    evs = SessionLog(c.app.state.v2.store, sid).events()
    assert any(e.type == "ProbeRendered" and e.payload["ok"] for e in evs)
    png = c.get(f"/api/v2/sessions/{sid}/requests/{q['request_id']}/items/{q['item_ids'][0]}.png")
    assert png.status_code == 200 and png.content[1:4] == b"PNG"
    for _ in range(8):
        if s["outstanding"] is None:
            break
        q = s["outstanding"]
        c.post(
            f"/api/v2/sessions/{sid}/responses",
            json={
                "request_id": q["request_id"],
                "intent_revision": q["intent_revision"],
                **q["approve_all_answer"],
            },
        )
        time.sleep(0.2)
        s = settled(c, sid)
    assert s["state"] == "committed", s
