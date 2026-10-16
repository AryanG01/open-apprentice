import json
import threading

import pytest

from open_apprentice.api.v2 import service
from open_apprentice.api.v2.tasks import CloudTasksDispatcher, Job, TasksAuth

AUD, SA = "https://oa-staging.example.run.app", "oa-staging-worker@proj.iam.gserviceaccount.com"


class FakeTasksClient:
    def __init__(self):
        self.created = []

    def create_task(self, parent=None, task=None):
        self.created.append((parent, task))
        return task


def fake_verifier(claims):
    def verify(token, audience):
        if token != "good" or audience != AUD:
            raise ValueError("bad token")
        return claims

    return verify


GOOD = {"email": SA, "email_verified": True, "aud": AUD}


@pytest.fixture
def tasks_on(v2):
    v2.internal_tasks = TasksAuth(AUD, SA, fake_verifier(GOOD))
    return v2


def ping(client, task_id="t1", token="good", job=None):
    body = json.dumps(job or {"kind": "ping", "key": "ping:1", "args": {"id": "1"}})
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    return client.post(f"/internal/tasks/{task_id}", content=body, headers=headers)


def test_dispatcher_creates_an_oidc_http_task():
    fake = FakeTasksClient()
    d = CloudTasksDispatcher(fake, "projects/p/locations/r/queues/q", AUD, SA)
    d.submit(Job("advance", "s1", {"sid": "s1"}))
    parent, task = fake.created[0]
    req = task["http_request"]
    assert parent == "projects/p/locations/r/queues/q" and req["url"].startswith(
        f"{AUD}/internal/tasks/"
    )
    assert req["oidc_token"] == {"service_account_email": SA, "audience": AUD}
    assert json.loads(req["body"]) == {"kind": "advance", "key": "s1", "args": {"sid": "s1"}}
    d.submit(Job("advance", "s1", {"sid": "s1"}))
    assert (
        fake.created[0][1]["http_request"]["url"] != fake.created[1][1]["http_request"]["url"]
    )  # never deduplicated by name


@pytest.mark.parametrize(
    "token, claims",
    [
        (None, GOOD),
        ("forged", GOOD),
        ("good", {**GOOD, "email": "evil@x"}),
        ("good", {**GOOD, "email_verified": False}),
    ],
)
def test_forged_internal_calls_are_refused_and_run_nothing(client, v2, token, claims):
    v2.internal_tasks = TasksAuth(AUD, SA, fake_verifier(claims))
    r = ping(client, token=token)
    assert r.status_code == 403 and v2.store.get("staging/ping-1") is None


def test_delivery_runs_the_job_once_even_when_repeated(client, tasks_on, monkeypatch):
    runs = []
    real = service.run_job
    monkeypatch.setattr(service, "run_job", lambda v, job: (runs.append(job.key), real(v, job)))
    assert ping(client).json() == {"state": "done"}
    assert ping(client).json() == {"state": "done"} and len(runs) == 1
    assert tasks_on.store.get("staging/ping-1") is not None


def test_concurrent_deliveries_run_once(client, tasks_on, monkeypatch):
    runs = []
    real = service.run_job

    def slow(v, job):
        runs.append(job.key)
        import time

        time.sleep(0.2)
        return real(v, job)

    monkeypatch.setattr(service, "run_job", slow)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(ping(client, "same").status_code))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(runs) == 1 and results == [200] * 4


def test_a_failing_job_is_recorded_and_not_retried(client, tasks_on):
    r = ping(client, "bad", job={"kind": "nonsense", "key": "x", "args": {}})
    assert (
        r.status_code == 200 and r.json()["state"] == "failed" and "nonsense" in r.json()["reason"]
    )


def test_route_is_absent_unless_cloud_tasks_is_configured(client):
    assert ping(client).status_code == 404
