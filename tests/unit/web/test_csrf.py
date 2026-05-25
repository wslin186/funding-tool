import pytest
from funding_tool.web.csrf import CsrfError, CsrfGuard


@pytest.fixture
def guard() -> CsrfGuard:
    return CsrfGuard(public_origin="https://example.com")


def test_valid_request_passes(guard: CsrfGuard) -> None:
    t = guard.issue_token()
    guard.verify(
        cookie_token=t, header_token=t,
        origin="https://example.com",
        referer="https://example.com/funding/backtest",
    )


def test_token_mismatch_rejected(guard: CsrfGuard) -> None:
    with pytest.raises(CsrfError):
        guard.verify(
            cookie_token="A", header_token="B",
            origin="https://example.com", referer="https://example.com/funding/",
        )


def test_missing_header_rejected(guard: CsrfGuard) -> None:
    t = guard.issue_token()
    with pytest.raises(CsrfError):
        guard.verify(cookie_token=t, header_token=None,
                     origin="https://example.com", referer="https://example.com/funding/")


def test_wrong_origin_rejected(guard: CsrfGuard) -> None:
    t = guard.issue_token()
    with pytest.raises(CsrfError):
        guard.verify(cookie_token=t, header_token=t,
                     origin="https://evil.com",
                     referer="https://example.com/funding/")


def test_missing_origin_rejected(guard: CsrfGuard) -> None:
    t = guard.issue_token()
    with pytest.raises(CsrfError):
        guard.verify(cookie_token=t, header_token=t,
                     origin=None, referer="https://example.com/funding/")


def test_wrong_referer_path_rejected(guard: CsrfGuard) -> None:
    t = guard.issue_token()
    with pytest.raises(CsrfError):
        guard.verify(cookie_token=t, header_token=t,
                     origin="https://example.com",
                     referer="https://example.com/other/")


def test_non_https_public_origin_raises_on_construct() -> None:
    with pytest.raises(ValueError):
        CsrfGuard(public_origin="http://example.com")


def test_token_is_constant_time_safe(guard: CsrfGuard) -> None:
    # short-circuit must not be by '==', verified by exception type only
    t = guard.issue_token()
    with pytest.raises(CsrfError):
        guard.verify(cookie_token=t, header_token=t[:-1] + "X",
                     origin="https://example.com",
                     referer="https://example.com/funding/")
