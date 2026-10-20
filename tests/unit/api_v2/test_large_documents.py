"""Large diagrams: a learned skill applies to pages far beyond the teaching size; teaching itself stays on small pages."""

from open_apprentice.drawio.classify import classify
from open_apprentice.drawio.parse import load_drawio
from tests.unit.api_v2.conftest import import_and_confirm
from tests.unit.drawio.fixtures import drawio, label, model, node


def big(n: int = 60) -> bytes:
    cells = []
    for k in range(n):
        x, y = 40 + (k % 10) * 160, 40 + (k // 10) * 120
        cells += [node(f"b{k}", x, y, 100, 40), label(f"n{k}", x + 3, y + 46)]
    return drawio(model(cells, w=1700, h=40 + (n // 10 + 1) * 120))


def test_a_page_with_120_objects_imports():
    c = classify(load_drawio(big()).pages[0])
    assert len(c.movable) == 60 and len(c.fixed) == 60


def test_a_learned_skill_applies_to_a_large_page(client, v2, committed_skill):
    ref = import_and_confirm(client, v2, big(), "big.drawio")
    r = client.post(
        f"/api/v2/skills/{committed_skill}/versions/1/apply",
        json={"documents": [ref], "idempotency_key": "big"},
    )
    v2.dispatcher.drain()
    res = client.get(f"/api/v2/runs/{r.json()['run_id']}").json()["results"]
    assert next(iter(res.values()))["status"] in ("published", "blocked", "unchanged"), res


def test_teaching_refuses_a_large_page_with_a_clear_reason(client, v2, doc_bytes):
    ref = import_and_confirm(client, v2, big(), "big.drawio")
    small = import_and_confirm(client, v2, doc_bytes, "small.drawio")
    sh = client.get(f"/api/v2/documents/{small['doc_id']}").json()["pages"][0]["scene_hash"]
    r = client.post(
        "/api/v2/sessions",
        json={
            "documents": [small, ref],
            "live": False,
            "idempotency_key": "big-teach",
            "demonstrations": [
                {"document_ref": 0, "before_scene_hash": sh, "boxes": {"l1": ["152", "58"]}}
            ],
        },
    )
    assert r.status_code == 409 and "teach" in r.json()["error"]["message"].lower(), r.text
