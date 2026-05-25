import logging

import httpx
import pytest
import respx

from funding_tool.core.errors import NetworkError, RateLimitError
from funding_tool.infra.http import HttpClient


@pytest.mark.asyncio
async def test_get_returns_json():
    async with HttpClient(base_url="https://fapi.example.com") as client:
        with respx.mock(base_url="https://fapi.example.com") as mock:
            mock.get("/fapi/v1/ping").mock(return_value=httpx.Response(200, json={"ok": 1}))
            result = await client.get_json("/fapi/v1/ping")
        assert result == {"ok": 1}


@pytest.mark.asyncio
async def test_retry_on_5xx():
    async with HttpClient(base_url="https://fapi.example.com", retry_attempts=3, retry_base_sleep=0) as client:
        with respx.mock(base_url="https://fapi.example.com") as mock:
            route = mock.get("/fapi/v1/ping")
            route.side_effect = [
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, json={"ok": 1}),
            ]
            result = await client.get_json("/fapi/v1/ping")
            assert result == {"ok": 1}
            assert route.call_count == 3


@pytest.mark.asyncio
async def test_no_retry_on_401():
    async with HttpClient(base_url="https://fapi.example.com", retry_attempts=3, retry_base_sleep=0) as client:
        with respx.mock(base_url="https://fapi.example.com") as mock:
            route = mock.get("/fapi/v1/ping").mock(return_value=httpx.Response(401, json={"msg": "bad key"}))
            from funding_tool.core.errors import AuthenticationError
            with pytest.raises(AuthenticationError):
                await client.get_json("/fapi/v1/ping")
            assert route.call_count == 1


@pytest.mark.asyncio
async def test_429_raises_rate_limit_after_retries():
    async with HttpClient(base_url="https://fapi.example.com", retry_attempts=2, retry_base_sleep=0) as client:
        with respx.mock(base_url="https://fapi.example.com") as mock:
            mock.get("/fapi/v1/ping").mock(return_value=httpx.Response(429))
            with pytest.raises(RateLimitError):
                await client.get_json("/fapi/v1/ping")


@pytest.mark.asyncio
async def test_network_error_wrapped():
    async with HttpClient(base_url="https://fapi.example.com", retry_attempts=1, retry_base_sleep=0) as client:
        with respx.mock(base_url="https://fapi.example.com") as mock:
            mock.get("/fapi/v1/ping").mock(side_effect=httpx.ConnectError("boom"))
            with pytest.raises(NetworkError):
                await client.get_json("/fapi/v1/ping")


@pytest.mark.asyncio
async def test_request_debug_log_is_scrubbed(caplog: pytest.LogCaptureFixture) -> None:
    """Sensitive params (api_key, signature) must not appear verbatim in DEBUG logs.

    The http client logs each outgoing request via the scrubbing logger;
    this is the one place credentials enter the wire and the whole point of
    routing through ScrubbingFilter.
    """
    caplog.set_level(logging.DEBUG, logger="funding_tool.infra.http")
    async with HttpClient(base_url="https://fapi.example.com") as client:
        with respx.mock(base_url="https://fapi.example.com") as mock:
            mock.get("/fapi/v1/income").mock(return_value=httpx.Response(200, json=[]))
            await client.get_json(
                "/fapi/v1/income",
                params={
                    "symbol": "BTCUSDT",
                    "api_key": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                    "signature": "deadbeefcafe1234567890abcdef",
                },
            )

    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "GHIJKLMNOPQRSTUVWXYZ" not in log_text  # full key value gone
    assert "deadbeefcafe1234567890abcdef" not in log_text  # signature gone
    assert "BTCUSDT" in log_text  # non-sensitive value preserved


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectTimeout("connect timed out"),
        httpx.PoolTimeout("pool exhausted"),
        httpx.TransportError("dns failure"),
    ],
)
async def test_transport_error_subclasses_wrapped_to_network_error(exc: httpx.TransportError) -> None:
    """ConnectTimeout/PoolTimeout/generic TransportError must reach the CLI as NetworkError.

    These are NOT subclasses of ConnectError, so they used to bypass the narrow
    handler and surface as raw tracebacks (CLI only catches FundingToolError).
    """
    async with HttpClient(base_url="https://fapi.example.com", retry_attempts=1, retry_base_sleep=0) as client:
        with respx.mock(base_url="https://fapi.example.com") as mock:
            mock.get("/fapi/v1/ping").mock(side_effect=exc)
            with pytest.raises(NetworkError):
                await client.get_json("/fapi/v1/ping")


@pytest.mark.asyncio
async def test_binance_error_code_1003_maps_to_rate_limit():
    """Binance returns 200 OK with JSON body {"code": -1003, "msg": "..."} for rate limits."""
    async with HttpClient(base_url="https://fapi.example.com", retry_attempts=1, retry_base_sleep=0) as client:
        with respx.mock(base_url="https://fapi.example.com") as mock:
            mock.get("/fapi/v1/ping").mock(return_value=httpx.Response(
                418, json={"code": -1003, "msg": "Way too many requests"},
            ))
            with pytest.raises(RateLimitError):
                await client.get_json("/fapi/v1/ping")


@pytest.mark.asyncio
async def test_binance_error_code_2014_maps_to_auth_error():
    """Binance error codes -2014/-2015 mean invalid API key / signature."""
    from funding_tool.core.errors import AuthenticationError
    async with HttpClient(base_url="https://fapi.example.com", retry_attempts=1, retry_base_sleep=0) as client:
        with respx.mock(base_url="https://fapi.example.com") as mock:
            mock.get("/fapi/v1/ping").mock(return_value=httpx.Response(
                400, json={"code": -2014, "msg": "API-key format invalid"},
            ))
            with pytest.raises(AuthenticationError):
                await client.get_json("/fapi/v1/ping")


@pytest.mark.asyncio
async def test_binance_status_418_maps_to_exchange_error():
    """418 'I'm a teapot' = IP banned for hitting rate limits — not retryable."""
    from funding_tool.core.errors import ExchangeError
    async with HttpClient(base_url="https://fapi.example.com", retry_attempts=3, retry_base_sleep=0) as client:
        with respx.mock(base_url="https://fapi.example.com") as mock:
            route = mock.get("/fapi/v1/ping").mock(return_value=httpx.Response(
                418, json={},  # no Binance code field → status-only
            ))
            with pytest.raises(ExchangeError):
                await client.get_json("/fapi/v1/ping")
            # IP-ban is not retryable: should be called exactly once
            assert route.call_count == 1
