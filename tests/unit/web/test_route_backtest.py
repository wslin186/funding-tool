import pytest
from fastapi.testclient import TestClient

from tests.unit.web.conftest_app import build_app_for_test


@pytest.fixture
def client(tmp_path) -> TestClient:
    return TestClient(build_app_for_test(tmp_path=tmp_path))


@pytest.fixture
def csrf_headers(client: TestClient, basic_auth_headers) -> dict[str, str]:
    r = client.get("/api/csrf", headers=basic_auth_headers)
    t = r.json()["token"]
    return {
        **basic_auth_headers,
        "X-Funding-Token": t,
        "Origin": "https://example.com",
        "Referer": "https://example.com/funding/backtest",
        "Cookie": f"funding_csrf={t}",
    }


def test_backtest_returns_payments(client: TestClient, csrf_headers) -> None:
    r = client.post("/api/backtest", json={
        "symbol": "BTCUSDT", "side": "LONG",
        "start": "2025-01-01T00:00:00Z", "end": "2025-01-02T00:00:00Z",
        "size_mode": "BASE", "size": "1.0",
    }, headers=csrf_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event_count"] == 1
    assert isinstance(body["total_quote"], str)
    assert isinstance(body["payments"][0]["payment_quote"], str)


def test_backtest_range_too_large_rejected(client: TestClient, csrf_headers) -> None:
    r = client.post("/api/backtest", json={
        "symbol": "BTCUSDT", "side": "LONG",
        "start": "2020-01-01T00:00:00Z", "end": "2025-01-01T00:00:00Z",
        "size_mode": "RATE_ONLY",
    }, headers=csrf_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "range_too_large"


def test_backtest_requires_csrf(client: TestClient, basic_auth_headers) -> None:
    r = client.post("/api/backtest", json={
        "symbol": "BTCUSDT", "side": "LONG",
        "start": "2025-01-01T00:00:00Z", "end": "2025-01-02T00:00:00Z",
        "size_mode": "RATE_ONLY",
    }, headers=basic_auth_headers)
    assert r.status_code == 403
