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
