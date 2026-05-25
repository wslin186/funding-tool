import pytest
from fastapi.testclient import TestClient

from tests.unit.web.conftest_app import build_app_for_test


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_app_for_test())


def test_csrf_requires_auth(client: TestClient) -> None:
    assert client.get("/api/csrf").status_code == 401


def test_csrf_sets_cookie_and_returns_token(client: TestClient, basic_auth_headers) -> None:
    r = client.get("/api/csrf", headers=basic_auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert len(body["token"]) > 20
    set_cookie = r.headers.get("set-cookie", "")
    assert "funding_csrf=" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=Strict" in set_cookie
    assert "Path=/funding/" in set_cookie


def test_csrf_token_matches_cookie_value(client: TestClient, basic_auth_headers) -> None:
    r = client.get("/api/csrf", headers=basic_auth_headers)
    token = r.json()["token"]
    cookie_val = r.cookies.get("funding_csrf")
    assert token == cookie_val
