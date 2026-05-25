import base64
import bcrypt
import pytest
from unittest.mock import MagicMock

from funding_tool.web.auth import AuthError, AuthVerifier, extract_client_ip


def _hash(pw: str) -> bytes:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=4))


def _basic(user: str, pw: str) -> str:
    raw = f"{user}:{pw}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def test_correct_credentials_pass() -> None:
    v = AuthVerifier(username="admin", password_hash=_hash("s3cret"))
    assert v.verify(ip="1.1.1.1", header=_basic("admin", "s3cret")) == "admin"


def test_missing_header_raises_required() -> None:
    v = AuthVerifier(username="admin", password_hash=_hash("s3cret"))
    with pytest.raises(AuthError) as ei:
        v.verify(ip="1.1.1.1", header=None)
    assert ei.value.code == "web_auth_required"


def test_wrong_password_raises_required() -> None:
    v = AuthVerifier(username="admin", password_hash=_hash("s3cret"))
    with pytest.raises(AuthError) as ei:
        v.verify(ip="1.1.1.1", header=_basic("admin", "WRONG"))
    assert ei.value.code == "web_auth_required"


def test_lockout_after_5_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    v = AuthVerifier(username="admin", password_hash=_hash("s3cret"), lockout_max=5, lockout_secs=300)
    for _ in range(5):
        with pytest.raises(AuthError):
            v.verify(ip="9.9.9.9", header=_basic("admin", "X"))
    # 6th attempt — even correct password should be locked
    with pytest.raises(AuthError) as ei:
        v.verify(ip="9.9.9.9", header=_basic("admin", "s3cret"))
    assert ei.value.code == "web_auth_locked"


def test_lockout_isolated_per_ip() -> None:
    v = AuthVerifier(username="admin", password_hash=_hash("s3cret"), lockout_max=3, lockout_secs=300)
    for _ in range(3):
        with pytest.raises(AuthError):
            v.verify(ip="1.1.1.1", header=_basic("admin", "X"))
    # different IP unaffected
    assert v.verify(ip="2.2.2.2", header=_basic("admin", "s3cret")) == "admin"


def test_extract_client_ip_trusts_xrealip_from_loopback() -> None:
    req = MagicMock()
    req.client.host = "127.0.0.1"
    req.headers = {"X-Real-IP": "9.9.9.9"}
    assert extract_client_ip(req) == "9.9.9.9"


def test_extract_client_ip_ignores_xrealip_from_remote() -> None:
    req = MagicMock()
    req.client.host = "8.8.8.8"
    req.headers = {"X-Real-IP": "9.9.9.9"}
    assert extract_client_ip(req) == "8.8.8.8"


def test_extract_client_ip_falls_back_when_no_header() -> None:
    req = MagicMock()
    req.client.host = "127.0.0.1"
    req.headers = {}
    assert extract_client_ip(req) == "127.0.0.1"


def test_init_rejects_non_bcrypt_hash() -> None:
    with pytest.raises(ValueError):
        AuthVerifier(username="admin", password_hash=b"not-a-bcrypt-hash")


def test_state_evicts_oldest_when_capped() -> None:
    v = AuthVerifier(username="admin", password_hash=_hash("s"), lockout_max=10, lockout_secs=300, state_max=2)
    for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        with pytest.raises(AuthError):
            v.verify(ip=ip, header=_basic("admin", "WRONG"))
    # 1.1.1.1 should be evicted; the other two still tracked
    assert "1.1.1.1" not in v._state
    assert "2.2.2.2" in v._state
    assert "3.3.3.3" in v._state
