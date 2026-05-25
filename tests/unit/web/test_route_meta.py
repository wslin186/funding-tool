import pytest
from fastapi.testclient import TestClient

from tests.unit.web.conftest_app import (
    build_app_for_test,
    get_list_symbols_call_count,
    reset_list_symbols_call_count,
)


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
    assert len(body["symbols"]) > 0
    assert all("BTC" in s for s in body["symbols"])


def test_symbols_cached(client: TestClient, basic_auth_headers) -> None:
    # Reset the route-level cache so this test is independent of test ordering.
    from funding_tool.web.routes import meta as meta_route
    meta_route._cache.clear()
    # Reset the call counter that tracks how many times the exchange was hit.
    reset_list_symbols_call_count()

    r1 = client.get("/api/symbols?q=ETH", headers=basic_auth_headers)
    r2 = client.get("/api/symbols?q=ETH", headers=basic_auth_headers)
    assert r1.json() == r2.json()
    # The exchange must have been called exactly once — the second request
    # should be served from the in-memory cache without hitting the exchange.
    assert get_list_symbols_call_count() == 1
