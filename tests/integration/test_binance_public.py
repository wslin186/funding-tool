"""Live tests against Binance public endpoints. Opt-in via `pytest -m integration`.

These hit production endpoints so they require network access. They do NOT need
an API key (all endpoints used here are public).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from funding_tool.core.exchanges.binance_usdm import build_binance_usdm_exchange

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_fetch_funding_rates_btcusdt_recent_week():
    ex = build_binance_usdm_exchange()
    end = datetime.now(UTC)
    start = end - timedelta(days=7)
    events = await ex.fetch_funding_rates("BTCUSDT", start, end)
    # BTCUSDT funds every 8h → expect ~21 events in 7 days; allow 18–24 for safety
    assert 15 <= len(events) <= 30
    # Each event must have a real mark_price merged in
    for ev in events:
        assert ev.mark_price > 0
        assert ev.rate is not None
        assert ev.interval_hours in (1, 2, 4, 8)


@pytest.mark.asyncio
async def test_fetch_funding_rates_pagination_one_year():
    """One-year window forces multiple paginated requests."""
    ex = build_binance_usdm_exchange()
    end = datetime.now(UTC)
    start = end - timedelta(days=365)
    events = await ex.fetch_funding_rates("BTCUSDT", start, end)
    # ~1095 events expected (365 * 3) — allow generous range
    assert len(events) >= 900
    # Monotonic increase, no duplicates
    timestamps = [ev.timestamp for ev in events]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)


@pytest.mark.asyncio
async def test_exchange_info_returns_interval_hours():
    ex = build_binance_usdm_exchange()
    hours = await ex.get_interval_hours("BTCUSDT")
    assert hours in (1, 2, 4, 8)


@pytest.mark.asyncio
async def test_unknown_symbol_raises():
    from funding_tool.core.errors import UnknownSymbolError
    ex = build_binance_usdm_exchange()
    end = datetime.now(UTC)
    start = end - timedelta(days=1)
    with pytest.raises(UnknownSymbolError):
        await ex.fetch_funding_rates("DEFINITELY_NOT_A_SYMBOL_XYZ", start, end)
