import os
import pathlib
import socket
import subprocess
import time

import httpx
import pytest

TOKEN = "e2e-token"


def pytest_collection_modifyitems(config, items):
    if os.environ.get("OA_ENGINE_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set OA_ENGINE_TESTS=1 (needs Chromium; run unsandboxed)")
    for it in items:
        if "engine_url" in getattr(it, "fixturenames", ()):
            it.add_marker(skip)


@pytest.fixture(scope="session")
def engine_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    root = pathlib.Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(
        ["node", "services/engine/src/server.js"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "EVALUATOR_TOKEN": TOKEN},
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            if httpx.get(url + "/health/live").status_code == 200:
                break
        except httpx.TransportError:
            time.sleep(0.1)
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
