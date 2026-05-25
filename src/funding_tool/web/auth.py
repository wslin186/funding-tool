"""HTTP Basic Auth with bcrypt + per-IP lockout."""
from __future__ import annotations

import base64
import secrets
import time
from dataclasses import dataclass
from threading import Lock
from typing import Literal

import bcrypt

AuthCode = Literal["web_auth_required", "web_auth_locked"]


class AuthError(Exception):
    def __init__(self, code: AuthCode) -> None:
        super().__init__(code)
        self.code: AuthCode = code


@dataclass
class _IpState:
    failures: int = 0
    locked_until: float = 0.0


class AuthVerifier:
    def __init__(
        self,
        *,
        username: str,
        password_hash: bytes,
        lockout_max: int = 5,
        lockout_secs: int = 300,
    ) -> None:
        self._username = username
        self._password_hash = password_hash
        self._lockout_max = lockout_max
        self._lockout_secs = lockout_secs
        self._state: dict[str, _IpState] = {}
        self._lock = Lock()

    def verify(self, *, ip: str, header: str | None) -> str:
        with self._lock:
            st = self._state.setdefault(ip, _IpState())
            now = time.monotonic()
            if st.locked_until > now:
                raise AuthError("web_auth_locked")

        if header is None or not header.startswith("Basic "):
            self._record_failure(ip)
            raise AuthError("web_auth_required")

        try:
            decoded = base64.b64decode(header[6:].strip(), validate=True).decode()
            user, _, pw = decoded.partition(":")
        except Exception as e:
            self._record_failure(ip)
            raise AuthError("web_auth_required") from e

        user_ok = secrets.compare_digest(user.encode(), self._username.encode())
        pw_ok = bcrypt.checkpw(pw.encode(), self._password_hash)
        if not (user_ok and pw_ok):
            self._record_failure(ip)
            raise AuthError("web_auth_required")

        with self._lock:
            self._state[ip] = _IpState()
        return self._username

    def reset(self, ip: str) -> None:
        with self._lock:
            self._state.pop(ip, None)

    def _record_failure(self, ip: str) -> None:
        with self._lock:
            st = self._state.setdefault(ip, _IpState())
            st.failures += 1
            if st.failures >= self._lockout_max:
                st.locked_until = time.monotonic() + self._lockout_secs


_LOOPBACK = {"127.0.0.1", "::1"}


def extract_client_ip(request, *, trust_loopback: bool = True) -> str:  # type: ignore[no-untyped-def]
    peer = request.client.host if request.client else "0.0.0.0"
    if trust_loopback and peer in _LOOPBACK:
        xri = request.headers.get("X-Real-IP")
        if xri:
            return xri.strip()
    return peer
