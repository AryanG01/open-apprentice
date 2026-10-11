"""Offline `.env` bootstrap (spec 24.2). Needs no database and no valid app secrets."""

from __future__ import annotations

import os
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_SESSION_PLACEHOLDERS = {"", "replace_with_a_generated_secret"}
_DB_PLACEHOLDERS = {"", "change_me"}


@dataclass
class InitResult:
    ok: bool
    messages: list[str] = field(default_factory=list)


def _parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v
    return out


def init_env_file(env_file: str, example_file: str = ".env.example") -> InitResult:
    """Create/update env_file from the example, replacing known placeholders only.

    User-supplied values are preserved. POSTGRES_PASSWORD and DATABASE_URL stay consistent.
    Secrets are never printed. The write is atomic.
    """
    example = Path(example_file)
    if not example.exists():
        return InitResult(False, [f"{example_file} not found"])
    target = Path(env_file)
    existing = _parse(target.read_text()) if target.exists() else {}
    base = _parse(example.read_text())
    values = {**base, **{k: v for k, v in existing.items() if k in base}}
    msgs: list[str] = []

    if values.get("SESSION_SECRET", "") in _SESSION_PLACEHOLDERS:
        values["SESSION_SECRET"] = secrets.token_urlsafe(48)
        msgs.append("SESSION_SECRET: generated (not shown)")
    if values.get("POSTGRES_PASSWORD", "") in _DB_PLACEHOLDERS:
        pw = secrets.token_urlsafe(24)
        old = values["POSTGRES_PASSWORD"]
        values["POSTGRES_PASSWORD"] = pw
        if old and old in values.get("DATABASE_URL", ""):
            values["DATABASE_URL"] = values["DATABASE_URL"].replace(f":{old}@", f":{pw}@")
        msgs.append("POSTGRES_PASSWORD + DATABASE_URL: generated, kept consistent (not shown)")

    lines = [f"{k}={values[k]}" for k in base]
    fd, tmp = tempfile.mkstemp(dir=str(target.parent or Path(".")), prefix=".env.tmp.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    msgs.append(f"wrote {env_file} (mode 600)")
    return InitResult(True, msgs)
