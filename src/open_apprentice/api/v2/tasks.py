"""Background jobs and Cloud Tasks (spec 8 `POST /internal/tasks/{action_id}`, spec 10).

A Job is serialisable background work (render a document, advance a session, apply a run). The local dispatcher runs jobs
in-process; the Cloud Tasks dispatcher enqueues an HTTP task carrying an OIDC token for the service account, delivered to
the internal route, which verifies the token before running anything."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class Job:
    kind: str  # render | advance | apply | ping
    key: str  # jobs with one key never run at the same time
    args: dict = field(default_factory=dict)


def job_to_json(job: Job) -> dict:
    return {"kind": job.kind, "key": job.key, "args": job.args}


def job_from_json(d: dict) -> Job:
    if (
        not isinstance(d, dict)
        or not isinstance(d.get("kind"), str)
        or not isinstance(d.get("key"), str)
    ):
        raise ValueError("not a job")
    return Job(d["kind"], d["key"], dict(d.get("args") or {}))


class Forbidden(Exception):
    pass


def google_verifier(token: str, audience: str) -> dict:
    from google.auth.transport import requests as greq
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(token, greq.Request(), audience=audience)


@dataclass(frozen=True)
class TasksAuth:
    """Who may call /internal/tasks: OIDC tokens for this audience issued to this service account."""

    audience: str
    service_account: str
    verifier: Callable[[str, str], dict] = google_verifier

    def verify(self, authorization: Optional[str]) -> None:
        if not authorization or not authorization.startswith("Bearer "):
            raise Forbidden("missing token")
        try:
            claims = self.verifier(authorization[len("Bearer ") :], self.audience)
        except Exception as e:  # any verification failure is a refusal
            raise Forbidden(f"invalid token ({type(e).__name__})") from e
        if claims.get("email") != self.service_account or claims.get("email_verified") is not True:
            raise Forbidden("token is not from the task service account")


class CloudTasksDispatcher:
    """Every submit is its own task (never deduplicated by name: that would drop a needed second advance); the internal
    route serialises jobs with one key, and the executors' claims make redundant work a no-op."""

    def __init__(
        self, client: Any, queue_path: str, service_url: str, service_account: str
    ) -> None:
        self.client, self.queue, self.url, self.sa = (
            client,
            queue_path,
            service_url.rstrip("/"),
            service_account,
        )

    def submit(self, job: Job) -> None:
        task_id = hashlib.sha256(f"{job.key}:{uuid.uuid4().hex}".encode()).hexdigest()[:32]
        self.client.create_task(
            parent=self.queue,
            task={
                "http_request": {
                    "http_method": "POST",
                    "url": f"{self.url}/internal/tasks/{task_id}",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(job_to_json(job)).encode(),
                    "oidc_token": {"service_account_email": self.sa, "audience": self.url},
                }
            },
        )

    def drain(self, timeout: float = 0) -> None:  # tasks run elsewhere
        return None

    def close(self) -> None:
        return None
