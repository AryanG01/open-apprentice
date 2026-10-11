from __future__ import annotations

from open_apprentice.config import Settings
from open_apprentice.providers.base import Provider
from open_apprentice.providers.mock import MockProvider


class MissingCredential(Exception):
    """Live mode requested without what spec 19.3 requires. Maps to ExitState.BLOCKED_NO_CREDENTIAL."""


def make_provider(settings: Settings, mock_script=None) -> Provider:
    if settings.provider_mode == "mock":
        return MockProvider(mock_script or {})
    if settings.provider_mode == "nebius":
        env = settings._raw_env
        if not env.get("NEBIUS_API_KEY"):
            raise MissingCredential("NEBIUS_API_KEY is not set; live integration NOT verified")
        if not settings.live_run_max_usd:
            raise MissingCredential("LIVE_RUN_MAX_USD is not set (spec 19.3)")
        from open_apprentice.providers.nebius import NebiusProvider

        def rate(k):
            return float(env[k]) if env.get(k) else None

        limit_field = "max_tokens"
        try:  # use what the live probe actually observed, if a report exists
            import json

            cap = json.load(open("docs/capabilities.json"))
            limit_field = cap["accepted_options"].get("completion_limit_field") or limit_field
        except (OSError, ValueError, KeyError):
            pass
        return NebiusProvider(
            base_url=settings.nebius_base_url,
            api_key=env["NEBIUS_API_KEY"],
            model=settings.nebius_model,
            limit_field=limit_field,
            reasoning_effort=settings.nebius_reasoning_effort,
            completion_floor=settings.nebius_completion_cap,
            input_usd_per_million=rate("INPUT_USD_PER_MILLION"),
            output_usd_per_million=rate("OUTPUT_USD_PER_MILLION"),
        )
    raise MissingCredential(f"provider mode {settings.provider_mode!r} has no factory yet")
