from datetime import UTC, datetime
from decimal import Decimal

import pytest

from funding_tool.core.backtest import run_backtest
from funding_tool.core.errors import ValidationError
from funding_tool.core.models import BacktestInput, FundingEvent
from tests.fakes import FakeExchange


def _events(prices_and_rates):
    """Helper: list of (mark_price, rate) → FundingEvents at 8h intervals from 2026-01-01."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    for i, (price, rate) in enumerate(prices_and_rates):
        out.append(FundingEvent(
            timestamp=base.replace(hour=(i * 8) % 24, day=1 + (i * 8) // 24),
            symbol="BTCUSDT",
            rate=Decimal(rate),
            mark_price=Decimal(price),
            interval_hours=8,
        ))
    return out


@pytest.mark.asyncio
async def test_base_mode_long_positive_rate_pays_out():
    """LONG + positive rate → payment is negative (you pay)."""
    events = _events([("50000", "0.0001")])
    ex = FakeExchange(funding_rates=events)
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="BASE", size=Decimal("1"),
    )
    res = await run_backtest(inp, exchange=ex)
    assert res.event_count == 1
    assert res.total_quote == Decimal("-5")        # -1 × 1 × 50000 × 0.0001
    assert res.payments[0].notional_quote == Decimal("50000")
    assert res.payments[0].quantity_base == Decimal("1")


@pytest.mark.asyncio
async def test_base_mode_short_positive_rate_receives():
    events = _events([("50000", "0.0001")])
    ex = FakeExchange(funding_rates=events)
    inp = BacktestInput(
        symbol="BTCUSDT", side="SHORT",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="BASE", size=Decimal("1"),
    )
    res = await run_backtest(inp, exchange=ex)
    assert res.total_quote == Decimal("5")         # +1 × 1 × 50000 × 0.0001


@pytest.mark.asyncio
async def test_base_mode_notional_tracks_price():
    """BASE: quantity fixed, notional moves with mark price."""
    events = _events([("50000", "0.0001"), ("60000", "0.0001")])
    ex = FakeExchange(funding_rates=events)
    inp = BacktestInput(
        symbol="BTCUSDT", side="SHORT",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="BASE", size=Decimal("1"),
    )
    res = await run_backtest(inp, exchange=ex)
    assert res.payments[0].notional_quote == Decimal("50000")
    assert res.payments[1].notional_quote == Decimal("60000")
    assert res.total_quote == Decimal("11")        # 5 + 6


@pytest.mark.asyncio
async def test_quote_mode_quantity_fixed_after_entry():
    """QUOTE: size is initial USDT; quantity = size / first mark price, then fixed."""
    events = _events([("50000", "0.0001"), ("60000", "0.0001")])
    ex = FakeExchange(funding_rates=events)
    inp = BacktestInput(
        symbol="BTCUSDT", side="SHORT",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="QUOTE", size=Decimal("50000"),
    )
    res = await run_backtest(inp, exchange=ex)
    # quantity_base = 50000 / 50000 = 1, then constant
    assert res.payments[0].quantity_base == Decimal("1")
    assert res.payments[1].quantity_base == Decimal("1")
    # Second notional reflects price change
    assert res.payments[1].notional_quote == Decimal("60000")


@pytest.mark.asyncio
async def test_rejects_naive_datetime():
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 1, 1),                # naive!
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="BASE", size=Decimal("1"),
    )
    with pytest.raises(ValidationError, match="timezone"):
        await run_backtest(inp, exchange=FakeExchange(funding_rates=[]))


@pytest.mark.asyncio
async def test_rejects_start_after_end():
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 2, 1, tzinfo=UTC),
        end=datetime(2026, 1, 1, tzinfo=UTC),
        size_mode="BASE", size=Decimal("1"),
    )
    with pytest.raises(ValidationError, match="start"):
        await run_backtest(inp, exchange=FakeExchange(funding_rates=[]))


@pytest.mark.asyncio
async def test_empty_events_returns_zero_totals_for_base_quote():
    ex = FakeExchange(funding_rates=[])
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="BASE", size=Decimal("1"),
    )
    res = await run_backtest(inp, exchange=ex)
    assert res.event_count == 0
    assert res.total_quote == Decimal("0")
    assert res.total_base == Decimal("0")
    assert res.apr == Decimal("0")
