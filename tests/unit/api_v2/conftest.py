"""Unit fixtures for /api/v2: a Store in tmp_path, a fake renderer (no browser), the offline enumerator, and an app that
contains only the v2 router, so these tests never start the engine or the legacy lifespan."""

import base64
import dataclasses
from fractions import Fraction

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_apprentice.api.v2 import routes
from open_apprentice.api.v2.context import V2, LocalDispatcher
from open_apprentice.concepts.label_enumerative import LabelEnumerator
from open_apprentice.storage.store import LocalStore
from open_apprentice.teaching.accounting import Ledger
from tests.unit.drawio.fixtures import drawio, label, model, node
from tests.unit.drawio.test_publish import fake_render

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def render_with_png(page):
    return dataclasses.replace(fake_render(page), png=PNG_1X1)


@pytest.fixture
def v2(tmp_path):
    store = LocalStore(tmp_path)
    d = LocalDispatcher()
    yield V2(
        store=store,
        render=render_with_png,
        proposer=LabelEnumerator(),
        scope_proposer=LabelEnumerator(),
        model="Fixture",
        live_available=lambda: False,
        ledger=Ledger(store, Fraction(0)),
        worst_usd=Fraction(0),
        dispatcher=d,
        secret=b"t" * 32,
    )
    d.close()


@pytest.fixture
def client(v2):
    app = FastAPI()
    routes.install(app)
    app.state.v2 = v2
    with TestClient(app) as c:
        yield c


@pytest.fixture
def doc_bytes():
    return drawio(
        model(
            [
                node("n1", 40, 40, 100, 50),
                node("n2", 300, 40, 100, 50),
                label("l1", 50, 100),
                label("l2", 310, 100),
            ]
        )
    )


@pytest.fixture
def batch_bytes():
    return drawio(
        model(
            [
                node("m1", 60, 200, 120, 60),
                node("m2", 330, 120, 80, 40),
                label("k1", 70, 280),
                label("k2", 340, 200),
            ]
        )
    )


OCTET = {"content-type": "application/octet-stream"}


def upload(client, raw, name="d.drawio"):
    return client.post(f"/api/v2/documents?name={name}", content=raw, headers=OCTET)


def import_and_confirm(client, v2, raw, name="d.drawio"):
    doc = upload(client, raw, name).json()
    v2.dispatcher.drain()
    pid = doc["pages"][0]["page_id"]
    mh = client.post(
        f"/api/v2/documents/{doc['doc_id']}/mapping",
        json={"page_id": pid, "labels": {}, "confirm": True},
    ).json()["mapping_hash"]
    return {"doc_id": doc["doc_id"], "page_id": pid, "mapping_hash": mh}


RIGHT_12 = {
    "l1": ["152", "58"],
    "l2": ["412", "58"],
}  # fake render: label box = geometry + (2, 3), 30x14


def start_session(client, v2, demo_raw, batch_raw, boxes=RIGHT_12, key="k1"):
    ref = import_and_confirm(client, v2, demo_raw)
    bref = import_and_confirm(client, v2, batch_raw, "b.drawio")
    sh = client.get(f"/api/v2/documents/{ref['doc_id']}").json()["pages"][0]["scene_hash"]
    body = {
        "documents": [ref, bref],
        "demonstrations": [{"document_ref": 0, "before_scene_hash": sh, "boxes": boxes}],
        "live": False,
        "idempotency_key": key,
    }
    sid = client.post("/api/v2/sessions", json=body).json()["session_id"]
    v2.dispatcher.drain()
    return sid


@pytest.fixture
def two_docs_session(client, v2, doc_bytes, batch_bytes):
    sid = start_session(client, v2, doc_bytes, batch_bytes)
    s = client.get(f"/api/v2/sessions/{sid}").json()
    assert s["outstanding"], s
    return sid, s


def answer_until_done(client, v2, sid, rounds=8):
    s = client.get(f"/api/v2/sessions/{sid}").json()
    for _ in range(rounds):
        if s["outstanding"] is None:
            break
        req = s["outstanding"]
        body = {
            "request_id": req["request_id"],
            "intent_revision": req["intent_revision"],
            **req["approve_all_answer"],
        }
        client.post(f"/api/v2/sessions/{sid}/responses", json=body)
        v2.dispatcher.drain()
        s = client.get(f"/api/v2/sessions/{sid}").json()
    return s


@pytest.fixture
def committed_skill(client, v2, doc_bytes, batch_bytes):
    s = answer_until_done(
        client, v2, start_session(client, v2, doc_bytes, batch_bytes, key="commit")
    )
    assert s["state"] == "committed", s
    return s["result"]["skill_id"]


@pytest.fixture
def fresh_bytes():
    return drawio(model([node("p1", 100, 150, 90, 40), label("q1", 110, 220)]))


@pytest.fixture
def crowded_bytes():
    # a node sits exactly where "right of the node, gap 12" puts the label
    return drawio(
        model([node("n1", 40, 40, 100, 50), node("x", 150, 50, 40, 30), label("l1", 50, 100)])
    )
