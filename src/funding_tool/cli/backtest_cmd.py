"""`funding-tool backtest` — Feature A."""

from __future__ import annotations

import asyncio
import decimal
import sys
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from funding_tool.cli.output import (
    console,
    format_backtest_json,
    print_backtest_table,
    write_backtest_csv,
)
from funding_tool.core.backtest import run_backtest
from funding_tool.core.errors import ValidationError
from funding_tool.core.exchanges.base import ExchangeProtocol
from funding_tool.core.models import BacktestInput
from funding_tool.infra.time_util import parse_user_datetime


def get_exchange(exchange_name: str) -> ExchangeProtocol:
    """Default factory: build BinanceUsdmExchange. Overridden in tests."""
    from funding_tool.core.exchanges.binance_usdm import build_binance_usdm_exchange

    if exchange_name != "binance_usdm":
        raise ValidationError(f"unsupported exchange {exchange_name!r}")
    return build_binance_usdm_exchange()


def backtest_command(
    symbol: Annotated[str, typer.Option("--symbol")],
    side: Annotated[str, typer.Option("--side", help="LONG or SHORT")],
    start: Annotated[str, typer.Option("--start", help="YYYY-MM-DD or ISO-8601 with TZ")],
    size_mode: Annotated[str, typer.Option("--size-mode", help="BASE | QUOTE | RATE_ONLY")],
    end: Annotated[str, typer.Option("--end")] = "now",
    size: Annotated[
        str | None,
        typer.Option("--size", help="position size (required unless RATE_ONLY)"),
    ] = None,
    exchange: Annotated[str, typer.Option("--exchange")] = "binance_usdm",
    detail: Annotated[bool, typer.Option("--detail")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="emit JSON to stdout")] = False,
    csv_path: Annotated[Path | None, typer.Option("--csv", help="write detail rows to CSV")] = None,
) -> None:
    """Run a hypothetical funding-rate backtest."""
    side_u = side.upper()
    mode_u = size_mode.upper()
    if side_u not in ("LONG", "SHORT"):
        raise typer.BadParameter("--side must be LONG or SHORT")
    if mode_u not in ("BASE", "QUOTE", "RATE_ONLY"):
        raise typer.BadParameter("--size-mode must be BASE, QUOTE, or RATE_ONLY")

    size_dec: Decimal | None
    if mode_u == "RATE_ONLY":
        size_dec = None
    else:
        if size is None:
            raise typer.BadParameter(f"--size is required for {mode_u} mode")
        try:
            size_dec = Decimal(size)
        except (decimal.InvalidOperation, ValueError) as exc:
            raise typer.BadParameter(f"--size must be a number, got {size!r}") from exc

    start_dt = parse_user_datetime(start)
    end_dt = parse_user_datetime(end)

    inp = BacktestInput(
        symbol=symbol.upper(), side=side_u,  # type: ignore[arg-type]
        start=start_dt, end=end_dt,
        size_mode=mode_u, size=size_dec,  # type: ignore[arg-type]
    )

    ex = get_exchange(exchange)
    res = asyncio.run(run_backtest(inp, exchange=ex))

    if csv_path is not None:
        write_backtest_csv(res, csv_path)
        console.print(f"[dim]wrote {len(res.payments)} rows to {csv_path}[/]")
    if json_out:
        sys.stdout.write(format_backtest_json(res))
        sys.stdout.write("\n")
    else:
        print_backtest_table(res, detail=detail)
