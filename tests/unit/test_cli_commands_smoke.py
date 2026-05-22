"""Smoke tests for backtest and history commands using typer's CliRunner.

These tests use a FakeExchange via dependency injection from the cli module's
`get_exchange` factory (monkeypatched in tests).
"""

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from funding_tool.cli.__main__ import app
from funding_tool.core.models import FundingEvent, IncomeRecord
from tests.fakes import FakeExchange

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class _Result:
    """Thin wrapper around click's Result that strips ANSI from stdout.

    Rich's help output wraps each character of option names with ANSI escape
    sequences (e.g. ``--symbol`` becomes ``\\x1b[1;36m-\\x1b[0m\\x1b[1;36m-symbol\\x1b[0m``),
    so ``"--symbol" in result.stdout`` fails. Stripping ANSI codes from the
    captured output makes substring assertions reliable without changing
    production behavior.
    """

    def __init__(self, raw):  # type: ignore[no-untyped-def]
        self._raw = raw
        self.exit_code = raw.exit_code
        self.exception = raw.exception
        self.stdout = _ANSI_RE.sub("", raw.stdout)


class _Runner(CliRunner):
    def invoke(self, *args, **kwargs):  # type: ignore[no-untyped-def, override]
        kwargs.setdefault("color", False)
        return _Result(super().invoke(*args, **kwargs))


runner = _Runner()


@pytest.fixture
def _stub_exchange(monkeypatch: pytest.MonkeyPatch) -> FakeExchange:
    """Replace the CLI's exchange factory with a FakeExchange we control."""
    ex = FakeExchange(funding_rates=[
        FundingEvent(
            timestamp=datetime(2026, 1, 1, 8, tzinfo=UTC),
            symbol="BTCUSDT", rate=Decimal("0.0001"),
            mark_price=Decimal("50000"), interval_hours=8,
        ),
    ], income_records=[
        IncomeRecord(
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            symbol="BTCUSDT", amount_usdt=Decimal("1.5"), tran_id="t1",
        ),
    ])

    from funding_tool.cli import backtest_cmd, history_cmd
    monkeypatch.setattr(backtest_cmd, "get_exchange", lambda exchange_name: ex)
    monkeypatch.setattr(history_cmd, "get_exchange", lambda exchange_name: ex)
    return ex


def test_backtest_help():
    result = runner.invoke(app, ["backtest", "--help"])
    assert result.exit_code == 0
    assert "--symbol" in result.stdout
    assert "--side" in result.stdout
    assert "--size-mode" in result.stdout


def test_backtest_runs_with_minimal_flags(_stub_exchange: FakeExchange):
    result = runner.invoke(app, [
        "backtest",
        "--symbol", "BTCUSDT",
        "--side", "LONG",
        "--start", "2026-01-01",
        "--end", "2026-01-02",
        "--size-mode", "BASE",
        "--size", "1",
    ])
    assert result.exit_code == 0, result.stdout
    assert "Backtest BTCUSDT LONG" in result.stdout
    assert "Settlements" in result.stdout


def test_backtest_json_output(_stub_exchange: FakeExchange):
    result = runner.invoke(app, [
        "backtest", "--symbol", "BTCUSDT", "--side", "LONG",
        "--start", "2026-01-01", "--end", "2026-01-02",
        "--size-mode", "BASE", "--size", "1", "--json",
    ])
    assert result.exit_code == 0
    import json
    data = json.loads(result.stdout)
    assert data["input"]["symbol"] == "BTCUSDT"


def test_backtest_csv_export(_stub_exchange: FakeExchange, tmp_path: Path):
    target = tmp_path / "out.csv"
    result = runner.invoke(app, [
        "backtest", "--symbol", "BTCUSDT", "--side", "LONG",
        "--start", "2026-01-01", "--end", "2026-01-02",
        "--size-mode", "BASE", "--size", "1",
        "--csv", str(target),
    ])
    assert result.exit_code == 0
    assert target.exists()
    assert "BTCUSDT" in target.read_text()


def test_backtest_now_expansion(_stub_exchange: FakeExchange):
    """--end now should be expanded by CLI, not passed to service."""
    result = runner.invoke(app, [
        "backtest", "--symbol", "BTCUSDT", "--side", "LONG",
        "--start", "2026-01-01", "--end", "now",
        "--size-mode", "BASE", "--size", "1",
    ])
    assert result.exit_code == 0


def test_backtest_rate_only_no_size_required(_stub_exchange: FakeExchange):
    result = runner.invoke(app, [
        "backtest", "--symbol", "BTCUSDT", "--side", "LONG",
        "--start", "2026-01-01", "--end", "2026-01-02",
        "--size-mode", "RATE_ONLY",
    ])
    assert result.exit_code == 0


