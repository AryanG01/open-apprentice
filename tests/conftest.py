import pytest


@pytest.fixture(autouse=True)
def _hermetic_provider_env(monkeypatch):
    """Tests must never depend on (or spend through) the developer's real credentials."""
    for k in ("NEBIUS_API_KEY", "PROVIDER_MODE", "LIVE_RUN_MAX_USD"):
        monkeypatch.delenv(k, raising=False)
