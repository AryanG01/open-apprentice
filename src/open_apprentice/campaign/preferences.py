"""Versioned overflow preferences (spec 7.6): the owner's choice of a built-in outcome, per language, with history and
rollback. Same compare-and-set pointer pattern as skills/versions.py; the choice is a preference, never a learned rule."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Optional

from open_apprentice.campaign.builtins import BUILTINS
from open_apprentice.storage.store import PreconditionFailed, Store


def scope_key(locale: str) -> str:
    return f"promo_card/9:16/overflow/{locale}"


@dataclass
class Preference:
    scope: str
    outcome: str
    version: int
    parent: Optional[int]
    provenance: dict


class PreferenceConflict(Exception):
    pass


class PreferenceStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    def _key(self, scope: str, leaf: str) -> str:
        return f"campaign/preferences/{scope}/{leaf}.json"

    def _pointer(self, scope: str) -> tuple[dict, Optional[int]]:
        blob = self.store.get(self._key(scope, "active"))
        if blob is None:
            return {"active": None, "latest": 0}, None
        return json.loads(blob.data), blob.generation

    def _version(self, scope: str, n: int) -> Preference:
        blob = self.store.get(self._key(scope, f"v{n}"))
        if blob is None:
            raise KeyError(f"{scope} has no version {n}")
        return Preference(**json.loads(blob.data))

    def _move(self, scope: str, state: dict, gen: Optional[int]) -> None:
        try:
            self.store.put(
                self._key(scope, "active"), json.dumps(state).encode(), if_generation=gen
            )
        except PreconditionFailed as e:
            raise PreferenceConflict(str(e)) from None

    def get(self, scope: str) -> Optional[Preference]:
        state, _ = self._pointer(scope)
        return None if state["active"] is None else self._version(scope, state["active"])

    def set(
        self, scope: str, outcome: str, provenance: dict, expected_version: Optional[int]
    ) -> Preference:
        if outcome not in BUILTINS:
            raise ValueError(f"a preference names a built-in outcome, not {outcome!r}")
        state, gen = self._pointer(scope)
        if state["active"] != expected_version:
            raise PreferenceConflict(
                f"{scope}: active version is {state['active']}, not {expected_version}"
            )
        pref = Preference(scope, outcome, state["latest"] + 1, state["active"], provenance)
        if not self.store.create(
            self._key(scope, f"v{pref.version}"), json.dumps(asdict(pref)).encode()
        ):
            raise PreferenceConflict(f"{scope}: version {pref.version} was written concurrently")
        self._move(scope, {"active": pref.version, "latest": pref.version}, gen)
        return pref

    def rollback(self, scope: str, to_version: int, expected_version: int) -> Preference:
        state, gen = self._pointer(scope)
        if state["active"] != expected_version or to_version == expected_version:
            raise PreferenceConflict(
                f"{scope}: active version is {state['active']}; cannot roll back to {to_version}"
            )
        target = self._version(scope, to_version)
        self._move(scope, {**state, "active": to_version}, gen)
        return target

    def history(self, scope: str) -> list[Preference]:
        state, _ = self._pointer(scope)
        return [self._version(scope, n) for n in range(1, state["latest"] + 1)]
