"""Binance USDT-M Futures exchange implementation."""

from __future__ import annotations

import bisect
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from funding_tool.core.cache import SqliteFundingRateCache
from funding_tool.core.errors import ExchangeError, UnknownSymbolError
from funding_tool.core.models import (
    ApiCredentials,
    FundingEvent,
    IncomeRecord,
    PermissionReport,
)
from funding_tool.infra.http import HttpClient
from funding_tool.infra.time_util import from_ms, to_ms


class BinanceUsdmExchange:
    """Binance USDT-Margined Futures.

    Funding events are built by joining:
      A) /fapi/v1/fundingRate  -> (fundingTime, fundingRate)
      B) /fapi/v1/markPriceKlines -> mark price at the same timestamps
    plus C) /fapi/v1/exchangeInfo -> fundingIntervalHours (per symbol, current value)
    """

    name = "binance_usdm"

    def __init__(
        self,
        cache: SqliteFundingRateCache,
        base_url: str = "https://fapi.binance.com",
    ) -> None:
        self._cache = cache
        self._base_url = base_url
        self._interval_cache: dict[str, int] = {}

    async def fetch_funding_rates(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[FundingEvent]:
        async with HttpClient(self._base_url) as http:
            interval = await self._get_interval(http, symbol)
            gaps = await self._cache.missing_ranges(self.name, symbol, start, end)
            for gap_start, gap_end in gaps:
                rates = await self._fetch_rate_pages(http, symbol, gap_start, gap_end)
                if not rates:
                    continue
                klines = await self._fetch_klines(http, symbol, gap_start, gap_end, interval)
                events = self._merge(symbol, rates, klines, interval)
                await self._cache.put(self.name, symbol, events)
        return await self._cache.get(self.name, symbol, start, end)

    async def _get_interval(self, http: HttpClient, symbol: str) -> int:
        if symbol in self._interval_cache:
            return self._interval_cache[symbol]
        info = await http.get_json("/fapi/v1/exchangeInfo")
        symbols = info.get("symbols", []) if isinstance(info, dict) else []
        for s in symbols:
            if isinstance(s, dict) and s.get("symbol") == symbol:
                interval = int(s.get("fundingIntervalHours", 8))
                self._interval_cache[symbol] = interval
                return interval
        raise UnknownSymbolError(f"symbol {symbol} not found in exchangeInfo")

    async def _fetch_rate_pages(
        self, http: HttpClient, symbol: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        all_rates: list[dict[str, Any]] = []
        cursor_ms = to_ms(start)
        end_ms = to_ms(end)
        while cursor_ms <= end_ms:
            batch = await http.get_json(
                "/fapi/v1/fundingRate",
                params={
                    "symbol": symbol,
                    "startTime": cursor_ms,
                    "endTime": end_ms,
                    "limit": 1000,
                },
            )
            if not batch:
                break
            all_rates.extend(batch)
            if len(batch) < 1000:
                break
            cursor_ms = int(batch[-1]["fundingTime"]) + 1
        return all_rates

    async def _fetch_klines(
        self,
        http: HttpClient,
        symbol: str,
        start: datetime,
        end: datetime,
        interval_h: int,
    ) -> dict[int, Decimal]:
        """Return {open_time_ms: open_price}.

        The open price of the kline starting at the funding timestamp is the
        mark price snapshot we want.
        """
        result: dict[int, Decimal] = {}
        cursor_ms = to_ms(start)
        end_ms = to_ms(end)
        while cursor_ms <= end_ms:
            batch = await http.get_json(
                "/fapi/v1/markPriceKlines",
                params={
                    "symbol": symbol,
                    "interval": f"{interval_h}h",
                    "startTime": cursor_ms,
                    "endTime": end_ms,
                    "limit": 1500,
                },
            )
            if not batch:
                break
            for row in batch:
                # row[0] = open_time, row[1] = open_price (string)
                result[int(row[0])] = Decimal(str(row[1]))
            if len(batch) < 1500:
                break
            cursor_ms = int(batch[-1][0]) + 1
        return result

    def _merge(
        self,
        symbol: str,
        rates: list[dict[str, Any]],
        klines: dict[int, Decimal],
        interval_h: int,
    ) -> list[FundingEvent]:
        """Join rates with klines on fundingTime.

        If no kline exists at the exact funding timestamp, fall back to the most
        recent kline whose open_time is within one ``interval_h`` before. Anything
        further back is treated as missing data and raised as ExchangeError.
        """
        events: list[FundingEvent] = []
        kline_times = sorted(klines.keys())
        tolerance_ms = interval_h * 3_600_000
        for r in rates:
            ft = int(r["fundingTime"])
            mark = klines.get(ft)
            if mark is None:
                # Floor-lookup: find the largest kline_time <= ft within tolerance.
                idx = bisect.bisect_right(kline_times, ft) - 1
                if idx >= 0 and ft - kline_times[idx] <= tolerance_ms:
                    mark = klines[kline_times[idx]]
            if mark is None:
                raise ExchangeError(
                    f"missing mark price for funding event at "
                    f"{from_ms(ft).isoformat()} ({symbol})"
                )
            events.append(
                FundingEvent(
                    timestamp=from_ms(ft),
                    symbol=symbol,
                    rate=Decimal(str(r["fundingRate"])),
                    mark_price=mark,
                    interval_hours=interval_h,
                )
            )
        return events

    # Stubs to be filled in next tasks
    async def fetch_funding_income(
        self,
        credentials: ApiCredentials,
        start: datetime,
        end: datetime,
        symbol: str | None = None,
    ) -> list[IncomeRecord]:
        raise NotImplementedError

    async def get_interval_hours(self, symbol: str) -> int:
        async with HttpClient(self._base_url) as http:
            return await self._get_interval(http, symbol)

    async def validate_symbol(self, symbol: str) -> bool:
        try:
            async with HttpClient(self._base_url) as http:
                await self._get_interval(http, symbol)
        except UnknownSymbolError:
            return False
        return True

    async def verify_credentials(
        self, credentials: ApiCredentials
    ) -> PermissionReport:
        raise NotImplementedError


_DEFAULT_CACHE_PATH = "~/.local/share/funding-tool/cache.sqlite"


def build_binance_usdm_exchange(
    *, cache_path: str | None = None
) -> BinanceUsdmExchange:
    """Factory used by the CLI to construct an exchange with the default cache."""
    if cache_path is None:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        cache_path = str(Path(base) / "funding-tool" / "cache.sqlite")
    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
    return BinanceUsdmExchange(cache=SqliteFundingRateCache(Path(cache_path)))
