"""Interactive demo end to end on the REAL engines (opt-in: OA_ENGINE_TESTS=1)."""

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import TOKEN


@pytest.fixture()
def client(engine_url, monkeypatch):
    monkeypatch.setenv("ENGINE_URL", engine_url)
    monkeypatch.setenv("EVALUATOR_TOKEN", TOKEN)
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        yield c


def _teach(client):
    st = client.post("/api/teach").json()
    for _ in range(3):
        if st["state"] != "AWAITING_USER":
            break
        q = st["question"]
        st = client.post(
            f"/api/teach/{st['id']}/answer",
            json={
                "query_id": q["query_id"],
                "answer": q["options"][0]["id"],
                "candidate_set_hash": q["candidate_set_hash"],
            },
        ).json()
    assert st["state"] == "INTENT_READY", st
    return st["id"], st


def test_teach_reuse_on_both_backends_then_tool_change_then_binding_only_repair(client):
    sid, st = _teach(client)
    sealed = st["concept"]["sealed_hash"]

    for backend in ("konva", "fabric"):
        r = client.post(f"/api/teach/{sid}/run", json={"width": 300, "backend": backend}).json()
        assert r["verifier_passed"] and r["native_passed"], (backend, r["checks"])
        assert (
            r["binding"]["origin"] == "fixture"
            and r["concept_hash"] == sealed
            and r["binding"]["concept_hash"] == sealed
        )

    bad = client.post(
        f"/api/teach/{sid}/run", json={"width": 300, "backend": "fabric", "tool_change": True}
    ).json()
    assert not bad["native_passed"] and not bad["verifier_passed"] and bad["can_repair"] is True
    assert bad["native_diffs"], "the mismatch must come with the observed numbers"

    fix = client.post(f"/api/teach/{sid}/repair").json()
    assert fix["status"] == "validated" and fix["rule_unchanged"] is True
    assert fix["concept_hash_before"] == fix["concept_hash_after"] == sealed
    assert (
        fix["attempts"][0]["failed_stage"] == "retained_in_original_env"
    )  # the hard-coded offset is rejected
    assert [v["version"] for v in fix["versions"]] == [1, 2] and fix["versions"][1]["active"]

    for tool_change in (True, False):  # repaired binding works in BOTH environments
        ok = client.post(
            f"/api/teach/{sid}/run",
            json={"width": 220, "backend": "fabric", "tool_change": tool_change},
        ).json()
        assert ok["verifier_passed"], (tool_change, ok["checks"])
    assert client.post(f"/api/teach/{sid}/repair").status_code == 409  # nothing left to repair


def test_export_svg_matches_engine_geometry_and_carries_provenance_and_the_evidence_package_rechecks(
    client,
):
    import xml.etree.ElementTree as ET

    sid, st = _teach(client)
    assert client.get(f"/api/teach/{sid}/export.svg").status_code == 409  # nothing executed yet
    run = client.post(f"/api/teach/{sid}/run", json={"width": 260, "backend": "fabric"}).json()
    svg = client.get(f"/api/teach/{sid}/export.svg")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml")
    ns = {"s": "http://www.w3.org/2000/svg", "oa": "https://open-apprentice.invalid/ns"}
    root = ET.fromstring(svg.content)
    rects = {r.get("id"): r for r in root.iterfind(".//s:rect", ns)}
    for b in run["canvases"][1]["boxes"]:  # the engine's observed geometry, verbatim
        r = rects[b["id"]]
        assert (
            float(r.get("x")),
            float(r.get("y")),
            float(r.get("width")),
            float(r.get("height")),
        ) == pytest.approx((b["x"], b["y"], b["w"], b["h"]), abs=1e-3)
    assert root.find(".//oa:concept_hash", ns).text == st["concept"]["sealed_hash"]
    assert (
        root.find(".//oa:independent_verifier", ns).text == "pass"
        and root.find(".//oa:model_used", ns).text == "none"
    )
    pkg = client.get(f"/api/teach/{sid}/evidence.json").json()
    assert (
        pkg["teaching_ledger_chain_verified"] is True
        and pkg["concept"]["sealed_hash"] == st["concept"]["sealed_hash"]
    )
    assert (
        pkg["observed_geometry"] == run["canvases"][1]["boxes"]
        and pkg["result"]["verifier_passed"] is True
    )
