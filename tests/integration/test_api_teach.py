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
    assert fix["repaired_by"] == "fixture"  # reference mode never calls a model
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


def _model_client(engine_url, monkeypatch, provider):
    monkeypatch.setenv("ENGINE_URL", engine_url)
    monkeypatch.setenv("EVALUATOR_TOKEN", TOKEN)
    from open_apprentice.api.app import app

    c = TestClient(app)
    c.__enter__()
    app.state.provider = provider
    return c


def _teach_with_model(c):
    st = c.post("/api/teach", json={"mode": "nemotron"}).json()
    for _ in range(3):
        if st["state"] != "AWAITING_USER":
            break
        q = st["question"]
        st = c.post(
            f"/api/teach/{st['id']}/answer",
            json={
                "query_id": q["query_id"],
                "answer": q["options"][0]["id"],
                "candidate_set_hash": q["candidate_set_hash"],
            },
        ).json()
    assert st["state"] == "INTENT_READY", st
    return st["id"]


def _script(binding_programs, repair_programs):
    from open_apprentice.api import fixtures as fx
    from open_apprentice.providers.mock import MockProvider
    from tests.fixtures_rules import CLAMPED_MARGIN, CONST_MARGIN, PROP_MARGIN

    rules = [
        ("fixed 12px inset", CONST_MARGIN),
        ("8% inset", PROP_MARGIN()),
        ("clamped inset", CLAMPED_MARGIN()),
    ]
    return MockProvider(
        {
            "hypotheses": [{"candidates": [{"summary": n, "rule": r} for n, r in rules]}],
            "binding": [fx.cands(*binding_programs)] * 2,
            "binding_repair": [fx.cands(*repair_programs)],
        }
    )


def test_model_mode_end_to_end_marks_model_origin_and_meters_every_call(engine_url, monkeypatch):
    from open_apprentice.api import fixtures as fx

    # The SCRIPTED mock plays "the model" and returns the known-good programs: this proves the plumbing (origin, meter, repair), not model quality.
    c = _model_client(
        engine_url, monkeypatch, _script([fx.NAIVE], [fx.HARDCODED_OFFSET, fx.PROBING])
    )
    try:
        sid = _teach_with_model(c)
        ok = c.post(f"/api/teach/{sid}/run", json={"width": 300, "backend": "fabric"}).json()
        assert (
            ok["verifier_passed"] and ok["binding"]["origin"] == "model" and ok["fallbacks"] == []
        )
        assert ok["meter"]["session_calls"] >= 2
        bad = c.post(
            f"/api/teach/{sid}/run", json={"width": 300, "backend": "fabric", "tool_change": True}
        ).json()
        assert not bad["verifier_passed"] and bad["can_repair"]
        fix = c.post(f"/api/teach/{sid}/repair").json()
        assert fix["status"] == "validated" and fix["rule_unchanged"] is True
        assert [a["source"] for a in fix["attempts"]] == ["model", "model"] and fix["versions"][-1][
            "origin"
        ] == "model"
        assert fix["repaired_by"] == "model"
    finally:
        c.__exit__(None, None, None)


def test_failed_model_repair_reports_the_fixture_as_the_repairer(engine_url, monkeypatch):
    from open_apprentice.api import fixtures as fx

    c = _model_client(
        engine_url, monkeypatch, _script([fx.NAIVE], [fx.HARDCODED_OFFSET])
    )  # the "model" repair is wrong, so the labelled fixture must be the one credited
    try:
        sid = _teach_with_model(c)
        c.post(
            f"/api/teach/{sid}/run", json={"width": 300, "backend": "fabric", "tool_change": True}
        )
        fix = c.post(f"/api/teach/{sid}/repair").json()
        assert fix["status"] == "validated" and fix["repaired_by"] == "fixture"
        assert "model" in [a["source"] for a in fix["attempts"]]
        assert any("scripted fixture repair was tried" in f for f in fix["fallbacks"])
    finally:
        c.__exit__(None, None, None)


def test_model_mode_falls_back_to_a_labelled_fixture_when_the_model_procedure_is_wrong(
    engine_url, monkeypatch
):
    from open_apprentice.api import fixtures as fx

    c = _model_client(
        engine_url, monkeypatch, _script([fx.HARDCODED_OFFSET], [fx.HARDCODED_OFFSET])
    )  # a wrong "model" answer
    try:
        sid = _teach_with_model(c)
        run = c.post(f"/api/teach/{sid}/run", json={"width": 300, "backend": "fabric"}).json()
        assert run["verifier_passed"] and run["binding"]["origin"] == "fixture"
        assert run["fallbacks"] and "scripted fixture was used instead" in run["fallbacks"][0]
        pkg = c.get(f"/api/teach/{sid}/evidence.json").json()
        assert pkg["fallbacks"] == run["fallbacks"] and pkg["model_meter"]["session_calls"] >= 2
    finally:
        c.__exit__(None, None, None)


def test_break_it_reports_what_was_tested_and_finds_the_unrepaired_tool_change(client):
    sid, _ = _teach(client)
    assert (
        client.post(f"/api/teach/{sid}/break", json={"backend": "konva", "samples": 5}).status_code
        == 200
    )
    ok = client.post(
        f"/api/teach/{sid}/break", json={"backend": "fabric", "samples": 20, "seed": 3}
    ).json()
    assert (
        ok["tested"] == 20
        and ok["passed"] == 20
        and ok["failed"] == 0
        and "not a proof" in ok["coverage"]
    )
    again = client.post(
        f"/api/teach/{sid}/break", json={"backend": "fabric", "samples": 20, "seed": 3}
    ).json()
    assert again["tested"] == 20 and again["failed"] == 0  # deterministic for a seed
    bad = client.post(
        f"/api/teach/{sid}/break", json={"backend": "fabric", "tool_change": True, "samples": 12}
    ).json()
    assert (
        bad["failed"] == bad["tested"] > 0 and bad["failures"][0]["native_diffs"]
    )  # the unrepaired scripted procedure fails everywhere
    client.post(
        f"/api/teach/{sid}/run", json={"width": 300, "backend": "fabric", "tool_change": True}
    )
    assert client.post(f"/api/teach/{sid}/repair").json()["status"] == "validated"
    fixed = client.post(
        f"/api/teach/{sid}/break",
        json={"backend": "fabric", "tool_change": True, "samples": 20, "seed": 5},
    ).json()
    assert (
        fixed["failed"] == 0 and fixed["passed"] == 20
    )  # after the repair, the changed tool passes too
    assert client.get(f"/api/teach/{sid}/evidence.json").json()["stress_test"]["tested"] == 20


def test_a_replay_session_is_labelled_replay_everywhere_including_its_evidence(client):
    from open_apprentice.api.app import app

    if app.state.tape is None:
        pytest.skip("no replay tape installed")
    st = client.post("/api/teach", json={"mode": "replay"}).json()
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
    sid = st["id"]
    run = client.post(f"/api/teach/{sid}/run", json={"width": 300, "backend": "konva"}).json()
    assert run["label"]["mode"].startswith("REPLAY"), run["label"]
    evidence = client.get(f"/api/teach/{sid}/evidence.json").json()
    assert evidence["label"]["mode"].startswith("REPLAY"), evidence["label"]
    svg = client.get(f"/api/teach/{sid}/export.svg").text
    assert "replay" in svg.lower()
    assert "LIVE ENGINE + NVIDIA NEMOTRON" not in svg
