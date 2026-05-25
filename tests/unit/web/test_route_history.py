"""Integration tests for POST /api/history + GET /api/history/result/{id}."""
import time

import pytest
from fastapi.testclient import TestClient

from tests.unit.web.conftest_app import build_app_for_test


@pytest.fixture
def client(tmp_path):
    # ``with TestClient(...)`` keeps the anyio BlockingPortal/loop alive
    # across requests in the test, so the background asyncio.Task submitted
    # by /api/history can actually run before we poll.
    app = build_app_for_test(tmp_path=tmp_path)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def csrf_headers(client: TestClient, basic_auth_headers) -> dict[str, str]:
    r = client.get("/api/csrf", headers=basic_auth_headers)
    t = r.json()["token"]
    return {
        **basic_auth_headers,
        "X-Funding-Token": t,
        "Origin": "https://example.com",
        "Referer": "https://example.com/funding/history",
        "Cookie": f"funding_csrf={t}",
    }


def _create_account(client: TestClient, csrf_headers) -> None:
    client.post(
        "/api/accounts",
        json={
            "name": "primary",
            "label": "",
            "api_key": "ABCDEF12",
            "api_secret": "secretXXX",
        },
        headers=csrf_headers,
    )


def test_submit_returns_task_id(client: TestClient, csrf_headers) -> None:
    _create_account(client, csrf_headers)
    r = client.post(
        "/api/history",
        json={
            "account_name": "primary",
            "start": "2025-01-01T00:00:00Z",
            "end": "2025-02-01T00:00:00Z",
        },
        headers=csrf_headers,
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert len(body["task_id"]) == 32


def test_history_result_completes(client: TestClient, csrf_headers) -> None:
    _create_account(client, csrf_headers)
    r = client.post(
        "/api/history",
        json={
            "account_name": "primary",
            "start": "2025-01-01T00:00:00Z",
            "end": "2025-02-01T00:00:00Z",
        },
        headers=csrf_headers,
    )
    tid = r.json()["task_id"]
    final = None
    body = None
    for _ in range(50):
        s = client.get(
            f"/api/history/result/{tid}",
            headers={"Authorization": csrf_headers["Authorization"]},
        )
        body = s.json()
        if body["status"] in ("done", "failed"):
            final = body
            break
        time.sleep(0.05)
    assert final and final["status"] == "done", f"never completed: {body}"
    assert final["result"]["total"] == "10"


def test_history_unknown_task_id(client: TestClient, basic_auth_headers) -> None:
    r = client.get("/api/history/result/deadbeef", headers=basic_auth_headers)
    assert r.status_code == 404


def test_history_range_too_large(client: TestClient, csrf_headers) -> None:
    _create_account(client, csrf_headers)
    r = client.post(
        "/api/history",
        json={
            "account_name": "primary",
            "start": "2020-01-01T00:00:00Z",
            "end": "2025-01-01T00:00:00Z",
        },
        headers=csrf_headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "range_too_large"