def test_history_help():
    result = runner.invoke(app, ["history", "--help"])
    assert result.exit_code == 0
    assert "--account" in result.stdout
    assert "--start" in result.stdout


def test_history_with_explicit_creds(
    _stub_exchange: FakeExchange, monkeypatch: pytest.MonkeyPatch,
):
    result = runner.invoke(app, [
        "history",
        "--api-key", "K", "--api-secret", "S",
        "--start", "2026-01-01", "--end", "2026-02-01",
        "--by-symbol",
    ])
    assert result.exit_code == 0, result.stdout
    assert "Total funding P&L" in result.stdout
    assert "BTCUSDT" in result.stdout


def test_history_prompts_when_no_credentials_resolve(
    _stub_exchange: FakeExchange,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """No --api-key, no env, no --account, no default → interactive prompt fires."""
    # Redirect account YAML to an empty tmp_path so default-account lookup yields None.
    from funding_tool.cli import history_cmd
    monkeypatch.setattr(
        history_cmd, "_default_config_path", lambda: tmp_path / "accounts.yaml",
    )
    # Strip env vars that resolve_credentials inspects so we fall through to prompt:
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)

    result = runner.invoke(
        app,
        ["history", "--start", "2026-01-01", "--end", "2026-02-01"],
        input="prompt_key\nprompt_secret\n",
    )
    assert result.exit_code == 0, result.stdout
    assert "No credentials provided" in result.stdout
    assert "Total funding P&L" in result.stdout


def test_history_named_account_with_missing_keyring_does_not_prompt(
    _stub_exchange: FakeExchange,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """If --account is given but the keyring entry is gone, error — don't prompt silently."""
    yaml_path = tmp_path / "accounts.yaml"
    # Account in YAML, but no matching keyring entries → get_credentials raises
    # MissingCredentialsError. The CLI must surface that, not prompt.
    yaml_path.write_text(
        "default: my-main\n"
        "accounts:\n"
        "  my-main:\n"
        "    exchange: binance_usdm\n"
        "    api_key_ref: 'keyring:funding-tool/my-main:key'\n"
        "    secret_ref: 'keyring:funding-tool/my-main:secret'\n"
        "    created_at: 2026-05-22T10:00:00+00:00\n"
        "    permissions_verified_at: null\n"
    )

    from funding_tool.cli import history_cmd
    monkeypatch.setattr(history_cmd, "_default_config_path", lambda: yaml_path)

    # Use a fake keyring with no entries — but we also need history_command to
    # construct its AccountStore using *this* keyring. Patch the AccountStore
    # constructor at the call site (history_cmd) so it uses our fake.
    from funding_tool.core.account_store import AccountStore as _RealStore

    class _EmptyKeyring:
        def get_password(self, s: str, u: str) -> str | None:
            return None

        def set_password(self, s: str, u: str, v: str) -> None: ...

        def delete_password(self, s: str, u: str) -> None: ...

    def _store_factory(*, config_path, keyring=None):  # type: ignore[no-untyped-def]
        return _RealStore(config_path=config_path, keyring=_EmptyKeyring())

    monkeypatch.setattr(history_cmd, "AccountStore", _store_factory, raising=False)

    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)

    result = runner.invoke(
        app,
        ["history", "--start", "2026-01-01", "--end", "2026-02-01"],
    )
    assert result.exit_code != 0
    # CliRunner invokes app() directly (not main()), so the FundingToolError
    # surfaces as result.exception. Verify it's the right error from
    # AccountStore.get_credentials, NOT a silent prompt fallthrough.
    from funding_tool.core.errors import MissingCredentialsError

    assert isinstance(result.exception, MissingCredentialsError)
    assert "missing" in str(result.exception).lower()


def test_backtest_invalid_size_gives_clean_error():
    """Bad --size should produce a typer error, not a Python traceback."""
    import decimal

    result = runner.invoke(app, [
        "backtest",
        "--symbol", "BTCUSDT", "--side", "LONG",
        "--start", "2026-01-01", "--end", "2026-01-02",
        "--size-mode", "BASE", "--size", "not-a-number",
    ])
    # typer.BadParameter -> SystemExit(2). Importantly, the underlying
    # decimal.InvalidOperation must NOT escape as the captured exception
    # (that would mean main() would show a raw traceback).
    assert result.exit_code == 2
    assert not isinstance(result.exception, decimal.InvalidOperation)
