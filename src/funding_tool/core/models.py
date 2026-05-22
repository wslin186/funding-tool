"""Data models for funding-tool. All money values are Decimal; all datetimes are tz-aware UTC."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class FundingEvent:
    """One funding settlement: rate + mark price at a specific timestamp."""
    timestamp: datetime
    symbol: str
    rate: Decimal
    mark_price: Decimal
    interval_hours: int


@dataclass(frozen=True)
class BacktestInput:
    """Inputs for a hypothetical backtest (feature A)."""
    symbol: str
    side: Literal["LONG", "SHORT"]
    start: datetime
    end: datetime  # non-optional; CLI/UI expands "now" before constructing
    size_mode: Literal["BASE", "QUOTE", "RATE_ONLY"]
    size: Decimal | None  # required unless RATE_ONLY


@dataclass(frozen=True)
class FundingPayment:
    """One funding settlement's contribution to backtest P&L."""
    event: FundingEvent
    quantity_base: Decimal
    notional_quote: Decimal
    payment_quote: Decimal  # signed; +income, -cost


@dataclass(frozen=True)
class BacktestResult:
    """Aggregated backtest output. total_* are None for RATE_ONLY mode."""
    input: BacktestInput
    payments: list[FundingPayment]
    total_quote: Decimal | None
    total_base: Decimal | None
    cumulative_rate_pct: Decimal
    apr: Decimal
    event_count: int
    avg_rate: Decimal


@dataclass(frozen=True)
class IncomeRecord:
    """One row from /fapi/v1/income (FUNDING_FEE type)."""
    timestamp: datetime
    symbol: str
    amount_usdt: Decimal
    tran_id: str


@dataclass(frozen=True)
class HistoryResult:
    """Aggregated account funding history (feature B)."""
    start: datetime
    end: datetime
    records: list[IncomeRecord]
    total: Decimal
    by_symbol: dict[str, Decimal]
    by_month: dict[str, Decimal]


@dataclass(frozen=True)
class ApiCredentials:
    """API key + secret (+ optional passphrase for exchanges like OKX)."""
    api_key: str
    api_secret: str
    passphrase: str | None = None


@dataclass(frozen=True)
class PermissionReport:
    """Report from `ExchangeProtocol.verify_credentials`.

    `read_ok` is the only required outcome — without read access the tool can't
    function. The other fields are advisory: they let the CLI warn when an
    overly-privileged key (trading/withdrawals enabled) is used for a read-only
    workflow. `None` means the exchange did not report on that capability.
    """
    read_ok: bool
    trading_enabled: bool | None
    withdrawals_enabled: bool | None
    spot_trading_enabled: bool | None
