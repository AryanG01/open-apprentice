"""Evaluator-side engine access: private drift config and native state. Never imported by agent code."""

from __future__ import annotations

from typing import Optional

import httpx

from open_apprentice.environments.client import EngineSession
from open_apprentice.evaluation.verifier import (
    VerifierReport,
    verify_expected_geometry,
    verify_gap_row,
)


class EvaluatorHarness:
    def __init__(
        self, base_url: str, token: str, transport: Optional[httpx.BaseTransport] = None
    ) -> None:
        self._base = base_url
        self._c = httpx.Client(
            base_url=base_url,
            headers={"x-evaluator-token": token},
            timeout=60.0,
            transport=transport,
        )

    def open_session(
        self, scene: dict, owner: str, private_config: Optional[dict] = None, backend: str = "konva"
    ) -> tuple[EngineSession, dict]:
        """Create a session (optionally drifted) and return (agent-facing handle, initial native state)."""
        r = self._c.post(
            "/internal/sessions",
            json={
                "scene": scene,
                "owner": owner,
                "private_config": private_config,
                "backend": backend,
            },
        )
        r.raise_for_status()
        d = r.json()
        session = EngineSession.attach(
            self._base, d["session_id"], owner, d["revision"], d["public_schema_hash"]
        )
        try:
            initial = self.native(d["session_id"], owner)
        except Exception:
            session.close()  # never leave an engine slot held by a session nobody can use
            raise
        return session, initial

    def native(self, session_id: str, owner: str) -> dict:
        r = self._c.get(f"/internal/sessions/{session_id}/native", params={"owner": owner})
        r.raise_for_status()
        return r.json()

    def judge_gap_row(self, session: EngineSession, initial: dict, task: dict) -> VerifierReport:
        """Seal-then-score: called only after the agent has committed its output."""
        return verify_gap_row(initial, self.native(session.session_id, session.owner), task)

    def judge_expected(
        self, session: EngineSession, initial: dict, expected: dict, selected_ids: list[str]
    ) -> VerifierReport:
        """Held-out intent check: `expected` comes from the PRIVATE teacher rule, never from the learner."""
        return verify_expected_geometry(
            initial, self.native(session.session_id, session.owner), expected, selected_ids
        )
