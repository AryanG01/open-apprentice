"""The demo model cap (Try-it-live and Campaign) must hold across server restarts and Cloud Run instances: spend is written to
the durable ledger every v2 instance reads, not only to one process's memory."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


class _Snap:
    def __init__(self, usd: float) -> None:
        self.usd = usd

    def snapshot(self) -> dict:
        return {
            "consumed": {"tokens": 1000, "usd": self.usd},
            "held": {"tokens": 0},
            "unknown_cost_tokens": 0,
        }


def _live(usd: float):
    return SimpleNamespace(replay=False, ledger=_Snap(usd), counted_tokens=0, counted_usd=0.0)


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("OA_NO_LOCAL_ENGINE", "1")
    monkeypatch.delenv("ENGINE_URL", raising=False)
    from open_apprentice.api import teach
    from open_apprentice.api.app import app

    monkeypatch.setenv("DEMO_MODEL_MAX_USD", str(teach.RESERVE_USD + 0.1))
    return app


def test_spend_survives_a_restart_and_is_seen_by_another_instance(app):
    from open_apprentice.api import teach

    with TestClient(app):
        req = SimpleNamespace(app=app)
        teach._require_model_budget(req)  # an empty ledger admits a session
        teach._account(req, _live(0.2))
    with TestClient(app):  # a new process: the in-memory counter starts at zero again
        req = SimpleNamespace(app=app)
        assert app.state.spend["usd"] == 0.0
        with pytest.raises(HTTPException) as e:
            teach._require_model_budget(req)
        assert e.value.status_code == 402


def test_accounting_records_only_the_new_spend_each_time(app):
    from open_apprentice.api import teach

    with TestClient(app):
        req = SimpleNamespace(app=app)
        live = _live(0.03)
        teach._account(req, live)
        live.ledger.usd = 0.05
        teach._account(req, live)
        teach._account(req, live)  # nothing new
        assert float(app.state.v2.ledger.exposure()["total"]) == pytest.approx(0.05)
