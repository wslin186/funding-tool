"""Account funding history service (Feature B). Pure: aggregates IncomeRecord into HistoryResult."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from funding_tool.core.errors import ValidationError
from funding_tool.core.models import ApiCredentials, HistoryResult

if TYPE_CHECKING:
    from funding_tool.core.exchanges.base import ExchangeProtocol


def _validate(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValidationError("start and end must be timezone-aware")
    if start >= end:
        raise ValidationError(f"start ({start}) must be before end ({end})")


async def run_account_history(
    *,
    creds: ApiCredentials,
    exchange: ExchangeProtocol,
    start: datetime,
    end: datetime,
    symbol: str | None = None,
) -> HistoryResult:
    _validate(start, end)

    records = await exchange.fetch_funding_income(
        credentials=creds, start=start, end=end, symbol=symbol,
    )

    by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    total = Decimal("0")
    for r in records:
        total += r.amount_usdt
        by_symbol[r.symbol] += r.amount_usdt
        by_month[r.timestamp.strftime("%Y-%m")] += r.amount_usdt

    return HistoryResult(
        start=start,
        end=end,
        records=records,
        total=total,
        by_symbol=dict(by_symbol),
        by_month=dict(by_month),
    )
