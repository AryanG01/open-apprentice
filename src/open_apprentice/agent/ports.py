"""What a policy may touch. Deliberately tiny. Nothing here names a drift, epoch, stage, or latent rule."""

from __future__ import annotations

from typing import Protocol

from open_apprentice.environments.client import EngineSession


class TeacherPort(Protocol):
    """Answers submitted queries only. The method set is the whole interface; there is no way to ask for a rule."""

    def answer(self, view: dict) -> str: ...
    def corrected_example(self, scene: dict) -> dict: ...


class EnvPort(Protocol):
    """Sessions for the CURRENT environment, plus opaque replay of cases the policy itself ran before.

    `replay` re-creates a stored case under whatever environment it was originally recorded in, without
    disclosing what that was (spec 11.3). Neither method reveals whether the tools changed."""

    def open(self, backend: str, scene: dict) -> EngineSession: ...
    def replay(self, backend: str, scene: dict) -> EngineSession: ...
