"""End-to-end CLI test: invokes `funding-tool backtest` against the real exchange.

Opt-in via `pytest -m integration`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.integration


def _yesterday_dates() -> tuple[str, str]:
    end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=2)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def test_backtest_btcusdt_base_mode_runs():
    start, end = _yesterday_dates()
    r = subprocess.run(
        [sys.executable, "-m", "funding_tool.cli",
         "backtest", "--symbol", "BTCUSDT", "--side", "LONG",
         "--start", start, "--end", end,
         "--size-mode", "BASE", "--size", "1",
         "--json"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["input"]["symbol"] == "BTCUSDT"
    assert data["event_count"] >= 4   # ≥4 settlements in 2 days for 8h interval


def test_backtest_rate_only_mode():
    start, end = _yesterday_dates()
    r = subprocess.run(
        [sys.executable, "-m", "funding_tool.cli",
         "backtest", "--symbol", "BTCUSDT", "--side", "SHORT",
         "--start", start, "--end", end,
         "--size-mode", "RATE_ONLY", "--json"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["total_quote"] is None
    assert data["total_base"] is None
