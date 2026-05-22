"""Exception hierarchy. All raised errors inherit from FundingToolError."""


class FundingToolError(Exception):
    """Base class for all tool errors."""


class ValidationError(FundingToolError):
    """User-supplied parameters failed validation."""


class UnknownSymbolError(FundingToolError):
    """Symbol not found on the exchange."""


class AuthenticationError(FundingToolError):
    """API key/secret invalid or lacking required permissions."""


class MissingCredentialsError(FundingToolError):
    """No credentials available for an authenticated operation."""


class RateLimitError(FundingToolError):
    """Exchange rate limit exceeded (retryable after backoff)."""


class ExchangeError(FundingToolError):
    """Generic exchange-side error (non-auth, non-rate-limit)."""


class NetworkError(FundingToolError):
    """Connection failure, timeout, DNS, etc."""


class CacheCorruptionError(FundingToolError):
    """Local SQLite cache integrity check failed."""


class ConfigError(FundingToolError):
    """Account config file is malformed or unreadable."""
