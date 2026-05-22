import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from funding_tool.cli.output import (
    format_backtest_json,
    format_history_json,
    write_backtest_csv,
    write_history_csv,
)
from funding_tool.core.models import (
    BacktestInput,
    BacktestResult,
    FundingEvent,
    FundingPayment,
    HistoryResult,
    IncomeRecord,
)


def _backtest_result() -> BacktestResult:
    inp = BacktestInput(
        symbol="BTCUSDT", side="LONG",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        size_mode="BASE", size=Decimal("1"),
    )
    ev = FundingEvent(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="BTCUSDT", rate=Decimal("0.0001"),
        mark_price=Decimal("50000"), interval_hours=8,
    )
    pay = FundingPayment(
        event=ev, quantity_base=Decimal("1"),
        notional_quote=Decimal("50000"), payment_quote=Decimal("-5"),
    )
    return BacktestResult(
        input=inp, payments=[pay],
        total_quote=Decimal("-5"), total_base=Decimal("-0.0001"),
        cumulative_rate_pct=Decimal("-0.01"),
        apr=Decimal("-0.0365"), event_count=1, avg_rate=Decimal("-0.0001"),
    )


def test_backtest_json_uses_strings_for_decimal():
    out = format_backtest_json(_backtest_result())
    data = json.loads(out)
    # Decimals must round-trip as strings to preserve precision.
    assert data["total_quote"] == "-5"
    assert data["apr"] == "-0.0365"
    assert data["payments"][0]["payment_quote"] == "-5"
    # Datetimes ISO-8601 with Z or offset:
    assert data["input"]["start"].endswith("+00:00") or data["input"]["start"].endswith("Z")


def test_backtest_json_handles_none_totals():
    res = _backtest_result()
    res = BacktestResult(
        input=res.input, payments=res.payments,
        total_quote=None, total_base=None,
        cumulative_rate_pct=res.cumulative_rate_pct,
        apr=res.apr, event_count=res.event_count, avg_rate=res.avg_rate,
    )
    data = json.loads(format_backtest_json(res))
    assert data["total_quote"] is None
    assert data["total_base"] is None


def test_backtest_csv_has_header_and_row(tmp_path: Path):
    target = tmp_path / "out.csv"
    write_backtest_csv(_backtest_result(), target)
    text = target.read_text()
    lines = text.strip().split("\n")
    assert lines[0] == "timestamp,symbol,rate,mark_price,quantity_base,notional_quote,payment_quote"
    assert "BTCUSDT" in lines[1]
    assert "-5" in lines[1]


def test_history_json_aggregation_preserved():
    rec = IncomeRecord(
        timestamp=datetime(2026, 1, 5, tzinfo=UTC),
        symbol="BTCUSDT", amount_usdt=Decimal("1.5"), tran_id="t1",
    )
    hist = HistoryResult(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        records=[rec], total=Decimal("1.5"),
        by_symbol={"BTCUSDT": Decimal("1.5")},
        by_month={"2026-01": Decimal("1.5")},
    )
    data = json.loads(format_history_json(hist))
    assert data["total"] == "1.5"
    assert data["by_symbol"]["BTCUSDT"] == "1.5"
    assert data["by_month"]["2026-01"] == "1.5"


def test_history_csv(tmp_path: Path):
    rec = IncomeRecord(
        timestamp=datetime(2026, 1, 5, tzinfo=UTC),
        symbol="BTCUSDT", amount_usdt=Decimal("1.5"), tran_id="t1",
    )
    hist = HistoryResult(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        records=[rec], total=Decimal("1.5"),
        by_symbol={"BTCUSDT": Decimal("1.5")}, by_month={"2026-01": Decimal("1.5")},
    )
    target = tmp_path / "h.csv"
    write_history_csv(hist, target)
    text = target.read_text()
    lines = text.strip().split("\n")
    assert lines[0] == "timestamp,symbol,amount_usdt,tran_id"
    assert "t1" in lines[1]
