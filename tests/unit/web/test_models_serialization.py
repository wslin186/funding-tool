from datetime import datetime, timezone
from decimal import Decimal

from funding_tool.core.models import (
    BacktestInput, BacktestResult, FundingEvent, FundingPayment,
)
from funding_tool.web.models import to_backtest_response


def test_decimal_serialized_as_string() -> None:
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2025, 1, 2, tzinfo=timezone.utc),
        size_mode="BASE", size=Decimal("1.5"),
    )
    ev = FundingEvent(
        timestamp=datetime(2025, 1, 1, 8, tzinfo=timezone.utc),
        symbol="BTCUSDT", rate=Decimal("0.0001"),
        mark_price=Decimal("60000"), interval_hours=8,
    )
    pay = FundingPayment(
        event=ev, quantity_base=Decimal("1.5"),
        notional_quote=Decimal("90000"), payment_quote=Decimal("-9"),
    )
    result = BacktestResult(
        input=inp, payments=[pay],
        total_quote=Decimal("-9"), total_base=Decimal("-0.00015"),
        cumulative_rate_pct=Decimal("0.01"), apr=Decimal("3.65"),
        event_count=1, avg_rate=Decimal("0.0001"),
    )
    js = to_backtest_response(result).model_dump(mode="json")
    assert js["total_quote"] == "-9"
    assert js["payments"][0]["payment_quote"] == "-9"
    assert js["cumulative_rate_pct"] == "0.01"


def test_rate_only_totals_are_null() -> None:
    inp = BacktestInput(
        symbol="X", side="LONG",
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2025, 1, 2, tzinfo=timezone.utc),
        size_mode="RATE_ONLY", size=None,
    )
    result = BacktestResult(
        input=inp, payments=[], total_quote=None, total_base=None,
        cumulative_rate_pct=Decimal("0"), apr=Decimal("0"),
        event_count=0, avg_rate=Decimal("0"),
    )
    js = to_backtest_response(result).model_dump(mode="json")
    assert js["total_quote"] is None
    assert js["total_base"] is None
