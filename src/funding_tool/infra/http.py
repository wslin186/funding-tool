"""Async HTTP client wrapper with retry, backoff, and error mapping."""

from __future__ import annotations

import asyncio
import random
from types import TracebackType
from typing import Any

import httpx

from funding_tool.core.errors import (
    AuthenticationError,
    ExchangeError,
    NetworkError,
    RateLimitError,
)
from funding_tool.infra.log import get_logger

logger = get_logger(__name__)

# Binance error codes we map to specific exception types.
# See https://binance-docs.github.io/apidocs/futures/en/#error-codes for the full list.
_BINANCE_RATE_LIMIT_CODE = -1003
_BINANCE_AUTH_CODES = frozenset({-2014, -2015, -1022, -1099, -2008})


def _extract_binance_code(resp: httpx.Response) -> int | None:
    """Return Binance's JSON `code` field if present and parseable, else None."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return None
    if isinstance(body, dict):
        code = body.get("code")
        if isinstance(code, int):
            return code
    return None


class HttpClient:
    """Async HTTP client. Use as `async with HttpClient(...) as c:`.

    Retries idempotent GETs on 5xx / 429 / network errors with exponential backoff.
    Maps Binance error codes to FundingToolError subclasses.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_connect: float = 5.0,
        timeout_read: float = 15.0,
        retry_attempts: int = 3,
        retry_base_sleep: float = 1.0,
    ) -> None:
        self._base_url = base_url
        self._retry_attempts = retry_attempts
        self._retry_base_sleep = retry_base_sleep
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(
                connect=timeout_connect,
                read=timeout_read,
                write=timeout_read,
                pool=timeout_read,
            ),
        )

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self._retry_attempts):
            # Log via the scrubbing logger — `params` may contain `api_key`,
            # `signature`, and other secrets which ScrubbingFilter masks before
            # the record reaches any handler.
            logger.debug("-> GET %s params=%s", path, params)
            try:
                resp = await self._client.get(path, params=params, headers=headers)
            except httpx.TransportError as exc:
                # TransportError is the parent of ConnectError, ConnectTimeout,
                # ReadTimeout, WriteTimeout, PoolTimeout, and bare DNS/transport
                # failures. Catching the parent ensures none of them slip past
                # the wrapper and surface as a raw traceback at the CLI boundary.
                last_exc = exc
                await self._sleep(attempt)
                continue

            # Map by Binance error code first if the body has one — codes are more
            # specific than HTTP status (e.g. -1003 in a 418 means rate limit; a
            # bare 418 with no code means IP ban).
            binance_code = _extract_binance_code(resp)

            if binance_code in _BINANCE_AUTH_CODES or resp.status_code in (401, 403):
                raise AuthenticationError(
                    f"{resp.status_code} code={binance_code}: {resp.text}"
                )

            if binance_code == _BINANCE_RATE_LIMIT_CODE or resp.status_code == 429:
                last_exc = RateLimitError(f"{resp.status_code}: {resp.text}")
                await self._sleep(attempt, resp.headers.get("Retry-After"))
                continue

            if resp.status_code == 418:
                # IP banned: not retryable, surface immediately.
                raise ExchangeError(f"418 IP banned: {resp.text}")

            if 500 <= resp.status_code < 600:
                last_exc = ExchangeError(f"{resp.status_code}: {resp.text}")
                await self._sleep(attempt)
                continue

            if resp.status_code >= 400:
                raise ExchangeError(f"{resp.status_code}: {resp.text}")

            logger.debug("<- %s %s (%d bytes)", resp.status_code, path, len(resp.content))
            return resp.json()

        if isinstance(last_exc, RateLimitError):
            raise last_exc
        if isinstance(last_exc, ExchangeError):
            raise last_exc
        raise NetworkError(str(last_exc) if last_exc else "unknown network failure")

    async def _sleep(self, attempt: int, retry_after: str | None = None) -> None:
        if retry_after:
            try:
                await asyncio.sleep(float(retry_after))
                return
            except ValueError:
                pass
        sleep_for = self._retry_base_sleep * (2 ** attempt) + random.uniform(0, 0.1)
        await asyncio.sleep(sleep_for)
