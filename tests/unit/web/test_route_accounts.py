import asyncio

import pytest
from fastapi.testclient import TestClient

from tests.unit.web.conftest_app import build_app_for_test

ORIGIN = "https://example.com"
REFERER = "https://example.com/funding/accounts"


@pytest.fixture
def client(tmp_path) -> TestClient:
    return TestClient(build_app_for_test(tmp_path=tmp_path))


@pytest.fixture
def csrf(client: TestClient, basic_auth_headers) -> dict[str, str]:
    r = client.get("/api/csrf", headers=basic_auth_headers)
    token = r.json()["token"]
    return {
        "Authorization": basic_auth_headers["Authorization"],
        "X-Funding-Token": token,
        "Origin": ORIGIN,
        "Referer": REFERER,
        "Cookie": f"funding_csrf={token}",
    }


def test_create_account_requires_csrf(client: TestClient, basic_auth_headers) -> None:
    r = client.post(
        "/api/accounts",
        json={"name": "x", "label": "", "api_key": "AAAAAAAA", "api_secret": "SSSSSSSS"},
        headers=basic_auth_headers,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_mismatch"


def test_create_account_persists(client: TestClient, csrf) -> None:
    r = client.post(
        "/api/accounts",
        json={"name": "primary", "label": "main", "api_key": "ABCDEF123456", "api_secret": "top-secret-789"},
        headers=csrf,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["account"]["name"] == "primary"
    assert body["account"]["key_first6"] == "ABCDEF"
    assert body["account"]["permissions"]["read"] is True
    assert body["account"]["permissions"]["trade"] is False
    assert body["account"]["permissions"]["withdraw"] is False


def test_list_accounts_does_not_leak_secrets(client: TestClient, csrf) -> None:
    client.post(
        "/api/accounts",
        json={"name": "a", "label": "", "api_key": "ABCDEF1Z", "api_secret": "secretXX"},
        headers=csrf,
    )
    r = client.get("/api/accounts", headers={"Authorization": csrf["Authorization"]})
    assert r.status_code == 200
    txt = r.text
    assert "secretXX" not in txt
    assert "ABCDEF1Z" not in txt  # full key MUST NOT appear (only first 6: "ABCDEF")
    assert "ABCDEF" in txt  # first 6 IS exposed


def test_delete_account(client: TestClient, csrf) -> None:
    client.post(
        "/api/accounts",
        json={"name": "a", "label": "", "api_key": "ABCDEF12", "api_secret": "secretXX"},
        headers=csrf,
    )
    r = client.delete("/api/accounts/a", headers=csrf)
    assert r.status_code == 204
    r2 = client.get("/api/accounts", headers={"Authorization": csrf["Authorization"]})
    assert r2.json()["accounts"] == []


def test_duplicate_account_rejected(client: TestClient, csrf) -> None:
    body = {"name": "a", "label": "", "api_key": "ABCDEF12", "api_secret": "secretXX"}
    client.post("/api/accounts", json=body, headers=csrf)
    r = client.post("/api/accounts", json=body, headers=csrf)
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["field"] == "account_name"


def test_create_account_timeout(tmp_path, basic_auth_headers) -> None:
    from unittest.mock import MagicMock
    from funding_tool.core.exchanges.base import ExchangeProtocol

    app = build_app_for_test(tmp_path=tmp_path)

    def factory(creds=None):
        ex = MagicMock(spec=ExchangeProtocol)
        async def verify_credentials(credentials):
            raise asyncio.TimeoutError()
        ex.verify_credentials = verify_credentials
        return ex

    app.state.exchange_factory = factory
    client = TestClient(app)
    r = client.get("/api/csrf", headers=basic_auth_headers)
    token = r.json()["token"]
    headers = {
        "Authorization": basic_auth_headers["Authorization"],
        "X-Funding-Token": token,
        "Origin": ORIGIN,
        "Referer": REFERER,
        "Cookie": f"funding_csrf={token}",
    }
    r2 = client.post(
        "/api/accounts",
        json={"name": "x", "label": "", "api_key": "ABCDEF12", "api_secret": "secret-xx"},
        headers=headers,
    )
    assert r2.status_code == 502
    assert r2.json()["error"]["code"] == "network_error"
