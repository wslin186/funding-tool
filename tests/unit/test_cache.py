from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from funding_tool.core.cache import SqliteFundingRateCache
from funding_tool.core.models import FundingEvent


def _ev(hours_offset: int, rate: str = "0.0001") -> FundingEvent:
    return FundingEvent(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hours_offset),
        symbol="BTCUSDT",
        rate=Decimal(rate),
        mark_price=Decimal("50000"),
        interval_hours=8,
    )


@pytest.fixture
def cache(tmp_path: Path) -> SqliteFundingRateCache:
    return SqliteFundingRateCache(tmp_path / "cache.db")


@pytest.mark.asyncio
async def test_put_and_get_roundtrip(cache):
    events = [_ev(0), _ev(8), _ev(16)]
    await cache.put("binance_usdm", "BTCUSDT", events)
    got = await cache.get("binance_usdm", "BTCUSDT",
                         datetime(2026, 1, 1, tzinfo=UTC),
                         datetime(2026, 1, 2, tzinfo=UTC))
    assert len(got) == 3
    assert got[0].rate == Decimal("0.0001")


@pytest.mark.asyncio
async def test_get_filters_by_window(cache):
    await cache.put("binance_usdm", "BTCUSDT", [_ev(0), _ev(8), _ev(16), _ev(24)])
    got = await cache.get("binance_usdm", "BTCUSDT",
                         datetime(2026, 1, 1, 5, tzinfo=UTC),
                         datetime(2026, 1, 1, 20, tzinfo=UTC))
    # event at hour 8 and hour 16 are in [05:00, 20:00]
    assert len(got) == 2


@pytest.mark.asyncio
async def test_put_idempotent(cache):
    ev = _ev(0)
    await cache.put("binance_usdm", "BTCUSDT", [ev])
    await cache.put("binance_usdm", "BTCUSDT", [ev])  # duplicate insert
    got = await cache.get("binance_usdm", "BTCUSDT",
                         datetime(2026, 1, 1, tzinfo=UTC),
                         datetime(2026, 1, 2, tzinfo=UTC))
    assert len(got) == 1


@pytest.mark.asyncio
async def test_missing_ranges_empty_cache(cache):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 5, tzinfo=UTC)
    gaps = await cache.missing_ranges("binance_usdm", "BTCUSDT", start, end)
    assert gaps == [(start, end)]


@pytest.mark.asyncio
async def test_missing_ranges_trailing_gap(cache):
    # cache has events at hours 0, 8, 16 — request extends 16 hours past last cached event.
    await cache.put("binance_usdm", "BTCUSDT", [_ev(0), _ev(8), _ev(16)])
    gaps = await cache.missing_ranges(
        "binance_usdm", "BTCUSDT",
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 2, 8, tzinfo=UTC),  # hour 32 = Jan 2 08:00
    )
    # Trailing gap starts one interval after the last cached event (hour 16 + 8h = hour 24).
    assert gaps == [(datetime(2026, 1, 2, 0, tzinfo=UTC),
                     datetime(2026, 1, 2, 8, tzinfo=UTC))]


@pytest.mark.asyncio
async def test_missing_ranges_leading_gap(cache):
    # cache has events at hours 16, 24 — request starts before first cached event.
    await cache.put("binance_usdm", "BTCUSDT", [_ev(16), _ev(24)])
    gaps = await cache.missing_ranges(
        "binance_usdm", "BTCUSDT",
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 2, 1, tzinfo=UTC),  # hour 25, just past last cached
    )
    # Leading gap: from requested `start` to the first cached event's timestamp.
    assert gaps == [(datetime(2026, 1, 1, tzinfo=UTC),
                     datetime(2026, 1, 1, 16, tzinfo=UTC))]


@pytest.mark.asyncio
async def test_missing_ranges_interior_hole(cache):
    # Cached events at hours 0, 8, 32 (interval 8h). Events at 16, 24 are missing.
    await cache.put("binance_usdm", "BTCUSDT", [_ev(0), _ev(8), _ev(32)])
    gaps = await cache.missing_ranges(
        "binance_usdm", "BTCUSDT",
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 2, 8, tzinfo=UTC),  # request covers full span [0, 32h]
    )
    # Interior gap = (last_before_hole + interval, next_after_hole.ts)
    #              = (hour 8 + 8h, hour 32) = (Jan 1 16:00, Jan 2 08:00)
    # No leading/trailing gap (start == hour 0, end == hour 32 == last cached).
    assert gaps == [
        (datetime(2026, 1, 1, 16, tzinfo=UTC), datetime(2026, 1, 2, 8, tzinfo=UTC)),
    ]


