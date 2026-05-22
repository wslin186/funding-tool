"""Output formatters for CLI commands. rich tables, JSON, CSV."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from funding_tool.core.models import BacktestResult, HistoryResult

console = Console()


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")


def format_backtest_json(res: BacktestResult) -> str:
    return json.dumps(asdict(res), default=_json_default, indent=2)


def format_history_json(res: HistoryResult) -> str:
    return json.dumps(asdict(res), default=_json_default, indent=2)


def write_backtest_csv(res: BacktestResult, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "timestamp", "symbol", "rate", "mark_price",
            "quantity_base", "notional_quote", "payment_quote",
        ])
        for p in res.payments:
            w.writerow([
                p.event.timestamp.isoformat(),
                p.event.symbol,
                str(p.event.rate),
                str(p.event.mark_price),
                str(p.quantity_base),
                str(p.notional_quote),
                str(p.payment_quote),
            ])


def write_history_csv(res: HistoryResult, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "symbol", "amount_usdt", "tran_id"])
        for r in res.records:
            w.writerow([
                r.timestamp.isoformat(), r.symbol,
                str(r.amount_usdt), r.tran_id,
            ])


def print_backtest_table(res: BacktestResult, *, detail: bool = False) -> None:
    inp = res.input
    days = (inp.end - inp.start).days
    console.print(
        f"[bold]Backtest {inp.symbol} {inp.side}[/]  "
        f"{inp.start.date()} → {inp.end.date()} ({days} days)"
    )
    if inp.size_mode == "RATE_ONLY":
        console.print("Size:    [dim]RATE_ONLY[/] (no notional)")
    else:
        console.print(f"Size:    {inp.size} ({inp.size_mode} mode)")

    summary = Table(show_header=False, box=None, pad_edge=False)
    if res.total_quote is not None:
        summary.add_row("Total income (USDT)", f"{res.total_quote:+.4f}")
        summary.add_row("Total income (base)", f"{res.total_base:+.8f}")
    summary.add_row("Cumulative rate", f"{res.cumulative_rate_pct:+.4f}%")
    summary.add_row("APR (annualized)", f"{res.apr * 100:+.4f}%")
    summary.add_row("Settlements", str(res.event_count))
    summary.add_row("Average rate", f"{res.avg_rate * 100:+.6f}%")
    console.print(summary)

    if detail and res.payments:
        t = Table("Time (UTC)", "Rate", "Mark Price", "Payment")
        for p in res.payments:
            t.add_row(
                p.event.timestamp.strftime("%Y-%m-%d %H:%M"),
                f"{p.event.rate * 100:+.4f}%",
                f"{p.event.mark_price:.2f}",
                f"{p.payment_quote:+.4f}",
            )
        console.print(t)


def print_history_table(
    res: HistoryResult, *, by_symbol: bool = False, by_month: bool = False,
    detail: bool = False,
) -> None:
    days = (res.end - res.start).days
    console.print(
        f"Range:   {res.start.date()} → {res.end.date()} ({days} days)"
    )
    console.print(f"\nTotal funding P&L:   [bold]{res.total:+.4f}[/] USDT")
    console.print(f"Settlements:         {len(res.records)}")

    if by_symbol and res.by_symbol:
        t = Table("Symbol", "Amount", title="By symbol")
        for sym, amt in sorted(res.by_symbol.items(), key=lambda kv: -kv[1]):
            t.add_row(sym, f"{amt:+.4f}")
        console.print(t)

    if by_month and res.by_month:
        t = Table("Month", "Amount", title="By month")
        for month, amt in sorted(res.by_month.items()):
            t.add_row(month, f"{amt:+.4f}")
        console.print(t)

    if detail and res.records:
        t = Table("Time (UTC)", "Symbol", "Amount", "Tran ID")
        for r in res.records:
            t.add_row(
                r.timestamp.strftime("%Y-%m-%d %H:%M"),
                r.symbol,
                f"{r.amount_usdt:+.4f}",
                r.tran_id,
            )
        console.print(t)
