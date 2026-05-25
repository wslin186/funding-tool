"""Translate core exceptions to web error codes + HTTP status."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from funding_tool.core.errors import (
    AuthenticationError, ExchangeError, NetworkError, RateLimitError,
    UnknownSymbolError, ValidationError as CoreValidationError,
)

WebCode = Literal[
    "web_auth_required", "web_auth_locked", "csrf_mismatch",
    "validation_error", "range_too_large", "unknown_symbol",
    "exchange_auth_error", "exchange_rate_limit", "network_error",
    "exchange_error", "server_error",
]


@dataclass
class WebError:
    code: WebCode
    http_status: int
    message: str
    field: str | None = None
    error_id: str | None = None


_FIELD_WHITELIST = {
    "symbol", "side", "start", "end", "size_mode", "size",
    "account_name", "api_key",
}


def safe_field(name: str | None) -> str | None:
    if name is None:
        return None
    return name if name in _FIELD_WHITELIST else "请求参数"


def map_core_exception(exc: BaseException) -> WebError:
    if isinstance(exc, UnknownSymbolError):
        return WebError("unknown_symbol", 404, "币安没有这个合约，请检查拼写")
    if isinstance(exc, CoreValidationError):
        return WebError("validation_error", 400, "输入参数有问题")
    if isinstance(exc, AuthenticationError):
        return WebError("exchange_auth_error", 502, "Binance 接口拒绝了请求，请检查账户")
    if isinstance(exc, RateLimitError):
        return WebError("exchange_rate_limit", 502, "币安限流，请稍后重试")
    if isinstance(exc, NetworkError):
        return WebError("network_error", 502, "网络异常")
    if isinstance(exc, ExchangeError):
        return WebError("exchange_error", 502, "币安接口异常")
    return WebError(
        "server_error", 500, "服务器错误（已记录）",
        error_id=str(uuid.uuid4()),
    )
