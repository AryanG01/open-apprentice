"""One real-engine flow over /api/v2: import → map → teach → answer → commit → apply → export (corpus files, offline learner)."""

import time
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient

from open_apprentice.drawio.parse import load_drawio

CORPUS = "tests/fixtures/drawio_corpus/dev"
OCTET = {"content-type": "application/octet-stream"}


@pytest.fixture
def api(engine_url, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_URL", engine_url)
    monkeypatch.setenv("EVALUATOR_TOKEN", "e2e-token")
    monkeypatch.setenv("OA_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.delenv("DEMO_MODEL_ENABLED", raising=False)
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        yield c


def imported(c, name):
    doc = c.post(
        f"/api/v2/documents?name={name}",
        content=open(f"{CORPUS}/{name}", "rb").read(),
        headers=OCTET,
    ).json()
    for _ in range(300):
        d = c.get(f"/api/v2/documents/{doc['doc_id']}").json()
        if d["render"] != "pending":
            break
        time.sleep(0.1)
    assert d["render"] == "done", d
    page = d["pages"][0]
    m = c.post(
        f"/api/v2/documents/{doc['doc_id']}/mapping",
        json={"page_id": page["page_id"], "labels": {}, "confirm": True},
    ).json()
    d = c.get(f"/api/v2/documents/{doc['doc_id']}").json()
    return {
        "doc_id": doc["doc_id"],
        "page_id": page["page_id"],
        "mapping_hash": m["mapping_hash"],
    }, d["pages"][0]


def wait(c, url, done, timeout=60):
    for _ in range(timeout * 10):
        s = c.get(url).json()
        if done(s):
            return s
        time.sleep(0.1)
    raise AssertionError(f"timed out: {s}")


def test_real_engine_teach_apply_export(api):
    c = api
    demo, page = imported(c, "d1.drawio")
    batch, _ = imported(c, "d2.drawio")
    target, _ = imported(c, "d3.drawio")
    # the demonstration: every mapped label centred below its node, gap 8 (right of the node runs off these pages)
    draft = c.post(
        f"/api/v2/documents/{demo['doc_id']}/draft",
        json={"page_id": demo["page_id"], "mapping_hash": demo["mapping_hash"], "boxes": {}},
    ).json()
    labels = page["mapping"]["labels"]
    assert draft["boxes"]  # the draft render measured every label
    from open_apprentice.api.v2 import identity, service

    v2 = c.app.state.v2
    owner = identity.verify(c.cookies.get("oa_owner"), v2.secret)
    _, _, _, scene = service.page_scene(
        v2, owner, demo["doc_id"], demo["page_id"], demo["mapping_hash"]
    )
    objs = {o["id"]: o for o in scene.scene["objects"]}
    boxes = {}
    for lid, m in labels.items():
        a, o = objs[m["node_id"]], objs[lid]
        boxes[lid] = [str(a["x"] + (a["w"] - o["w"]) / 2), str(a["y"] + a["h"] + 8)]
    body = {"documents": [demo, batch], "demonstrations": [{"document_ref": 0, "before_scene_hash": page["scene_hash"], "boxes": boxes}],
            "live": False, "idempotency_key": "real"}  # fmt: skip
    r = c.post("/api/v2/sessions", json=body)
    assert r.status_code == 202, r.text
    sid = r.json()["session_id"]
    s = wait(
        c, f"/api/v2/sessions/{sid}", lambda s: s["state"] not in ("teaching", "waiting_for_model")
    )
    for _ in range(10):
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
        s = wait(
            c,
            f"/api/v2/sessions/{sid}",
            lambda x, rev=s["manifest_revision"]: x["manifest_revision"] > rev
            and (
                x["outstanding"] is not None or x["state"] in ("committed", "failed", "cancelled")
            ),
        )
    assert s["state"] == "committed", s
    skill = s["result"]["skill_id"]
    run = c.post(
        f"/api/v2/skills/{skill}/versions/1/apply",
        json={"documents": [batch, target], "idempotency_key": "real"},
    ).json()
    run = wait(c, f"/api/v2/runs/{run['run_id']}", lambda x: x["status"] != "running")
    # d2's outputs were approved in the preview, so they must publish through every check on the real engine
    res = run["results"][f"{batch['doc_id']}:{batch['page_id']}"]
    assert res["status"] == "published", res
    q = {"doc_id": batch["doc_id"], "page_id": batch["page_id"]}
    out = c.get(f"/api/v2/runs/{run['run_id']}/export", params={**q, "format": "drawio"})
    assert out.status_code == 200 and load_drawio(out.content).pages
    rec = c.get(f"/api/v2/runs/{run['run_id']}/export", params={**q, "format": "receipt"}).json()
    assert rec["conformance"]["ok"] and rec["preservation"]["ok"] and rec["layout"]["ok"]
    svg = c.get(f"/api/v2/runs/{run['run_id']}/export", params={**q, "format": "svg"})
    assert svg.status_code == 200 and b"<svg" in svg.content[:500]
    # d3: published, or blocked with its reasons (e.g. an overlap the rule would create)
    other = run["results"][f"{target['doc_id']}:{target['page_id']}"]
    assert other["status"] in ("published", "blocked", "unchanged")
    assert other["status"] != "blocked" or other["reasons"]
    assert Fraction(0) == Fraction(s["spend"]["recorded"])  # offline: nothing spent
