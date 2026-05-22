from datetime import UTC, datetime
from decimal import Decimal

import pytest

from funding_tool.core.exchanges.base import ExchangeProtocol
from funding_tool.core.models import ApiCredentials, FundingEvent
from tests.fakes import FakeExchange


def test_fake_satisfies_protocol():
    fake: ExchangeProtocol = FakeExchange()  # type-check assignment
    assert fake.name == "fake"


@pytest.mark.asyncio
async def test_fake_fetch_returns_events_in_window():
    ev = FundingEvent(
        timestamp=datetime(2026, 1, 1, 8, tzinfo=UTC),
        symbol="BTCUSDT", rate=Decimal("0.0001"),
        mark_price=Decimal("50000"), interval_hours=8,
    )
    fake = FakeExchange(funding_rates=[ev])
    result = await fake.fetch_funding_rates(
        "BTCUSDT",
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert result == [ev]


@pytest.mark.asyncio
async def test_fake_fetch_funding_income_records_call_and_filters_by_symbol():
    from funding_tool.core.models import IncomeRecord
    rec_btc = IncomeRecord(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="BTCUSDT", amount_usdt=Decimal("1"), tran_id="t1",
    )
    rec_eth = IncomeRecord(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="ETHUSDT", amount_usdt=Decimal("2"), tran_id="t2",
    )
    fake = FakeExchange(income_records=[rec_btc, rec_eth])
    result = await fake.fetch_funding_income(
        ApiCredentials(api_key="k", api_secret="s"),
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 2, 1, tzinfo=UTC),
        symbol="BTCUSDT",
    )
    assert result == [rec_btc]
    assert fake.last_income_call["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_fake_verify_credentials_returns_report():
    from funding_tool.core.models import PermissionReport
    fake = FakeExchange()
    report = await fake.verify_credentials(ApiCredentials(api_key="k", api_secret="s"))
    assert isinstance(report, PermissionReport)
    assert report.read_ok is True


@pytest.mark.asyncio
async def test_fake_verify_credentials_customizable():
    from funding_tool.core.models import PermissionReport
    fake = FakeExchange(verify_result=PermissionReport(
        read_ok=True, trading_enabled=True,
        withdrawals_enabled=False, spot_trading_enabled=False,
    ))
    report = await fake.verify_credentials(ApiCredentials(api_key="k", api_secret="s"))
    assert report.trading_enabled is True
