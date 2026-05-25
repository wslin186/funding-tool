import pytest
from funding_tool.core.errors import (
    AuthenticationError, NetworkError, RateLimitError,
    UnknownSymbolError, ValidationError as CoreValidationError,
    ExchangeError,
)
from funding_tool.web.errors import map_core_exception, WebError


@pytest.mark.parametrize("exc, code, status", [
    (UnknownSymbolError("BTC"), "unknown_symbol", 404),
    (CoreValidationError("x"), "validation_error", 400),
    (AuthenticationError("x"), "exchange_auth_error", 502),
    (RateLimitError("x"), "exchange_rate_limit", 502),
    (NetworkError("x"), "network_error", 502),
    (ExchangeError("x"), "exchange_error", 502),
])
def test_core_exception_mapping(exc: Exception, code: str, status: int) -> None:
    web = map_core_exception(exc)
    assert isinstance(web, WebError)
    assert web.code == code
    assert web.http_status == status


def test_unknown_exception_maps_to_server_error() -> None:
    web = map_core_exception(RuntimeError("boom"))
    assert web.code == "server_error"
    assert web.http_status == 500
    assert web.error_id  # uuid set
