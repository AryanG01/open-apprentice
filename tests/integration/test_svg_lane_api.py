"""Real-SVG lane end to end on the REAL engine: teach a rule, apply it to three owner-authored SVGs, verify rendered geometry in the browser,
refuse harmful patches, and refuse incompatible documents. (opt-in: OA_ENGINE_TESTS=1)"""

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import TOKEN
from tests.integration.test_api_teach import _teach

PAIRS = {
    "product-cards": [("card-1", "badge-1"), ("card-2", "badge-2"), ("card-3", "badge-3")],
    "dashboard-tiles": [("a-card", "a-badge"), ("b-card", "b-badge"), ("c-card", "c-badge")],
    "pricing-table": [("plan-free", "plan-free-tag"), ("plan-pro", "plan-pro-tag")],
}


@pytest.fixture()
def client(engine_url, monkeypatch):
    monkeypatch.setenv("ENGINE_URL", engine_url)
    monkeypatch.setenv("EVALUATOR_TOKEN", TOKEN)
    from open_apprentice.api.app import app

    with TestClient(app) as c:
        yield c


def test_samples_and_inspect_are_public_and_report_coverage(client):
    names = {s["id"] for s in client.get("/api/svg/samples").json()}
    assert names == set(PAIRS)
    inv = client.post("/api/svg/inspect", json={"sample": "pricing-table"}).json()["inventory"]
    assert (
        inv["coverage"]["editable"] < inv["coverage"]["listed"]
    )  # the rotated promo card is listed but not editable
    assert client.post("/api/svg/inspect", json={"sample": "../etc/passwd"}).status_code == 404


@pytest.mark.parametrize("name", PAIRS)
def test_the_taught_rule_is_applied_and_the_browser_confirms_the_geometry(client, name):
    sid, st = _teach(client)
    body = {
        "sample": name,
        "session_id": sid,
        "pairs": [{"card": c, "badge": b} for c, b in PAIRS[name]],
    }
    r = client.post("/api/svg/apply", json=body).json()
    assert (
        r["passed"] is True
        and r["unrelated_byte_changes"] == 0
        and r["only_selected_badges_moved"] is True
    )
    assert r["concept_hash"] == st["concept"]["sealed_hash"] and r["label"]["model"] == "none"
    for row in r["rows"]:
        assert (
            row["passed"] and row["max_error_px"] <= 0.5
        ), row  # measured by Chromium, not computed by us
    assert set(r["moved_elements"]) == {b for _, b in PAIRS[name]}
    assert r["modified_svg"] != r["original_svg"] and r["hash_before"] != r["hash_after"]


def test_apply_requires_a_taught_rule_and_refuses_unsupported_selections(client):
    st = client.post("/api/teach").json()
    body = {
        "sample": "product-cards",
        "session_id": st["id"],
        "pairs": [{"card": "card-1", "badge": "badge-1"}],
    }
    assert client.post("/api/svg/apply", json=body).status_code == 409
    sid, _ = _teach(client)
    bad = client.post(
        "/api/svg/apply",
        json={
            "sample": "pricing-table",
            "session_id": sid,
            "pairs": [{"card": "plan-promo", "badge": "plan-promo-tag"}],
        },
    )
    assert bad.status_code == 422 and "transform" in bad.text
    assert (
        client.post(
            "/api/svg/apply",
            json={
                "sample": "product-cards",
                "session_id": sid,
                "pairs": [{"card": "card-1", "badge": "no-such"}],
            },
        ).status_code
        == 422
    )


def test_harmful_patches_are_all_rejected_and_incompatible_uploads_are_refused(client):
    r = client.post("/api/svg/harmful-demo", json={"sample": "dashboard-tiles"}).json()
    assert (
        r["all_rejected"] is True
        and len(r["attempts"]) >= 7
        and all(a["reasons"] for a in r["attempts"])
    )
    evil = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><rect id="a" x="0" y="0" width="1" height="1"/></svg>'
    u = client.post("/api/svg/inspect", json={"svg": evil})
    assert u.status_code == 422 and "scripts" in u.text
    assert (
        client.post("/api/svg/inspect", json={"svg": evil, "sample": "product-cards"}).status_code
        == 422
    )  # exactly one source
