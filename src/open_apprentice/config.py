"""Application settings, loaded from environment variables (see .env.example).

Spec 14.2: never print secret values. describe_settings_safely() only emits
presence/absence for secret-bearing fields.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

_PLACEHOLDER_VALUES = frozenset({"change_me", "replace_with_a_generated_secret", ""})


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    app_base_url: str = "http://localhost:8080"
    database_url: str = ""
    artifact_root: str = "/data/artifacts"
    engine_url: str = "http://engine:8090"
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    nebius_model: str = "nvidia/nemotron-3-super-120b-a12b"
    provider_mode: str = "mock"
    nebius_vision_model: str = (
        ""  # a Nemotron VL model for reading banner images; empty = no vision (manual editor only)
    )
    page_mode: str = (
        "mock"  # "mock" (offline fixtures) or "tavily" (Tavily Extract fetches the owner's product page)
    )
    tavily_api_key: str = field(default="", repr=False)
    live_run_max_usd: Optional[str] = None
    max_provider_concurrency: int = 2
    nebius_completion_cap: int = (
        0  # per-call completion-token floor (0 = use what each caller asks for)
    )
    nebius_reasoning_effort: Optional[str] = (
        None  # none|minimal|low|medium|high|xhigh|max; ONE value for every method
    )
    _raw_env: dict = field(default_factory=dict, repr=False, compare=False)

    def validation_problems(self) -> list[str]:
        """Config consistency problems (not live reachability; that is `oa provider probe`)."""
        problems: list[str] = []
        if self.provider_mode not in ("mock", "nebius", "replay"):
            problems.append(f"PROVIDER_MODE={self.provider_mode!r} is not mock|nebius|replay")
        if self.provider_mode == "nebius":
            if not self._raw_env.get("NEBIUS_API_KEY"):
                problems.append("PROVIDER_MODE=nebius but NEBIUS_API_KEY is unset")
            if not self.live_run_max_usd:
                problems.append("PROVIDER_MODE=nebius but LIVE_RUN_MAX_USD is unset (spec 19.3)")
        if self.nebius_reasoning_effort not in (
            None,
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        ):
            problems.append(
                f"NEBIUS_REASONING_EFFORT={self.nebius_reasoning_effort!r} is not a documented value"
            )
        if self._raw_env.get("SESSION_SECRET", "") in _PLACEHOLDER_VALUES:
            problems.append("SESSION_SECRET unset/placeholder; run `oa config init`")
        return problems


def _read_dotenv(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v
    except FileNotFoundError:
        pass
    return out


def load_settings(dotenv_path: str = ".env", env: Optional[dict] = None) -> Settings:
    """Process environment wins over .env; .env fills the gaps. `env` replaces both (tests)."""
    env = dict(env) if env is not None else {**_read_dotenv(dotenv_path), **os.environ}
    return Settings(
        app_env=env.get("APP_ENV", "development"),
        app_base_url=env.get("APP_BASE_URL", "http://localhost:8080"),
        database_url=env.get("DATABASE_URL", ""),
        artifact_root=env.get("ARTIFACT_ROOT", "/data/artifacts"),
        engine_url=env.get("ENGINE_URL", "http://engine:8090"),
        nebius_base_url=env.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"),
        nebius_model=env.get("NEBIUS_MODEL", "nvidia/nemotron-3-super-120b-a12b"),
        provider_mode=env.get("PROVIDER_MODE", "mock"),
        nebius_vision_model=env.get("NEBIUS_VISION_MODEL", ""),
        page_mode=env.get("PAGE_MODE", "mock"),
        tavily_api_key=env.get("TAVILY_API_KEY", ""),
        live_run_max_usd=env.get("LIVE_RUN_MAX_USD") or None,
        max_provider_concurrency=int(env.get("MAX_PROVIDER_CONCURRENCY", "2")),
        nebius_reasoning_effort=env.get("NEBIUS_REASONING_EFFORT") or None,
        nebius_completion_cap=int(env.get("NEBIUS_COMPLETION_CAP") or 0),
        _raw_env=dict(env),
    )


def describe_settings_safely(s: Settings) -> list[str]:
    key_set = bool(s._raw_env.get("NEBIUS_API_KEY"))
    secret_set = s._raw_env.get("SESSION_SECRET", "") not in _PLACEHOLDER_VALUES
    mock = "  (MOCK: no live inference, no credits spent)" if s.provider_mode == "mock" else ""
    return [
        f"APP_ENV           = {s.app_env}",
        f"PROVIDER_MODE     = {s.provider_mode}{mock}",
        f"NEBIUS_BASE_URL   = {s.nebius_base_url}",
        f"NEBIUS_MODEL      = {s.nebius_model}",
        f"REASONING_EFFORT  = {s.nebius_reasoning_effort or '<provider default>'}",
        f"COMPLETION_CAP    = {s.nebius_completion_cap or '<per caller>'}",
        f"NEBIUS_API_KEY    = {'<set>' if key_set else '<unset>'}",
        f"LIVE_RUN_MAX_USD  = {s.live_run_max_usd or '<unset>'}",
        f"SESSION_SECRET    = {'<set, not shown>' if secret_set else '<unset/placeholder>'}",
        f"DATABASE_URL      = {'<set>' if s.database_url else '<unset>'}",
        f"ARTIFACT_ROOT     = {s.artifact_root}",
        f"ENGINE_URL        = {s.engine_url}",
    ]