@pytest.mark.asyncio
async def test_missing_ranges_tolerates_ms_jitter(cache):
    """Binance fundingTime values drift by a few ms between events. Two adjacent
    cached events whose delta is ~interval_hours (off by milliseconds) are
    contiguous — there is no gap between them."""
    # Events are 8 hours apart but with different sub-second offsets, mimicking
    # Binance's real behaviour: one event lands at :00.007Z, the next at :00.013Z.
    prev = FundingEvent(
        timestamp=datetime(2026, 1, 1, 12, 0, 0, 7_000, tzinfo=UTC),
        symbol="BTCUSDT",
        rate=Decimal("0.0001"),
        mark_price=Decimal("50000"),
        interval_hours=8,
    )
    nxt = FundingEvent(
        timestamp=datetime(2026, 1, 1, 20, 0, 0, 13_000, tzinfo=UTC),
        symbol="BTCUSDT",
        rate=Decimal("0.0001"),
        mark_price=Decimal("50000"),
        interval_hours=8,
    )
    await cache.put("binance_usdm", "BTCUSDT", [prev, nxt])
    gaps = await cache.missing_ranges(
        "binance_usdm", "BTCUSDT",
        datetime(2026, 1, 1, 12, tzinfo=UTC),
        datetime(2026, 1, 1, 20, tzinfo=UTC),
    )
    assert gaps == []


@pytest.mark.asyncio
async def test_missing_ranges_full_interval_gap_still_detected(cache):
    """The jitter tolerance must not swallow real missing events: a delta of one
    full interval (or more) between adjacent cached events is still a gap."""
    # Cached events at hours 0 and 16 — the event at hour 8 is genuinely missing.
    await cache.put("binance_usdm", "BTCUSDT", [_ev(0), _ev(16)])
    gaps = await cache.missing_ranges(
        "binance_usdm", "BTCUSDT",
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, 16, tzinfo=UTC),
    )
    # Interior gap from hour 0 + 8h = hour 8 → hour 16.
    assert gaps == [
        (datetime(2026, 1, 1, 8, tzinfo=UTC), datetime(2026, 1, 1, 16, tzinfo=UTC)),
    ]


@pytest.mark.asyncio
async def test_decimal_precision_preserved(cache):
    ev = FundingEvent(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="BTCUSDT",
        rate=Decimal("0.00012345678901234"),
        mark_price=Decimal("50123.45678901234"),
        interval_hours=8,
    )
    await cache.put("binance_usdm", "BTCUSDT", [ev])
    got = await cache.get("binance_usdm", "BTCUSDT",
                         datetime(2026, 1, 1, tzinfo=UTC),
                         datetime(2026, 1, 2, tzinfo=UTC))
    assert got[0].rate == Decimal("0.00012345678901234")
    assert got[0].mark_price == Decimal("50123.45678901234")


@pytest.mark.asyncio
async def test_stats_returns_per_symbol_summary(cache):
    await cache.put("binance_usdm", "BTCUSDT", [_ev(0), _ev(8), _ev(16)])
    await cache.put("binance_usdm", "ETHUSDT", [_ev(0)])
    stats = cache.stats()
    by_symbol = {row["symbol"]: row for row in stats}
    assert by_symbol["BTCUSDT"]["rows"] == 3
    assert by_symbol["BTCUSDT"]["first"] == "2026-01-01"
    assert by_symbol["BTCUSDT"]["last"] == "2026-01-01"
    assert by_symbol["ETHUSDT"]["rows"] == 1
    assert by_symbol["BTCUSDT"]["exchange"] == "binance_usdm"


def test_stats_empty_cache(cache):
    assert cache.stats() == []


@pytest.mark.asyncio
async def test_clear_all_rows(cache):
    await cache.put("binance_usdm", "BTCUSDT", [_ev(0), _ev(8)])
    await cache.put("binance_usdm", "ETHUSDT", [_ev(0)])
    n = cache.clear()
    assert n == 3
    assert cache.stats() == []


@pytest.mark.asyncio
async def test_clear_by_symbol(cache):
    await cache.put("binance_usdm", "BTCUSDT", [_ev(0), _ev(8)])
    await cache.put("binance_usdm", "ETHUSDT", [_ev(0)])
    n = cache.clear(symbol="BTCUSDT")
    assert n == 2
    remaining = cache.stats()
    assert [r["symbol"] for r in remaining] == ["ETHUSDT"]


@pytest.mark.asyncio
async def test_check_integrity_ok(cache):
    await cache.put("binance_usdm", "BTCUSDT", [_ev(0)])
    # Healthy SQLite DB → returns None (no exception).
    cache.check_integrity()


def test_check_integrity_raises_on_corrupt_file(tmp_path: Path):
    """A non-SQLite file at the cache path must surface a clear error, not silently swallow."""
    from funding_tool.core.errors import CacheCorruptionError

    corrupt_path = tmp_path / "cache.db"
    corrupt_path.write_bytes(b"this is not a valid sqlite database file")
    # Bypass __init__ (which calls executescript and would fail confusingly) by
    # constructing via __new__ and patching the path.
    cache = SqliteFundingRateCache.__new__(SqliteFundingRateCache)
    cache._db_path = corrupt_path
    with pytest.raises(CacheCorruptionError):
        cache.check_integrity()
