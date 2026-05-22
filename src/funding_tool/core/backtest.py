"""Backtest service (Feature A).

Pure: takes BacktestInput + ExchangeProtocol, returns BacktestResult.
"""

from __future__ import annotations

from decimal import Decimal
from statistics import mean
from typing import TYPE_CHECKING

from funding_tool.core.errors import ValidationError
from funding_tool.core.models import (
    BacktestInput,
    BacktestResult,
    FundingEvent,
    FundingPayment,
)

if TYPE_CHECKING:
    from funding_tool.core.exchanges.base import ExchangeProtocol

_SECONDS_PER_YEAR = Decimal("31557600")  # 365.25 * 86400


def _side_sign(side: str) -> int:
    # Positive funding rate → LONG pays SHORT. So LONG = -1, SHORT = +1.
    return -1 if side == "LONG" else 1


def _validate(inp: BacktestInput) -> None:
    if inp.start.tzinfo is None or inp.end.tzinfo is None:
        raise ValidationError("start and end must be timezone-aware")
    if inp.start >= inp.end:
        raise ValidationError(f"start ({inp.start}) must be before end ({inp.end})")
    if inp.size_mode in ("BASE", "QUOTE") and (inp.size is None or inp.size <= 0):
        raise ValidationError(f"size must be positive for {inp.size_mode} mode")


def _quantity_for_event(
    inp: BacktestInput, events: list[FundingEvent], idx: int
) -> Decimal:
    if inp.size_mode == "BASE":
        return inp.size  # type: ignore[return-value]
    if inp.size_mode == "QUOTE":
        # Constant after entry: size / events[0].mark_price
        entry = events[0].mark_price
        return inp.size / entry  # type: ignore[operator]
    # RATE_ONLY handled in Task 12; assert unreachable here.
    raise ValidationError(f"unsupported size_mode {inp.size_mode}")


async def run_backtest(
    inp: BacktestInput,
    *,
    exchange: ExchangeProtocol,
) -> BacktestResult:
    _validate(inp)

    events = await exchange.fetch_funding_rates(inp.symbol, inp.start, inp.end)
    side_sign = _side_sign(inp.side)

    payments: list[FundingPayment] = []
    for i, ev in enumerate(events):
        qty = _quantity_for_event(inp, events, i)
        notional = qty * ev.mark_price
        payment = Decimal(side_sign) * qty * ev.mark_price * ev.rate
        payments.append(FundingPayment(
            event=ev, quantity_base=qty,
            notional_quote=notional, payment_quote=payment,
        ))

    event_count = len(payments)
    cumulative_rate_pct = (
        sum((Decimal(side_sign) * p.event.rate for p in payments), Decimal("0")) * 100
    )
    avg_rate = (
        Decimal(mean([Decimal(side_sign) * p.event.rate for p in payments]))
        if event_count
        else Decimal("0")
    )

    total_quote = sum((p.payment_quote for p in payments), Decimal("0"))
    total_base = sum(
        (p.payment_quote / p.event.mark_price for p in payments), Decimal("0")
    )

    # APR for BASE / QUOTE: total_quote / avg_notional / elapsed_years
    elapsed_seconds = Decimal(str((inp.end - inp.start).total_seconds()))
    elapsed_years = elapsed_seconds / _SECONDS_PER_YEAR
    if event_count and elapsed_years > 0:
        if inp.size_mode == "BASE":
            avg_notional = Decimal(mean([p.notional_quote for p in payments]))
        else:  # QUOTE
            avg_notional = inp.size  # type: ignore[assignment]
        apr = (total_quote / avg_notional) / elapsed_years if avg_notional else Decimal("0")
    else:
        apr = Decimal("0")

    return BacktestResult(
        input=inp,
        payments=payments,
        total_quote=total_quote,
        total_base=total_base,
        cumulative_rate_pct=cumulative_rate_pct,
        apr=apr,
        event_count=event_count,
        avg_rate=avg_rate,
    )
