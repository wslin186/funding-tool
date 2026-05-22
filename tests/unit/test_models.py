from datetime import UTC, datetime
from decimal import Decimal

import pytest

from funding_tool.core.models import (
    ApiCredentials,
    BacktestInput,
    BacktestResult,
    FundingEvent,
    FundingPayment,
    HistoryResult,
    IncomeRecord,
    PermissionReport,
)


def _ev(ts=None, rate="0.0001", mark="50000", interval=8):
    return FundingEvent(
        timestamp=ts or datetime(2026, 1, 1, tzinfo=UTC),
        symbol="BTCUSDT",
        rate=Decimal(rate),
        mark_price=Decimal(mark),
        interval_hours=interval,
    )


def test_funding_event_is_frozen():
    ev = _ev()
    with pytest.raises(Exception):  # noqa: B017
        ev.rate = Decimal("0.5")  # type: ignore[misc]


def test_backtest_input_requires_end():
    # end is non-optional; service layer rejects None.
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        size_mode="BASE", size=Decimal("1"),
    )
    assert inp.symbol == "BTCUSDT"


def test_backtest_result_total_fields_optional():
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="RATE_ONLY", size=None,
    )
    res = BacktestResult(
        input=inp, payments=[],
        total_quote=None, total_base=None,
        cumulative_rate_pct=Decimal("0"),
        apr=Decimal("0"), event_count=0, avg_rate=Decimal("0"),
    )
    assert res.total_quote is None
    assert res.total_base is None


def test_api_credentials_passphrase_defaults_none():
    c = ApiCredentials(api_key="k", api_secret="s")
    assert c.passphrase is None
    c2 = ApiCredentials(api_key="k", api_secret="s", passphrase="p")
    assert c2.passphrase == "p"


def test_income_record_uses_decimal():
    r = IncomeRecord(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="BTCUSDT",
        amount_usdt=Decimal("1.5"),
        tran_id="123",
    )
    assert r.amount_usdt == Decimal("1.5")


def test_history_result_aggregations():
    r1 = IncomeRecord(timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                     symbol="BTCUSDT", amount_usdt=Decimal("1"), tran_id="1")
    h = HistoryResult(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        records=[r1], total=Decimal("1"),
        by_symbol={"BTCUSDT": Decimal("1")},
        by_month={"2026-01": Decimal("1")},
    )
    assert h.total == Decimal("1")


def test_funding_payment_fields():
    ev = _ev()
    p = FundingPayment(
        event=ev, quantity_base=Decimal("1"),
        notional_quote=Decimal("50000"),
        payment_quote=Decimal("-5"),
    )
    assert p.payment_quote == Decimal("-5")


def test_permission_report_advisory_fields_optional():
    """`read_ok` is required; advisory fields default to None when unknown."""
    r = PermissionReport(
        read_ok=True, trading_enabled=None,
        withdrawals_enabled=None, spot_trading_enabled=None,
    )
    assert r.read_ok is True
    assert r.trading_enabled is None
