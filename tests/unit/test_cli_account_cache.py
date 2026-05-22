"""Smoke tests for the account and cache CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from funding_tool.cli.__main__ import app
from funding_tool.core.models import PermissionReport

runner = CliRunner()


class _FakeKeyring:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, s: str, u: str) -> str | None:
        return self._store.get((s, u))

    def set_password(self, s: str, u: str, v: str) -> None:
        self._store[(s, u)] = v

    def delete_password(self, s: str, u: str) -> None:
        self._store.pop((s, u), None)


def _ok_report() -> PermissionReport:
    """A read-only PermissionReport — what tests get back from the stubbed live call."""
    return PermissionReport(
        read_ok=True,
        trading_enabled=False,
        withdrawals_enabled=False,
        spot_trading_enabled=False,
    )


@pytest.fixture
def _patch_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect account YAML and cache DB to tmp_path; install fake keyring."""
    yaml_path = tmp_path / "accounts.yaml"
    cache_path = tmp_path / "cache.sqlite"

    from funding_tool.cli import account_cmd, cache_cmd
    monkeypatch.setattr(account_cmd, "_default_config_path", lambda: yaml_path)
    monkeypatch.setattr(account_cmd, "_build_keyring", lambda: _FakeKeyring())
    monkeypatch.setattr(cache_cmd, "_default_cache_path", lambda: cache_path)
    # Skip live API verification so tests don't make network calls. The stub
    # must return a PermissionReport because account_add inspects .read_ok and
    # _warn_about_permissions reads the advisory flags.
    monkeypatch.setattr(account_cmd, "_verify_credentials_live", lambda creds: _ok_report())
    return tmp_path


def test_account_add_and_list(_patch_paths: Path):
    r = runner.invoke(app, [
        "account", "add", "--name", "my-main",
        "--api-key", "K1", "--api-secret", "S1",
        "--skip-verify",
    ])
    assert r.exit_code == 0, r.stdout
    r = runner.invoke(app, ["account", "list"])
    assert r.exit_code == 0
    assert "my-main" in r.stdout
    assert "S1" not in r.stdout  # secret never displayed


def test_account_remove(_patch_paths: Path):
    runner.invoke(app, ["account", "add", "--name", "x",
                         "--api-key", "K", "--api-secret", "S", "--skip-verify"])
    r = runner.invoke(app, ["account", "remove", "x"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["account", "list"])
    assert "x" not in r.stdout


def test_account_use_sets_default(_patch_paths: Path):
    runner.invoke(app, ["account", "add", "--name", "a",
                         "--api-key", "K1", "--api-secret", "S1", "--skip-verify"])
    runner.invoke(app, ["account", "add", "--name", "b",
                         "--api-key", "K2", "--api-secret", "S2", "--skip-verify"])
    r = runner.invoke(app, ["account", "use", "b"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["account", "list"])
    # "default" or "*" marker should appear next to b
    assert "b" in r.stdout


def test_cache_info_empty(_patch_paths: Path):
    r = runner.invoke(app, ["cache", "info"])
    assert r.exit_code == 0
    assert "0" in r.stdout  # zero rows


def test_cache_clear(_patch_paths: Path):
    r = runner.invoke(app, ["cache", "clear"])
    assert r.exit_code == 0
