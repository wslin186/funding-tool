"""CSRF guard: token + Origin/Referer strict match against canonical PUBLIC_ORIGIN."""
from __future__ import annotations

import secrets


class CsrfError(Exception):
    code = "csrf_mismatch"


class CsrfGuard:
    def __init__(
        self,
        *,
        public_origin: str,
        cookie_name: str = "funding_csrf",
        header_name: str = "X-Funding-Token",
    ) -> None:
        if not public_origin.startswith("https://"):
            raise ValueError(f"public_origin must be https://, got {public_origin!r}")
        self._public_origin = public_origin.rstrip("/")
        self._referer_prefix = f"{self._public_origin}/funding/"
        self.cookie_name = cookie_name
        self.header_name = header_name

    def issue_token(self) -> str:
        return secrets.token_urlsafe(32)

    def verify(
        self,
        *,
        cookie_token: str | None,
        header_token: str | None,
        origin: str | None,
        referer: str | None,
    ) -> None:
        if not cookie_token or not header_token:
            raise CsrfError("missing token")
        if not secrets.compare_digest(cookie_token, header_token):
            raise CsrfError("token mismatch")
        if origin != self._public_origin:
            raise CsrfError(f"bad origin: {origin!r}")
        if not referer or not referer.startswith(self._referer_prefix):
            raise CsrfError(f"bad referer: {referer!r}")
