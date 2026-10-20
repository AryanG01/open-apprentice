"""Plan 8 review fixes: loop cost is bounded, exports reuse the publish render, the policy travels with the skill,
the display trace never breaks the session view, corrections stay on teaching-sized pages."""

import time
from fractions import Fraction

import pytest

from open_apprentice.concepts.rules import RuleError, evaluate_rule


def _objs(n):
    return [
        {
            "id": f"o{k}",
            "kind": "node",
            "role": "",
            "attached": "",
            "x": Fraction(k),
            "y": Fraction(0),
            "w": Fraction(1),
            "h": Fraction(1),
        }
        for k in range(n)
    ]


def test_nested_empty_loops_over_a_large_page_hit_the_step_cap_quickly():
    loop = lambda v, body: {
        "op": "for_each",
        "var": v,
        "index_var": f"i{v}",
        "over": {"ref": "objects"},
        "body": body,
    }
    rule = [loop("a", [loop("b", [loop("c", [])])])]
    t = time.monotonic()
    with pytest.raises(RuleError):
        evaluate_rule(rule, _objs(400), {"w": Fraction(10000), "h": Fraction(10000)})
    assert time.monotonic() - t < 5


def test_png_export_reuses_the_render_made_while_publishing(
    client, v2, committed_skill, fresh_bytes
):
    from tests.unit.api_v2.conftest import import_and_confirm

    ok = import_and_confirm(client, v2, fresh_bytes, "fresh.drawio")
    rid = client.post(
        f"/api/v2/skills/{committed_skill}/versions/1/apply",
        json={"documents": [ok], "idempotency_key": "p8png"},
    ).json()["run_id"]
    v2.dispatcher.drain()
    calls = []
    real = v2.render
    v2.render = lambda page: (calls.append(1), real(page))[1]
    r = client.get(
        f"/api/v2/runs/{rid}/export",
        params={"doc_id": ok["doc_id"], "page_id": ok["page_id"], "format": "png"},
    )
    assert r.status_code == 200 and calls == []


def test_skill_and_run_provenance_carry_the_policy(client, v2, committed_skill, fresh_bytes):
    from tests.unit.api_v2.conftest import import_and_confirm

    assert client.get(f"/api/v2/skills/{committed_skill}").json()["provenance"]["policy"] == "A"
    ok = import_and_confirm(client, v2, fresh_bytes, "fresh.drawio")
    rid = client.post(
        f"/api/v2/skills/{committed_skill}/versions/1/apply",
        json={"documents": [ok], "idempotency_key": "p8prov"},
    ).json()["run_id"]
    v2.dispatcher.drain()
    assert client.get(f"/api/v2/runs/{rid}").json()["provenance"]["policy"] == "A"


def test_a_broken_trace_never_breaks_the_session_view():
    from open_apprentice.api.v2.service import _thinking
    from open_apprentice.teaching.events import Event

    bad = [Event("e1", None, 1, "ModelProposalReturned", "system", {"action_id": "a"}, None)]
    assert _thinking(bad, "Live") == []


def test_a_correction_on_a_page_too_large_to_teach_is_refused_clearly(client, v2, committed_skill):
    from tests.unit.api_v2.conftest import import_and_confirm
    from tests.unit.api_v2.test_corrections import correct
    from tests.unit.api_v2.test_large_documents import big

    ref = import_and_confirm(client, v2, big(), "big.drawio")
    run = client.post(
        f"/api/v2/skills/{committed_skill}/versions/1/apply",
        json={"documents": [ref], "idempotency_key": "p8big"},
    ).json()
    v2.dispatcher.drain()
    active = client.get(f"/api/v2/skills/{committed_skill}").json()["active"]
    r = correct(client, committed_skill, run["run_id"], ref, active, {"n0": ["50", "90"]}, "p8c")
    assert r.status_code == 409 and r.json()["error"]["code"] == "TOO_LARGE_TO_TEACH", r.text
