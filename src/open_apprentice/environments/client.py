"""Agent-facing engine client. Exposes ONLY the public tool surface.

There is deliberately no method here for private config or native state: those live in
evaluation/harness.py behind the evaluator token (import-linter keeps agent code away from it).
Sync httpx: the restricted interpreter calls tools synchronously. # ponytail: blocks the event loop
during tool calls; fine for one worker, move to a thread if concurrency matters.
"""

from __future__ import annotations

import itertools
from typing import Any, Optional

import httpx


class EngineToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class EngineSession:
    def __init__(
        self, client: httpx.Client, session_id: str, owner: str, revision: int, schema_hash: str
    ) -> None:
        self._c, self.session_id, self.owner = client, session_id, owner
        self.revision = revision
        self.public_schema_hash = schema_hash
        self.actions_used = 0
        self._ids = itertools.count()

    @classmethod
    def create(
        cls,
        base_url: str,
        scene: dict,
        owner: str,
        backend: str = "konva",
        transport: Optional[httpx.BaseTransport] = None,
    ) -> "EngineSession":
        c = httpx.Client(base_url=base_url, timeout=30.0, transport=transport)
        r = c.post("/sessions", json={"scene": scene, "owner": owner, "backend": backend})
        r.raise_for_status()
        d = r.json()
        return cls(c, d["session_id"], owner, d["revision"], d["public_schema_hash"])

    @classmethod
    def attach(
        cls,
        base_url: str,
        session_id: str,
        owner: str,
        revision: int,
        schema_hash: str,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> "EngineSession":
        """Bind to a session someone else created (the evaluator, for private-config episodes)."""
        return cls(
            httpx.Client(base_url=base_url, timeout=30.0, transport=transport),
            session_id,
            owner,
            revision,
            schema_hash,
        )

    def call(self, tool: str, **args: Any) -> Any:
        """One primitive action. Mutations carry the expected revision and a unique action id."""
        self.actions_used += 1
        body = {
            "owner": self.owner,
            "tool": tool,
            "args": args,
            "expected_revision": self.revision,
            "action_id": f"{self.session_id}:{next(self._ids)}",
        }
        r = self._c.post(f"/sessions/{self.session_id}/actions", json=body)
        r.raise_for_status()
        d = r.json()
        if not d.get("ok"):
            err = d.get("error", {})
            raise EngineToolError(err.get("code", "TOOL_ERROR"), err.get("message", ""))
        self.revision = d["revision"]
        return d["result"]

    def tools(self, names: list[str]) -> dict:
        return {n: (lambda _n=n, **kw: self.call(_n, **kw)) for n in names}

    def close(self) -> None:
        try:
            self._c.delete(f"/sessions/{self.session_id}", params={"owner": self.owner})
        finally:
            self._c.close()
