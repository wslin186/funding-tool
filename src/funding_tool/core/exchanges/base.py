"""ExchangeProtocol: the abstraction every exchange implementation must satisfy."""

from datetime import datetime
from typing import Protocol

from funding_tool.core.models import (
    ApiCredentials,
    FundingEvent,
    IncomeRecord,
    PermissionReport,
)


class ExchangeProtocol(Protocol):
    name: str

    async def fetch_funding_rates(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[FundingEvent]: ...

    async def fetch_funding_income(
        self,
        credentials: ApiCredentials,
        start: datetime,
        end: datetime,
        symbol: str | None = None,
    ) -> list[IncomeRecord]: ...

    async def get_interval_hours(self, symbol: str) -> int: ...

    async def validate_symbol(self, symbol: str) -> bool: ...

    async def verify_credentials(
        self, credentials: ApiCredentials
    ) -> PermissionReport: ...
