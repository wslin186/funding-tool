"""`funding-tool history` — Feature B."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from funding_tool.cli.output import (
    console,
    format_history_json,
    print_history_table,
    write_history_csv,
)
from funding_tool.core.account import run_account_history
from funding_tool.core.account_store import AccountStore, resolve_credentials
from funding_tool.core.errors import MissingCredentialsError, ValidationError
from funding_tool.core.exchanges.base import ExchangeProtocol
from funding_tool.core.models import ApiCredentials
from funding_tool.infra.time_util import parse_user_datetime


def get_exchange(exchange_name: str) -> ExchangeProtocol:
    from funding_tool.core.exchanges.binance_usdm import build_binance_usdm_exchange

    if exchange_name != "binance_usdm":
        raise ValidationError(f"unsupported exchange {exchange_name!r}")
    return build_binance_usdm_exchange()


def _default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "funding-tool" / "accounts.yaml"


def _prompt_for_credentials() -> ApiCredentials:
    """Interactive fallback (priority 5 of the credential resolution order).

    Only reached when --api-key, env vars, --account, and the default account
    all came up empty. The api_secret prompt hides input.
    """
    console.print(
        "[yellow]No credentials provided.[/] Enter API key and secret to continue.\n"
        "(Set up an account with [bold]funding-tool account add[/] to avoid this prompt.)"
    )
    api_key = typer.prompt("API key")
    api_secret = typer.prompt("API secret", hide_input=True)
    return ApiCredentials(api_key=api_key, api_secret=api_secret)


def history_command(
    start: Annotated[str, typer.Option("--start")],
    end: Annotated[str, typer.Option("--end")] = "now",
    account: Annotated[str | None, typer.Option("--account")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key")] = None,
    api_secret: Annotated[str | None, typer.Option("--api-secret")] = None,
    symbol: Annotated[str | None, typer.Option("--symbol")] = None,
    by_symbol: Annotated[bool, typer.Option("--by-symbol")] = False,
    by_month: Annotated[bool, typer.Option("--by-month")] = False,
    detail: Annotated[bool, typer.Option("--detail")] = False,
    exchange: Annotated[str, typer.Option("--exchange")] = "binance_usdm",
    json_out: Annotated[bool, typer.Option("--json")] = False,
    csv_path: Annotated[Path | None, typer.Option("--csv")] = None,
) -> None:
    """Fetch and aggregate real account funding-fee history."""
    import keyring as _keyring  # noqa: PLC0415

    store = AccountStore(config_path=_default_config_path(), keyring=_keyring)
    try:
        creds = resolve_credentials(
            store, cli_api_key=api_key, cli_api_secret=api_secret,
            env=dict(os.environ), account_name=account,
        )
    except MissingCredentialsError:
        # Priority 5: interactive prompt. resolve_credentials raises only when
        # nothing else worked, so this is the last fallback.
        creds = _prompt_for_credentials()

    start_dt = parse_user_datetime(start)
    end_dt = parse_user_datetime(end)

    ex = get_exchange(exchange)
    res = asyncio.run(run_account_history(
        creds=creds, exchange=ex,
        start=start_dt, end=end_dt,
        symbol=symbol.upper() if symbol else None,
    ))

    if csv_path is not None:
        write_history_csv(res, csv_path)
        console.print(f"[dim]wrote {len(res.records)} rows to {csv_path}[/]")
    if json_out:
        sys.stdout.write(format_history_json(res))
        sys.stdout.write("\n")
    else:
        if account:
            console.print(f"Account: {account} ({exchange})")
        print_history_table(res, by_symbol=by_symbol, by_month=by_month, detail=detail)
