from datetime import UTC, datetime
from decimal import Decimal

import pytest

from funding_tool.core.account import run_account_history
from funding_tool.core.errors import ValidationError
from funding_tool.core.models import ApiCredentials, IncomeRecord
from tests.fakes import FakeExchange

CREDS = ApiCredentials(api_key="k", api_secret="s")


def _rec(month, day, symbol, amount, tran_id):
    return IncomeRecord(
        timestamp=datetime(2026, month, day, tzinfo=UTC),
        symbol=symbol,
        amount_usdt=Decimal(amount),
        tran_id=tran_id,
    )


@pytest.mark.asyncio
async def test_aggregates_total_by_symbol_by_month():
    records = [
        _rec(1, 5, "BTCUSDT", "1.5", "t1"),
        _rec(1, 6, "BTCUSDT", "-0.5", "t2"),
        _rec(2, 1, "ETHUSDT", "2", "t3"),
    ]
    ex = FakeExchange(income_records=records)
    res = await run_account_history(
        creds=CREDS, exchange=ex,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 3, 1, tzinfo=UTC),
    )
    assert res.total == Decimal("3")
    assert res.by_symbol == {"BTCUSDT": Decimal("1"), "ETHUSDT": Decimal("2")}
    assert res.by_month == {"2026-01": Decimal("1"), "2026-02": Decimal("2")}


@pytest.mark.asyncio
async def test_symbol_filter():
    records = [
        _rec(1, 5, "BTCUSDT", "1", "t1"),
        _rec(1, 6, "ETHUSDT", "2", "t2"),
    ]
    ex = FakeExchange(income_records=records)
    res = await run_account_history(
        creds=CREDS, exchange=ex,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        symbol="BTCUSDT",
    )
    assert res.total == Decimal("1")
    assert list(res.by_symbol.keys()) == ["BTCUSDT"]


@pytest.mark.asyncio
async def test_empty_records_total_zero():
    ex = FakeExchange(income_records=[])
    res = await run_account_history(
        creds=CREDS, exchange=ex,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert res.total == Decimal("0")
    assert res.by_symbol == {}
    assert res.by_month == {}
    assert res.records == []


@pytest.mark.asyncio
async def test_rejects_naive_start_end():
    ex = FakeExchange(income_records=[])
    with pytest.raises(ValidationError, match="timezone"):
        await run_account_history(
            creds=CREDS, exchange=ex,
            start=datetime(2026, 1, 1),
            end=datetime(2026, 2, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_rejects_start_after_end():
    ex = FakeExchange(income_records=[])
    with pytest.raises(ValidationError, match="start"):
        await run_account_history(
            creds=CREDS, exchange=ex,
            start=datetime(2026, 3, 1, tzinfo=UTC),
            end=datetime(2026, 2, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_passes_symbol_filter_to_exchange():
    """If symbol is given, exchange.fetch_funding_income should be called with it."""
    ex = FakeExchange(income_records=[])
    await run_account_history(
        creds=CREDS, exchange=ex,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        symbol="BTCUSDT",
    )
    assert ex.last_income_call["symbol"] == "BTCUSDT"
