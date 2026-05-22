"""`funding-tool cache ...` commands."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.table import Table

from funding_tool.cli.output import console
from funding_tool.core.cache import SqliteFundingRateCache

cache_app = typer.Typer(help="Inspect and clear the local funding-rate cache.")


def _default_cache_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "funding-tool" / "cache.sqlite"


@cache_app.command("info")
def cache_info() -> None:
    """Show row counts and coverage per symbol."""
    cache = SqliteFundingRateCache(_default_cache_path())
    stats = cache.stats()
    if not stats:
        console.print("rows: 0")
        return
    t = Table("Exchange", "Symbol", "Rows", "First", "Last")
    total = 0
    for row in stats:
        rows_count = cast("int", row["rows"])
        t.add_row(
            cast("str", row["exchange"]),
            cast("str", row["symbol"]),
            str(rows_count),
            cast("str | None", row["first"]) or "-",
            cast("str | None", row["last"]) or "-",
        )
        total += rows_count
    console.print(t)
    console.print(f"total rows: {total}")


@cache_app.command("clear")
def cache_clear(
    symbol: Annotated[str | None, typer.Option("--symbol")] = None,
) -> None:
    """Delete cached rows (entire cache, or one symbol)."""
    cache = SqliteFundingRateCache(_default_cache_path())
    n = cache.clear(symbol=symbol.upper() if symbol else None)
    console.print(f"[green]cleared[/] {n} rows")
