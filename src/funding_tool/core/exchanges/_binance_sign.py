"""HMAC-SHA256 signing for Binance Futures API. Internal use only."""

import hashlib
import hmac


def sign_query(secret: str, query_string: str) -> str:
    """Return hex-encoded HMAC-SHA256 of `query_string` keyed by `secret`."""
    return hmac.new(
        secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
