"""Typer entry point. Subcommands are wired up in tasks 16–17."""

from __future__ import annotations

import sys

import typer
from rich.console import Console

from funding_tool.core.errors import FundingToolError

app = typer.Typer(
    name="funding-tool",
    help="Binance USDT-M perpetual funding rate P&L calculator.",
    no_args_is_help=True,
)


@app.callback()
def _entry() -> None:
    """Top-level callback. Currently a no-op; reserved for global flags."""


def main() -> None:
    err_console = Console(stderr=True)
    try:
        app()
    except FundingToolError as exc:
        err_console.print(f"[red]error:[/] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
