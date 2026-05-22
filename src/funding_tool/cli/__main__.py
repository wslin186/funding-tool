"""Typer entry point."""

from __future__ import annotations

import sys

import typer
from rich.console import Console

from funding_tool.cli.account_cmd import account_app
from funding_tool.cli.backtest_cmd import backtest_command
from funding_tool.cli.cache_cmd import cache_app
from funding_tool.cli.history_cmd import history_command
from funding_tool.core.errors import FundingToolError

app = typer.Typer(
    name="funding-tool",
    help="Binance USDT-M perpetual funding rate P&L calculator.",
    no_args_is_help=True,
)

app.command(name="backtest")(backtest_command)
app.command(name="history")(history_command)
app.add_typer(account_app, name="account")
app.add_typer(cache_app, name="cache")


def main() -> None:
    err_console = Console(stderr=True)
    try:
        app()
    except FundingToolError as exc:
        err_console.print(f"[red]error:[/] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
