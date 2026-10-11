"""Start the Node engine for local runs. The child gets a MINIMAL environment: it never sees NEBIUS_API_KEY or any
other secret in the parent's environment. The evaluator token is random per process."""

from __future__ import annotations

import os
import pathlib
import secrets
import socket
import subprocess
import time
from contextlib import contextmanager
from typing import Iterator

import httpx


@contextmanager
def local_engine(root: str = ".") -> Iterator[tuple[str, str]]:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    token = secrets.token_urlsafe(24)
    env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG") if k in os.environ}
    env.update(PORT=str(port), HOST="127.0.0.1", EVALUATOR_TOKEN=token)
    proc = subprocess.Popen(
        ["node", "services/engine/src/server.js"],
        cwd=pathlib.Path(root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(200):
            if proc.poll() is not None:
                raise RuntimeError(
                    "engine exited during startup (is Chromium installed and are you outside the sandbox?)"
                )
            try:
                if httpx.get(url + "/health/live", timeout=2).status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(0.1)
        else:
            raise RuntimeError("engine did not become healthy")
        yield url, token
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
