import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from funding_tool.core.cache import SqliteFundingRateCache
from funding_tool.core.exchanges.binance_usdm import BinanceUsdmExchange

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def exchange(tmp_path):
    cache = SqliteFundingRateCache(tmp_path / "cache.db")
    return BinanceUsdmExchange(cache=cache, base_url="https://fapi.example.com")


@pytest.mark.asyncio
async def test_fetch_funding_rates_merges_mark_price(exchange):
    funding_data = json.loads((FIXTURES / "funding_rates_sample.json").read_text())
    klines_data = json.loads((FIXTURES / "mark_price_klines_sample.json").read_text())

    with respx.mock(base_url="https://fapi.example.com") as mock:
        mock.get("/fapi/v1/fundingRate").mock(return_value=httpx.Response(200, json=funding_data))
        mock.get("/fapi/v1/markPriceKlines").mock(return_value=httpx.Response(200, json=klines_data))
        mock.get("/fapi/v1/exchangeInfo").mock(return_value=httpx.Response(200, json={
            "symbols": [{"symbol": "BTCUSDT", "fundingIntervalHours": 8}]
        }))

        events = await exchange.fetch_funding_rates(
            "BTCUSDT",
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 2, tzinfo=UTC),
        )

    assert len(events) == 3
    assert events[0].rate == Decimal("0.0001")
    assert events[0].mark_price == Decimal("50000.00")
    assert events[0].interval_hours == 8
    assert events[1].rate == Decimal("-0.00005")
    assert events[1].mark_price == Decimal("50050.00")


@pytest.mark.asyncio
async def test_fetch_funding_rates_uses_cache(exchange):
    """Second call within cached window must not hit HTTP."""
    funding_data = json.loads((FIXTURES / "funding_rates_sample.json").read_text())
    klines_data = json.loads((FIXTURES / "mark_price_klines_sample.json").read_text())

    with respx.mock(base_url="https://fapi.example.com") as mock:
        funding_route = mock.get("/fapi/v1/fundingRate").mock(return_value=httpx.Response(200, json=funding_data))
        mock.get("/fapi/v1/markPriceKlines").mock(return_value=httpx.Response(200, json=klines_data))
        mock.get("/fapi/v1/exchangeInfo").mock(return_value=httpx.Response(200, json={
            "symbols": [{"symbol": "BTCUSDT", "fundingIntervalHours": 8}]
        }))

        await exchange.fetch_funding_rates(
            "BTCUSDT",
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 2, tzinfo=UTC),
        )
        first_call_count = funding_route.call_count

        # Second call — same window — should be served from cache
        events = await exchange.fetch_funding_rates(
            "BTCUSDT",
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 2, tzinfo=UTC),
        )

    assert len(events) == 3
    assert funding_route.call_count == first_call_count  # no additional HTTP


@pytest.mark.asyncio
async def test_fetch_funding_rates_missing_mark_price_raises(exchange):
    """If markPriceKlines doesn't cover a funding timestamp, raise ExchangeError."""
    funding_data = [
        {"symbol": "BTCUSDT", "fundingTime": 1735689600000, "fundingRate": "0.0001"},
    ]
    # klines missing — empty array
    with respx.mock(base_url="https://fapi.example.com") as mock:
        mock.get("/fapi/v1/fundingRate").mock(return_value=httpx.Response(200, json=funding_data))
        mock.get("/fapi/v1/markPriceKlines").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/fapi/v1/exchangeInfo").mock(return_value=httpx.Response(200, json={
            "symbols": [{"symbol": "BTCUSDT", "fundingIntervalHours": 8}]
        }))

        from funding_tool.core.errors import ExchangeError
        with pytest.raises(ExchangeError, match="mark price"):
            await exchange.fetch_funding_rates(
                "BTCUSDT",
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 2, tzinfo=UTC),
            )


@pytest.mark.asyncio
async def test_fetch_funding_rates_floor_lookup_within_tolerance(exchange):
    """If no kline at exact funding timestamp, use the nearest previous kline
    within one interval. This handles minor exchange-side alignment quirks."""
    funding_time_ms = 1735689600000  # 2025-01-01 00:00 UTC
    funding_data = [
        {"symbol": "BTCUSDT", "fundingTime": funding_time_ms, "fundingRate": "0.0001"},
    ]
    # Kline open_time is 1 hour BEFORE funding_time, well within the 8h interval tolerance.
    earlier_kline_time = funding_time_ms - 3_600_000  # one hour earlier
    klines_data = [
        [earlier_kline_time, "49000.00", "49100.00", "48900.00", "49050.00",
         "0", earlier_kline_time + 3_599_999, "0", 0, "0", "0", "0"],
    ]
    with respx.mock(base_url="https://fapi.example.com") as mock:
        mock.get("/fapi/v1/fundingRate").mock(return_value=httpx.Response(200, json=funding_data))
        mock.get("/fapi/v1/markPriceKlines").mock(return_value=httpx.Response(200, json=klines_data))
        mock.get("/fapi/v1/exchangeInfo").mock(return_value=httpx.Response(200, json={
            "symbols": [{"symbol": "BTCUSDT", "fundingIntervalHours": 8}]
        }))

        events = await exchange.fetch_funding_rates(
            "BTCUSDT",
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 2, tzinfo=UTC),
        )

    assert len(events) == 1
    assert events[0].mark_price == Decimal("49000.00")
