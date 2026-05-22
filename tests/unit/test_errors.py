import pytest

from funding_tool.core.errors import (
    AuthenticationError,
    CacheCorruptionError,
    ConfigError,
    ExchangeError,
    FundingToolError,
    MissingCredentialsError,
    NetworkError,
    RateLimitError,
    UnknownSymbolError,
    ValidationError,
)


@pytest.mark.parametrize("cls", [
    ValidationError, UnknownSymbolError,
    AuthenticationError, MissingCredentialsError,
    RateLimitError, ExchangeError, NetworkError,
    CacheCorruptionError, ConfigError,
])
def test_all_errors_inherit_from_base(cls):
    err = cls("boom")
    assert isinstance(err, FundingToolError)
    assert str(err) == "boom"


def test_base_is_exception():
    assert issubclass(FundingToolError, Exception)
