from datetime import UTC, datetime
from decimal import Decimal

import pytest

from funding_tool.core.backtest import run_backtest
from funding_tool.core.models import BacktestInput, FundingEvent
from tests.fakes import FakeExchange


def _events(rates, interval_hours=8):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        FundingEvent(
            timestamp=base.replace(hour=(i * interval_hours) % 24,
                                   day=1 + (i * interval_hours) // 24),
            symbol="BTCUSDT",
            rate=Decimal(r),
            mark_price=Decimal("50000"),   # ignored for RATE_ONLY
            interval_hours=interval_hours,
        )
        for i, r in enumerate(rates)
    ]


@pytest.mark.asyncio
async def test_rate_only_totals_are_none():
    ex = FakeExchange(funding_rates=_events(["0.0001", "-0.0002"]))
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="RATE_ONLY", size=None,
    )
    res = await run_backtest(inp, exchange=ex)
    assert res.total_quote is None
    assert res.total_base is None
    assert res.event_count == 2


@pytest.mark.asyncio
async def test_rate_only_cumulative_rate_long():
    """LONG: side_sign = -1; cumulative_rate_pct = sum(-rate) × 100."""
    ex = FakeExchange(funding_rates=_events(["0.0001", "0.0001", "-0.0002"]))
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="RATE_ONLY", size=None,
    )
    res = await run_backtest(inp, exchange=ex)
    # sum(-1 × [0.0001, 0.0001, -0.0002]) × 100 = 0
    assert res.cumulative_rate_pct == Decimal("0")


@pytest.mark.asyncio
async def test_rate_only_apr_uses_intervals_per_year():
    """RATE_ONLY APR = avg_rate × intervals_per_year. 8h interval → 1095.75 per year."""
    ex = FakeExchange(funding_rates=_events(["0.0001"], interval_hours=8))
    inp = BacktestInput(
        symbol="BTCUSDT", side="SHORT",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="RATE_ONLY", size=None,
    )
    res = await run_backtest(inp, exchange=ex)
    # avg_rate (with SHORT sign) = +0.0001; intervals_per_year = 24*365.25/8 = 1095.75
    expected = Decimal("0.0001") * (Decimal("24") * Decimal("365.25") / Decimal("8"))
    assert res.apr == expected


@pytest.mark.asyncio
async def test_rate_only_empty_events_totals_remain_none():
    """Empty window in RATE_ONLY → total_* stays None (NOT 0)."""
    ex = FakeExchange(funding_rates=[])
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="RATE_ONLY", size=None,
    )
    res = await run_backtest(inp, exchange=ex)
    assert res.event_count == 0
    assert res.total_quote is None
    assert res.total_base is None
    assert res.apr == Decimal("0")


@pytest.mark.asyncio
async def test_rate_only_size_param_ignored():
    """size param must be allowed (None) for RATE_ONLY; service should not reject."""
    ex = FakeExchange(funding_rates=_events(["0.0001"]))
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="RATE_ONLY", size=None,
    )
    res = await run_backtest(inp, exchange=ex)
    assert res.event_count == 1
