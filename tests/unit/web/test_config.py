import pytest
from funding_tool.web.config import Settings, load_settings


def test_https_origin_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FUNDING_PUBLIC_ORIGIN", "http://example.com")
    monkeypatch.setenv("FUNDING_AUTH_USER", "u")
    monkeypatch.setenv("FUNDING_AUTH_PASSWORD_HASH", "$2b$04$abc")
    with pytest.raises(ValueError, match="https://"):
        load_settings()


def test_settings_built_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("FUNDING_PUBLIC_ORIGIN", "https://example.com")
    monkeypatch.setenv("FUNDING_AUTH_USER", "admin")
    monkeypatch.setenv("FUNDING_AUTH_PASSWORD_HASH", "$2b$04$" + "a" * 53)
    monkeypatch.setenv("FUNDING_DB_PATH", str(tmp_path / "s.sqlite"))
    monkeypatch.setenv("FUNDING_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("FUNDING_TASKS_DIR", str(tmp_path / "tasks"))
    s = load_settings()
    assert s.public_origin == "https://example.com"
    assert s.auth_user == "admin"
    assert isinstance(s, Settings)


def test_missing_required_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FUNDING_PUBLIC_ORIGIN", raising=False)
    with pytest.raises(KeyError):
        load_settings()
