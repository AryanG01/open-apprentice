def test_app_starts_when_the_v2_store_cannot_be_created(monkeypatch, tmp_path):
    """A broken v2 setup (e.g. an unwritable store folder in the container) must not take down the legacy demo."""
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("OA_NO_LOCAL_ENGINE", "1")
    monkeypatch.setenv(
        "OA_STORE_DIR", str(blocker / "store")
    )  # a folder inside a file: cannot be created
    from fastapi.testclient import TestClient

    from open_apprentice.api.app import app

    with TestClient(app) as c:
        assert c.get("/health/live").status_code == 200
        assert c.get("/api/svg/samples").status_code == 200
        r = c.get("/api/v2/documents/x")
        assert r.status_code == 503 and r.json()["error"]["code"] == "V2_UNAVAILABLE"
