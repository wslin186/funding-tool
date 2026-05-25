import pytest
from fastapi.testclient import TestClient

from tests.unit.web.conftest_app import build_app_for_test


@pytest.fixture
def client() -> TestClient:
    app = build_app_for_test()
    return TestClient(app)


def test_health_is_anonymous(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_symbols_requires_auth(client: TestClient) -> None:
    r = client.get("/api/symbols?q=BTC")
    assert r.status_code == 401


def test_symbols_returns_filtered_list(client: TestClient, basic_auth_headers) -> None:
    r = client.get("/api/symbols?q=BTC", headers=basic_auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "symbols" in body
    assert all("BTC" in s for s in body["symbols"])


def test_symbols_cached(client: TestClient, basic_auth_headers) -> None:
    r1 = client.get("/api/symbols?q=ETH", headers=basic_auth_headers)
    r2 = client.get("/api/symbols?q=ETH", headers=basic_auth_headers)
    assert r1.json() == r2.json()
