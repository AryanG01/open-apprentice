import os
import stat

from open_apprentice.bootstrap import init_env_file
from open_apprentice.config import describe_settings_safely, load_settings


def _example(tmp_path):
    ex = tmp_path / ".env.example"
    ex.write_text(
        "DATABASE_URL=postgresql+psycopg://apprentice:change_me@db:5432/apprentice\n"
        "POSTGRES_PASSWORD=change_me\nSESSION_SECRET=replace_with_a_generated_secret\n"
        "NEBIUS_API_KEY=\nPROVIDER_MODE=mock\n"
    )
    return ex


def test_init_generates_secrets_and_keeps_db_consistent(tmp_path):
    ex, env = _example(tmp_path), tmp_path / ".env"
    res = init_env_file(str(env), str(ex))
    assert res.ok
    vals = dict(l.split("=", 1) for l in env.read_text().splitlines())
    assert vals["SESSION_SECRET"] not in ("", "replace_with_a_generated_secret")
    assert vals["POSTGRES_PASSWORD"] != "change_me"
    assert f":{vals['POSTGRES_PASSWORD']}@" in vals["DATABASE_URL"]
    assert stat.S_IMODE(os.stat(env).st_mode) == 0o600
    for m in res.messages:  # secrets never printed
        assert vals["SESSION_SECRET"] not in m and vals["POSTGRES_PASSWORD"] not in m


def test_init_preserves_user_values_and_is_idempotent(tmp_path):
    ex, env = _example(tmp_path), tmp_path / ".env"
    env.write_text("NEBIUS_API_KEY=user-key\nPROVIDER_MODE=nebius\n")
    init_env_file(str(env), str(ex))
    first = env.read_text()
    init_env_file(str(env), str(ex))
    assert env.read_text() == first
    assert "NEBIUS_API_KEY=user-key" in first and "PROVIDER_MODE=nebius" in first


def test_describe_never_prints_secrets(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "sk-super-secret")
    monkeypatch.setenv("SESSION_SECRET", "hunter2-hunter2")
    out = "\n".join(describe_settings_safely(load_settings(dotenv_path="/nonexistent/.env")))
    assert "sk-super-secret" not in out and "hunter2" not in out


def test_live_mode_requires_key_and_ceiling(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "nebius")
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("LIVE_RUN_MAX_USD", raising=False)
    probs = load_settings(
        dotenv_path="/nonexistent/.env"
    ).validation_problems()  # hermetic: never read the developer's real .env
    assert any("NEBIUS_API_KEY" in p for p in probs)
    assert any("LIVE_RUN_MAX_USD" in p for p in probs)


def test_dotenv_fills_gaps_but_env_wins(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("PROVIDER_MODE=replay\nNEBIUS_MODEL=from-file\nSESSION_SECRET=abc\n")
    monkeypatch.setenv("NEBIUS_MODEL", "from-env")
    monkeypatch.delenv("PROVIDER_MODE", raising=False)
    s = load_settings(str(f))
    assert s.provider_mode == "replay" and s.nebius_model == "from-env"


def test_reasoning_effort_must_be_a_documented_value(monkeypatch):
    monkeypatch.setenv("NEBIUS_REASONING_EFFORT", "turbo")
    assert any(
        "REASONING_EFFORT" in p
        for p in load_settings(dotenv_path="/nonexistent").validation_problems()
    )
    monkeypatch.setenv("NEBIUS_REASONING_EFFORT", "low")
    assert not any(
        "REASONING_EFFORT" in p
        for p in load_settings(dotenv_path="/nonexistent").validation_problems()
    )
