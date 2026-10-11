"""Evaluator-side environment service implementing agent.ports.EnvPort. Holds the PRIVATE drift schedule."""

from __future__ import annotations

from typing import Optional

from open_apprentice.concepts.bindings import backend_scene
from open_apprentice.concepts.schemas import sha
from open_apprentice.environments.client import EngineSession
from open_apprentice.evaluation.episodes import Episode
from open_apprentice.evaluation.harness import EvaluatorHarness


def _key(backend: str, scene: dict) -> str:
    return sha([backend, [{k: str(v) for k, v in o.items()} for o in scene["objects"]]])


class EnvService:
    def __init__(self, harness: EvaluatorHarness, episode: Episode, owner: str) -> None:
        self.h, self.ep, self.owner = harness, episode, owner
        self.drift_active = False
        self._stored: dict[str, Optional[dict]] = {}
        self.sessions: list[tuple[EngineSession, dict]] = (
            []
        )  # (session, initial native) for sealing/judging/cleanup

    def begin_stage(self, stage: str) -> None:
        """The evaluator flips the tool change at the recovery stage (and keeps it): the policy is never told."""
        if stage == "recovery" and self.ep.drift is not None:
            self.drift_active = True

    def _private(self, backend: str) -> Optional[dict]:
        return self.ep.drift if (self.drift_active and backend == self.ep.target_backend) else None

    def open(self, backend: str, scene: dict) -> EngineSession:
        priv = self._private(backend)
        s, initial = self.h.open_session(backend_scene(scene), self.owner, priv, backend=backend)
        self._stored[_key(backend, scene)] = priv
        self.sessions.append((s, initial))
        return s

    def replay(self, backend: str, scene: dict) -> EngineSession:
        k = _key(backend, scene)
        if k not in self._stored:
            raise KeyError("no stored case for this scene")
        s, initial = self.h.open_session(
            backend_scene(scene), self.owner, self._stored[k], backend=backend
        )
        self.sessions.append((s, initial))
        return s

    def initial_of(self, session: EngineSession) -> dict:
        return next(i for s, i in self.sessions if s is session)

    def close_all(self) -> None:
        for s, _ in self.sessions:
            try:
                s.close()
            except Exception:
                pass
        self.sessions.clear()
