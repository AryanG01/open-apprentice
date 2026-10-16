import ast
import pathlib

import pytest

ROUTES = [
    ("get", "/api/v2/documents/{doc}"),
    ("get", "/api/v2/documents/{doc}/pages/{page}/preview.png"),
    ("post", "/api/v2/documents/{doc}/mapping"),
    ("post", "/api/v2/documents/{doc}/draft"),
    ("get", "/api/v2/sessions/{sid}"),
    ("post", "/api/v2/sessions/{sid}/responses"),
    ("post", "/api/v2/sessions/{sid}/cancel"),
    ("get", "/api/v2/runs/{run}"),
    ("get", "/api/v2/runs/{run}/export"),
    ("post", "/api/v2/runs/{run}/cancel"),
    ("get", "/api/v2/skills/{skill}"),
    ("post", "/api/v2/skills/{skill}/versions/1/apply"),
    ("post", "/api/v2/skills/{skill}/corrections"),
    ("post", "/api/v2/skills/{skill}/activate"),
]


@pytest.mark.parametrize("method, path", ROUTES)
def test_every_owned_route_hides_other_owners(full_flow, method, path):
    client, ids = full_flow
    client.cookies.clear()  # a different (new) owner
    url = path.format(**ids)
    r = getattr(client, method)(url, **({"json": {}} if method == "post" else {}))
    assert r.status_code == 404, (url, r.status_code, r.text[:200])


def test_tampered_cookie_is_a_new_owner(full_flow):
    client, ids = full_flow
    tok = client.cookies.get("oa_owner")
    client.cookies.clear()
    client.cookies.set("oa_owner", tok[:-2] + ("xx" if not tok.endswith("xx") else "yy"))
    assert client.get(f"/api/v2/documents/{ids['doc']}").status_code == 404


def test_same_idempotency_key_different_body_is_409(full_flow):
    client, ids = full_flow
    url = f"/api/v2/skills/{ids['skill']}/versions/1/apply"
    a = client.post(url, json={"documents": [ids["docref"]], "idempotency_key": "same"})
    b = client.post(url, json={"documents": [], "idempotency_key": "same"})
    assert a.status_code == 202 and b.status_code == 409


def test_legacy_routes_still_answer_and_v2_is_not_shadowed(monkeypatch):
    monkeypatch.setenv("OA_NO_LOCAL_ENGINE", "1")
    from fastapi.testclient import TestClient

    from open_apprentice.api.app import app

    with TestClient(app) as c:
        assert c.get("/api/svg/samples").status_code == 200
        r = c.get("/api/v2/documents/nope")
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


def test_api_v2_does_not_import_the_evaluator():
    banned = (
        "open_apprentice.evaluation.labels",
        "open_apprentice.evaluation.verifier",
        "open_apprentice.evaluation.episodes",
    )
    for f in pathlib.Path("src/open_apprentice/api/v2").glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                assert not any(n.startswith(banned) for n in names), (f, names)
