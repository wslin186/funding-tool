"""CSRF guard: token + Origin/Referer strict match against canonical PUBLIC_ORIGIN."""
from __future__ import annotations

import secrets
from urllib.parse import urlparse


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
        parsed = urlparse(public_origin.rstrip("/"))
        if parsed.scheme != "https":
            raise ValueError(f"public_origin must be https://, got {public_origin!r}")
        if not parsed.netloc:
            raise ValueError(f"public_origin missing host, got {public_origin!r}")
        if parsed.path:
            raise ValueError(f"public_origin must not contain a path, got {public_origin!r}")
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
        if not referer:
            raise CsrfError(f"bad referer: {referer!r}")
        ref_parsed = urlparse(referer)
        expected = urlparse(self._public_origin)
        if (
            ref_parsed.scheme != expected.scheme
            or ref_parsed.netloc != expected.netloc
            or not ref_parsed.path.startswith("/funding/")
            or ".." in ref_parsed.path.split("/")
        ):
            raise CsrfError(f"bad referer: {referer!r}")
