"""In-memory fake ExchangeProtocol implementation for service-layer tests."""

from dataclasses import dataclass, field
from datetime import datetime

from funding_tool.core.models import (
    ApiCredentials,
    FundingEvent,
    IncomeRecord,
    PermissionReport,
)


@dataclass
class FakeExchange:
    """In-memory ExchangeProtocol stand-in. Pass `funding_rates` and `income_records`
    directly; the fake filters them by symbol/time on demand."""

    name: str = "fake"
    interval_hours: int = 8
    funding_rates: list[FundingEvent] = field(default_factory=list)
    income_records: list[IncomeRecord] = field(default_factory=list)
    valid_symbols: set[str] = field(default_factory=lambda: {"BTCUSDT", "ETHUSDT"})
    verify_result: PermissionReport = field(default_factory=lambda: PermissionReport(
        read_ok=True, trading_enabled=False,
        withdrawals_enabled=False, spot_trading_enabled=False,
    ))

    # populated by fetch_funding_income — tests inspect it to assert filter args
    last_income_call: dict = field(default_factory=dict)

    async def fetch_funding_rates(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[FundingEvent]:
        return [
            e for e in self.funding_rates
            if e.symbol == symbol and start <= e.timestamp <= end
        ]

    async def fetch_funding_income(
        self,
        credentials: ApiCredentials,
        start: datetime,
        end: datetime,
        symbol: str | None = None,
    ) -> list[IncomeRecord]:
        self.last_income_call = {"start": start, "end": end, "symbol": symbol}
        return [
            r for r in self.income_records
            if start <= r.timestamp <= end
            and (symbol is None or r.symbol == symbol)
        ]

    async def get_interval_hours(self, symbol: str) -> int:
        return self.interval_hours

    async def validate_symbol(self, symbol: str) -> bool:
        return symbol in self.valid_symbols

    async def list_symbols(self) -> list[str]:
        """Return all tradeable USDT-M perpetual symbols."""
        return sorted(self.valid_symbols)

    async def verify_credentials(
        self, credentials: ApiCredentials
    ) -> PermissionReport:
        return self.verify_result
