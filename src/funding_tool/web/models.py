"""Pydantic request/response models. All Decimal fields serialize to str."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer

from funding_tool.core.models import BacktestResult, HistoryResult, PermissionReport

DecimalStr = Annotated[Decimal, PlainSerializer(lambda d: format(d, "f"), return_type=str)]
DecimalStrOpt = Annotated[Decimal | None, PlainSerializer(
    lambda d: format(d, "f") if d is not None else None, return_type=str | None
)]


class BacktestRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: Literal["LONG", "SHORT"]
    start: datetime
    end: datetime
    size_mode: Literal["BASE", "QUOTE", "RATE_ONLY"]
    size: Decimal | None = None


class FundingPaymentOut(BaseModel):
    timestamp: datetime
    rate: DecimalStr
    mark_price: DecimalStr
    quantity_base: DecimalStr
    notional_quote: DecimalStr
    payment_quote: DecimalStr


class BacktestResponse(BaseModel):
    event_count: int
    total_quote: DecimalStrOpt
    total_base: DecimalStrOpt
    cumulative_rate_pct: DecimalStr
    avg_rate_pct: DecimalStr
    annualized_pct: DecimalStr
    payments: list[FundingPaymentOut]


def to_backtest_response(r: BacktestResult) -> BacktestResponse:
    return BacktestResponse(
        event_count=r.event_count,
        total_quote=r.total_quote,
        total_base=r.total_base,
        cumulative_rate_pct=r.cumulative_rate_pct,
        avg_rate_pct=r.avg_rate * Decimal("100"),
        annualized_pct=r.apr * Decimal("100"),
        payments=[
            FundingPaymentOut(
                timestamp=p.event.timestamp,
                rate=p.event.rate,
                mark_price=p.event.mark_price,
                quantity_base=p.quantity_base,
                notional_quote=p.notional_quote,
                payment_quote=p.payment_quote,
            )
            for p in r.payments
        ],
    )


class HistoryRequest(BaseModel):
    account_name: str
    start: datetime
    end: datetime
    symbol: str | None = None


class IncomeRecordOut(BaseModel):
    timestamp: datetime
    symbol: str
    amount_usdt: DecimalStr
    tran_id: str


class HistoryPayload(BaseModel):
    start: datetime
    end: datetime
    total: DecimalStr
    by_symbol: dict[str, DecimalStr]
    by_month: dict[str, DecimalStr]
    records: list[IncomeRecordOut]


def to_history_payload(r: HistoryResult) -> HistoryPayload:
    return HistoryPayload(
        start=r.start, end=r.end, total=r.total,
        by_symbol=dict(r.by_symbol), by_month=dict(r.by_month),
        records=[
            IncomeRecordOut(
                timestamp=ir.timestamp, symbol=ir.symbol,
                amount_usdt=ir.amount_usdt, tran_id=ir.tran_id,
            )
            for ir in r.records
        ],
    )


class HistoryTaskStatus(BaseModel):
    status: Literal["pending", "running", "done", "failed"]
    progress: dict[str, int] | None = None
    result: HistoryPayload | None = None
    error: dict[str, str] | None = None


class HistorySubmitResponse(BaseModel):
    task_id: str
    status: Literal["pending"]


class AccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    label: str = Field(default="", max_length=128)
    api_key: str = Field(min_length=8, max_length=128)
    api_secret: str = Field(min_length=8, max_length=256)


class AccountPermissions(BaseModel):
    """对外暴露的 3 字段权限报告，与前端 labels.ts 的"只读/交易/提现"一一对应。
    `None` = 不确定（API 未返回该字段）。
    """
    read: bool | None
    trade: bool | None
    withdraw: bool | None


class AccountOut(BaseModel):
    name: str
    label: str
    created_at: datetime
    key_first6: str
    permissions: AccountPermissions


class AccountCreateResponse(BaseModel):
    account: AccountOut


def map_permission_report(report: PermissionReport) -> AccountPermissions:
    """core PermissionReport → 对外 3 字段（丢弃 spot_trading_enabled）。"""
    return AccountPermissions(
        read=report.read_ok,
        trade=report.trading_enabled,
        withdraw=report.withdrawals_enabled,
    )
