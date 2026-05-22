"""`funding-tool account ...` commands."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table

from funding_tool.cli.output import console
from funding_tool.core.account_store import (
    AccountStore,
    PlaintextFallbackRequired,
)
from funding_tool.core.models import ApiCredentials, PermissionReport

account_app = typer.Typer(help="Manage credentials for one or more accounts.")


def _default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "funding-tool" / "accounts.yaml"


def _build_keyring() -> Any:
    import keyring as _keyring  # noqa: PLC0415

    return _keyring


def _verify_credentials_live(creds: ApiCredentials) -> PermissionReport:
    """Call Binance to confirm Futures read permission and read the permission bitmap.

    Returns the PermissionReport so callers can warn on trading/withdrawal flags.
    Tests monkeypatch this to return a controlled report.
    """
    import asyncio  # noqa: PLC0415

    from funding_tool.core.exchanges.binance_usdm import (  # noqa: PLC0415
        build_binance_usdm_exchange,
    )

    ex = build_binance_usdm_exchange()
    return asyncio.run(ex.verify_credentials(creds))


def _warn_about_permissions(report: PermissionReport) -> None:
    """Print red warnings if the key has more than read permission. Non-fatal."""
    if report.trading_enabled:
        console.print(
            "[yellow]Warning:[/] this API key has [bold]trading[/] enabled. "
            "For a read-only workflow, create a key restricted to Futures read."
        )
    if report.withdrawals_enabled:
        console.print(
            "[red]DANGER:[/] this API key has [bold]withdrawals enabled[/]. "
            "Disable withdrawals on this key NOW — funding-tool never needs that permission."
        )
    if report.spot_trading_enabled:
        console.print(
            "[yellow]Warning:[/] spot trading enabled. Consider a Futures-read-only key."
        )


@account_app.command("add")
def account_add(
    name: Annotated[str, typer.Option("--name", prompt=True)],
    api_key: Annotated[str | None, typer.Option("--api-key")] = None,
    api_secret: Annotated[str | None, typer.Option("--api-secret")] = None,
    exchange: Annotated[str, typer.Option("--exchange")] = "binance_usdm",
    skip_verify: Annotated[bool, typer.Option("--skip-verify",
        help="Skip live API verification (use for offline registration)")] = False,
) -> None:
    """Register a new named account (api_key + api_secret stored in keyring)."""
    if not api_key:
        api_key = typer.prompt("API key")
    if not api_secret:
        api_secret = typer.prompt("API secret", hide_input=True)

    creds = ApiCredentials(api_key=api_key, api_secret=api_secret)

    verified = False
    if not skip_verify:
        try:
            report = _verify_credentials_live(creds)
            verified = report.read_ok
        except Exception as exc:  # noqa: BLE001  # surface any verify failure to user
            console.print(f"[red]verification failed:[/] {exc}")
            raise typer.Exit(1) from exc
        _warn_about_permissions(report)

    store = AccountStore(config_path=_default_config_path(), keyring=_build_keyring())
    try:
        store.add(name=name, exchange=exchange, credentials=creds, verified=verified)
    except PlaintextFallbackRequired:
        console.print(
            "[yellow]Warning:[/] no keyring backend available on this system.\n"
            "Plaintext storage in YAML (chmod 0600) is the only alternative."
        )
        if not typer.confirm("Store API key and secret in plaintext YAML?", default=False):
            console.print("Aborted.")
            raise typer.Exit(1) from None
        store.add(
            name=name, exchange=exchange, credentials=creds,
            verified=verified, allow_plaintext=True,
        )

    console.print(f"[green]added account[/] {name}")


@account_app.command("list")
def account_list() -> None:
    """List configured accounts (secrets never displayed)."""
    store = AccountStore(config_path=_default_config_path(), keyring=_build_keyring())
    default = store.get_default_name()
    accounts = store.list_accounts()
    if not accounts:
        console.print("[dim]no accounts configured[/]")
        return
    table = Table("", "Name", "Exchange", "Created", "Verified")
    for a in accounts:
        marker = "*" if a.name == default else ""
        verified = (
            a.permissions_verified_at.strftime("%Y-%m-%d")
            if a.permissions_verified_at
            else "-"
        )
        table.add_row(marker, a.name, a.exchange,
                      a.created_at.strftime("%Y-%m-%d"), verified)
    console.print(table)


@account_app.command("remove")
def account_remove(
    name: Annotated[str, typer.Argument()],
) -> None:
    """Remove account from YAML and keyring."""
    store = AccountStore(config_path=_default_config_path(), keyring=_build_keyring())
    store.remove(name)
    console.print(f"[green]removed account[/] {name}")


@account_app.command("use")
def account_use(
    name: Annotated[str, typer.Argument()],
) -> None:
    """Set the default account."""
    store = AccountStore(config_path=_default_config_path(), keyring=_build_keyring())
    store.set_default(name)
    console.print(f"[green]default →[/] {name}")


@account_app.command("test")
def account_test(
    name: Annotated[str, typer.Argument()],
) -> None:
    """Test connectivity and read permission for an account."""
    store = AccountStore(config_path=_default_config_path(), keyring=_build_keyring())
    creds = store.get_credentials(name)
    try:
        _verify_credentials_live(creds)
    except Exception as exc:  # noqa: BLE001  # surface any verify failure to user
        console.print(f"[red]FAIL:[/] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]OK:[/] {name} connectivity + Futures read permission verified")
