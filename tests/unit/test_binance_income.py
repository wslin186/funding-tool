import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from funding_tool.core.cache import SqliteFundingRateCache
from funding_tool.core.exchanges.binance_usdm import BinanceUsdmExchange
from funding_tool.core.models import ApiCredentials

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def exchange(tmp_path):
    return BinanceUsdmExchange(
        cache=SqliteFundingRateCache(tmp_path / "cache.db"),
        base_url="https://fapi.example.com",
    )


@pytest.fixture
def credentials():
    return ApiCredentials(api_key="testkey", api_secret="testsecret")


@pytest.mark.asyncio
async def test_fetch_funding_income_basic(exchange, credentials):
    sample = json.loads((FIXTURES / "income_sample.json").read_text())
    with respx.mock(base_url="https://fapi.example.com") as mock:
        mock.get("/fapi/v1/time").mock(
            return_value=httpx.Response(200, json={"serverTime": 1735689600000})
        )
        mock.get("/fapi/v1/income").mock(return_value=httpx.Response(200, json=sample))

        records = await exchange.fetch_funding_income(
            credentials,
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 2, tzinfo=UTC),
        )

    assert len(records) == 3
    assert records[0].amount_usdt == Decimal("-1.23")
    assert records[0].tran_id == "1001"


@pytest.mark.asyncio
async def test_fetch_funding_income_segments_7_day_windows(exchange, credentials):
    """A 21-day request window should result in 3 outer windows (each <= 7 days)."""
    with respx.mock(base_url="https://fapi.example.com") as mock:
        mock.get("/fapi/v1/time").mock(
            return_value=httpx.Response(200, json={"serverTime": 1735689600000})
        )
        route = mock.get("/fapi/v1/income").mock(return_value=httpx.Response(200, json=[]))

        await exchange.fetch_funding_income(
            credentials,
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 22, tzinfo=UTC),  # 21 days
        )
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_verify_credentials_read_only_key(exchange, credentials):
    """Read-only key: /fapi/v3/balance OK, apiRestrictions reports no trading/withdraw."""
    with respx.mock(base_url="https://fapi.example.com") as mock:
        mock.get("/fapi/v1/time").mock(
            return_value=httpx.Response(200, json={"serverTime": 1735689600000})
        )
        mock.get("/fapi/v3/balance").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/sapi/v1/account/apiRestrictions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "enableReading": True,
                    "enableFutures": False,
                    "enableMargin": False,
                    "enableWithdrawals": False,
                    "enableSpotAndMarginTrading": False,
                },
            )
        )
        report = await exchange.verify_credentials(credentials)
    assert report.read_ok is True
    assert report.trading_enabled is False
    assert report.withdrawals_enabled is False


@pytest.mark.asyncio
async def test_verify_credentials_warns_on_trading_enabled(exchange, credentials):
    """If apiRestrictions reports enableFutures=true, report.trading_enabled is True."""
    with respx.mock(base_url="https://fapi.example.com") as mock:
        mock.get("/fapi/v1/time").mock(
            return_value=httpx.Response(200, json={"serverTime": 1735689600000})
        )
        mock.get("/fapi/v3/balance").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/sapi/v1/account/apiRestrictions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "enableReading": True,
                    "enableFutures": True,
                    "enableMargin": False,
                    "enableWithdrawals": True,
                    "enableSpotAndMarginTrading": False,
                },
            )
        )
        report = await exchange.verify_credentials(credentials)
    assert report.read_ok is True
    assert report.trading_enabled is True
    assert report.withdrawals_enabled is True


@pytest.mark.asyncio
async def test_verify_credentials_balance_failure_raises(exchange, credentials):
    """A signed /fapi/v3/balance returning Binance error code -2014 raises AuthenticationError."""
    from funding_tool.core.errors import AuthenticationError

    with respx.mock(base_url="https://fapi.example.com") as mock:
        mock.get("/fapi/v1/time").mock(
            return_value=httpx.Response(200, json={"serverTime": 1735689600000})
        )
        mock.get("/fapi/v3/balance").mock(
            return_value=httpx.Response(
                400, json={"code": -2014, "msg": "API-key format invalid."},
            )
        )
        with pytest.raises(AuthenticationError):
            await exchange.verify_credentials(credentials)


@pytest.mark.asyncio
async def test_verify_credentials_apirestrictions_404_is_non_fatal(exchange, credentials):
    """Older keys don't have apiRestrictions endpoint - we still return read_ok=True."""
    with respx.mock(base_url="https://fapi.example.com") as mock:
        mock.get("/fapi/v1/time").mock(
            return_value=httpx.Response(200, json={"serverTime": 1735689600000})
        )
        mock.get("/fapi/v3/balance").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/sapi/v1/account/apiRestrictions").mock(return_value=httpx.Response(404))
        report = await exchange.verify_credentials(credentials)
    assert report.read_ok is True
    # Advisory fields stay None when we couldn't read them
    assert report.trading_enabled is None
    assert report.withdrawals_enabled is None


@pytest.mark.asyncio
async def test_fetch_funding_income_dedupes_tran_id(exchange, credentials):
    """Boundary rows returned twice (one per page) must be deduped by tranId."""
    page1 = [
        {
            "symbol": "BTCUSDT",
            "incomeType": "FUNDING_FEE",
            "income": "-1",
            "asset": "USDT",
            "time": 1735689600000,
            "info": "FUNDING_FEE",
            "tranId": "1001",
            "tradeId": "",
        }
    ] * 1000
    # Same tranId 1001 appears on page 1 boundary AND page 2 boundary
    page2 = [
        {
            "symbol": "BTCUSDT",
            "incomeType": "FUNDING_FEE",
            "income": "-1",
            "asset": "USDT",
            "time": 1735689600000 + i,
            "info": "FUNDING_FEE",
            "tranId": f"{1001 + i}",
            "tradeId": "",
        }
        for i in range(500)
    ]

    with respx.mock(base_url="https://fapi.example.com") as mock:
        mock.get("/fapi/v1/time").mock(
            return_value=httpx.Response(200, json={"serverTime": 1735689600000})
        )
        route = mock.get("/fapi/v1/income")
        route.side_effect = [
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ]
        records = await exchange.fetch_funding_income(
            credentials,
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 2, tzinfo=UTC),  # within 7 days, single outer window
        )

    # 1000 page1 entries (all tranId=1001 -> dedupes to 1) + 500 page2 entries
    # (1001..1500, of which 1001 already seen -> 499 new)
    tran_ids = {r.tran_id for r in records}
    assert "1001" in tran_ids
    assert len(records) == 500  # 1 from page1 + 499 new from page2
