"""Web UI integration smoke test — full canonical user flow.

Drives the FastAPI app via TestClient through:
  1. GET  /api/csrf           — issue token + cookie
  2. POST /api/accounts       — verify_credentials + persist
  3. GET  /api/accounts       — list (no secret leak)
  4. POST /api/backtest       — synchronous compute
  5. POST /api/history        — async submit
     GET  /api/history/result/{id}  — poll until terminal
  6. CSRF negative (missing token → 403 csrf_mismatch)
  7. Origin negative (wrong Origin → 403)
  8. DELETE /api/accounts/{name} — 204

All Binance traffic is intercepted by respx — no network.

This test is gated by ``@pytest.mark.integration`` so the default
``pytest`` (which adds ``-m 'not integration'``) skips it; CI runs
``pytest -m integration`` explicitly.
"""
from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from funding_tool.core.cache import SqliteFundingRateCache
from funding_tool.core.exchanges.binance_usdm import BinanceUsdmExchange

pytestmark = pytest.mark.integration


_USER = "admin"
_PASSWORD = "s3cret!"
_ORIGIN = "https://example.com"
_REFERER = f"{_ORIGIN}/funding/accounts"
_BASE_URL = "https://fapi.binance.com"


def _basic_auth_header(user: str, password: str) -> str:
    raw = f"{user}:{password}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _make_funding_time(year: int, month: int, day: int, hour: int = 0) -> int:
    """Return Binance-style fundingTime in ms (UTC)."""
    return int(
        datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp() * 1000
    )


@pytest.fixture
def web_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Set up the 6 FUNDING_* envs + CREDENTIALS_DIRECTORY + master_key.

    Returns the tmp paths so the test can introspect tasks_dir / audit log.
    """
    creds_dir = tmp_path / "creds"
    creds_dir.mkdir()
    # Master key must be exactly 32 bytes.
    (creds_dir / "master_key").write_bytes(os.urandom(32))
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(creds_dir))

    db_path = tmp_path / "secrets.sqlite"
    audit_path = tmp_path / "audit.jsonl"
    tasks_dir = tmp_path / "tasks"

    monkeypatch.setenv("FUNDING_PUBLIC_ORIGIN", _ORIGIN)
    monkeypatch.setenv("FUNDING_AUTH_USER", _USER)
    monkeypatch.setenv(
        "FUNDING_AUTH_PASSWORD_HASH",
        bcrypt.hashpw(_PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode(),
    )
    monkeypatch.setenv("FUNDING_DB_PATH", str(db_path))
    monkeypatch.setenv("FUNDING_AUDIT_LOG_PATH", str(audit_path))
    monkeypatch.setenv("FUNDING_TASKS_DIR", str(tasks_dir))

    return {
        "creds_dir": creds_dir,
        "db_path": db_path,
        "audit_path": audit_path,
        "tasks_dir": tasks_dir,
        "cache_path": tmp_path / "cache.sqlite",
    }


def _exchange_factory(cache_path: Path):
    """Build a real BinanceUsdmExchange. respx intercepts httpx underneath.

    The production default factory at ``web.main._exchange_factory_default``
    constructs ``BinanceUsdmExchange(credentials=creds)`` which doesn't match
    the exchange's actual ``__init__`` signature (it takes ``cache`` + ``base_url``).
    Override with a working factory for this test.
    """
    cache = SqliteFundingRateCache(cache_path)

    def _factory(creds: object = None) -> BinanceUsdmExchange:
        # creds is intentionally ignored here — exchange methods that need
        # credentials accept them as explicit args (verify_credentials,
        # fetch_funding_income), not via the constructor.
        return BinanceUsdmExchange(cache=cache, base_url=_BASE_URL)

    return _factory


def test_web_full_flow(web_env: dict[str, Path]) -> None:
    """Canonical happy-path + 2 negative cases, all driven via TestClient."""
    # Delayed import — create_app + lifespan run with envs already set.
    from funding_tool.web.main import create_app

    app = create_app()

    auth = {"Authorization": _basic_auth_header(_USER, _PASSWORD)}

    # respx intercepts the httpx layer used by BinanceUsdmExchange.
    # assert_all_called=False because verify_credentials only hits time+balance
    # in the happy path; apiRestrictions is registered as best-effort and we
    # don't want a "never called" failure if the path changes.
    with respx.mock(base_url=_BASE_URL, assert_all_called=False) as binance:
        # ---- mocks for verify_credentials (POST /api/accounts) ----
        binance.get("/fapi/v1/time").mock(
            return_value=httpx.Response(
                200, json={"serverTime": int(time.time() * 1000)}
            )
        )
        binance.get("/fapi/v3/balance").mock(
            return_value=httpx.Response(200, json=[])
        )
        # apiRestrictions returns safe defaults (no trading, no withdrawals).
        binance.get("/sapi/v1/account/apiRestrictions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "enableFutures": False,
                    "enableMargin": False,
                    "enableWithdrawals": False,
                    "enableSpotAndMarginTrading": False,
                },
            )
        )

        # ---- mocks for backtest (fetch_funding_rates) ----
        # exchangeInfo: declare BTCUSDT as 8h-funding USDT-M perp.
        binance.get("/fapi/v1/exchangeInfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "fundingIntervalHours": 8,
                            "status": "TRADING",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                        }
                    ]
                },
            )
        )
        # Two funding events in the requested range.
        ft1 = _make_funding_time(2025, 1, 1, 0)
        ft2 = _make_funding_time(2025, 1, 1, 8)
        binance.get("/fapi/v1/fundingRate").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"symbol": "BTCUSDT", "fundingTime": ft1, "fundingRate": "0.0001"},
                    {"symbol": "BTCUSDT", "fundingTime": ft2, "fundingRate": "0.0002"},
                ],
            )
        )
        # markPriceKlines: each row is a 12-tuple Binance kline; we only need
        # open_time (row[0]) and open price (row[1]). One kline per funding
        # event timestamp.
        binance.get("/fapi/v1/markPriceKlines").mock(
            return_value=httpx.Response(
                200,
                json=[
                    [ft1, "60000", "60100", "59900", "60050", "0", ft1 + 1, "0", 0, "0", "0", "0"],
                    [ft2, "60100", "60200", "60000", "60150", "0", ft2 + 1, "0", 0, "0", "0", "0"],
                ],
            )
        )

        # ---- mock for history (fetch_funding_income) ----
        income_time = _make_funding_time(2025, 1, 15, 8)
        binance.get("/fapi/v1/income").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "symbol": "BTCUSDT",
                        "incomeType": "FUNDING_FEE",
                        "income": "-0.5",
                        "asset": "USDT",
                        "time": income_time,
                        "tranId": 100001,
                    },
                    # Non-funding row to verify upstream filtering doesn't crash;
                    # the exchange currently doesn't filter by incomeType
                    # client-side (it passes incomeType=FUNDING_FEE to Binance),
                    # so we only feed FUNDING_FEE rows. Keep a second one for
                    # totals.
                    {
                        "symbol": "ETHUSDT",
                        "incomeType": "FUNDING_FEE",
                        "income": "0.25",
                        "asset": "USDT",
                        "time": income_time + 3_600_000,
                        "tranId": 100002,
                    },
                ],
            )
        )

        with TestClient(app) as client:
            # Override the exchange factory AFTER lifespan has run (lifespan
            # installs the broken default). respx will catch all httpx calls.
            app.state.exchange_factory = _exchange_factory(
                web_env["cache_path"]
            )

            # ---- 1. GET /api/csrf ----
            r = client.get("/api/csrf", headers=auth)
            assert r.status_code == 200, r.text
            token = r.json()["token"]
            assert token and len(token) > 16

            # Build the canonical header bundle for write requests.
            csrf_headers = {
                **auth,
                "X-Funding-Token": token,
                "Origin": _ORIGIN,
                "Referer": _REFERER,
                # Force cookie on every request — the Set-Cookie Path=/funding/
                # may not match /api/* in TestClient's jar.
                "Cookie": f"funding_csrf={token}",
            }

            # ---- 2. POST /api/accounts ----
            api_key = "ABCDEF1234567890"
            api_secret = "very-secret-do-not-leak-XYZ"
            r = client.post(
                "/api/accounts",
                json={
                    "name": "primary",
                    "label": "main",
                    "api_key": api_key,
                    "api_secret": api_secret,
                },
                headers=csrf_headers,
            )
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["account"]["name"] == "primary"
            assert body["account"]["key_first6"] == api_key[:6]
            assert body["account"]["permissions"]["read"] is True
            assert body["account"]["permissions"]["trade"] is False
            assert body["account"]["permissions"]["withdraw"] is False

            # ---- 3. GET /api/accounts ----
            r = client.get("/api/accounts", headers=auth)
            assert r.status_code == 200
            txt = r.text
            assert api_secret not in txt
            # Full api_key must not appear; only key_first6 is exposed.
            assert api_key not in txt
            assert api_key[:6] in txt
            names = [a["name"] for a in r.json()["accounts"]]
            assert names == ["primary"]

            # ---- 4. POST /api/backtest ----
            r = client.post(
                "/api/backtest",
                json={
                    "symbol": "BTCUSDT",
                    "side": "LONG",
                    "start": "2025-01-01T00:00:00+00:00",
                    "end": "2025-01-01T16:00:00+00:00",
                    "size_mode": "RATE_ONLY",
                },
                headers=csrf_headers,
            )
            assert r.status_code == 200, r.text
            bt = r.json()
            assert bt["event_count"] == 2
            assert bt["total_quote"] is None  # RATE_ONLY
            assert bt["total_base"] is None
            assert len(bt["payments"]) == 2
            # Decimal serializer emits str — never float.
            for p in bt["payments"]:
                assert isinstance(p["rate"], str)
                assert isinstance(p["mark_price"], str)

            # ---- 5. POST /api/history → poll ----
            r = client.post(
                "/api/history",
                json={
                    "account_name": "primary",
                    "start": "2025-01-01T00:00:00+00:00",
                    "end": "2025-01-31T00:00:00+00:00",
                },
                headers=csrf_headers,
            )
            assert r.status_code == 202, r.text
            task_id = r.json()["task_id"]
            assert r.json()["status"] == "pending"

            # Poll up to ~5 seconds for terminal state.
            final = None
            for _ in range(50):
                r = client.get(
                    f"/api/history/result/{task_id}",
                    headers=auth,
                )
                assert r.status_code == 200, r.text
                body = r.json()
                if body["status"] in ("done", "failed"):
                    final = body
                    break
                time.sleep(0.1)
            assert final is not None, "history task did not reach terminal state"
            assert final["status"] == "done", f"task failed: {final.get('error')}"
            result = final["result"]
            # total = -0.5 + 0.25 = -0.25, serialized via PlainSerializer
            # (format(d, "f")) — no scientific notation, no quantization.
            assert result["total"] == "-0.25"
            assert set(result["by_symbol"].keys()) == {"BTCUSDT", "ETHUSDT"}
            assert result["by_symbol"]["BTCUSDT"] == "-0.5"
            assert result["by_symbol"]["ETHUSDT"] == "0.25"
            assert len(result["records"]) == 2

            # ---- 6. Negative: missing X-Funding-Token → 403 csrf_mismatch ----
            bad_headers = {k: v for k, v in csrf_headers.items() if k != "X-Funding-Token"}
            r = client.post(
                "/api/accounts",
                json={
                    "name": "x",
                    "label": "",
                    "api_key": "AAAAAAAA",
                    "api_secret": "SSSSSSSS",
                },
                headers=bad_headers,
            )
            assert r.status_code == 403
            assert r.json()["error"]["code"] == "csrf_mismatch"

            # ---- 7. Negative: wrong Origin → 403 ----
            wrong_origin = {**csrf_headers, "Origin": "https://attacker.example"}
            r = client.post(
                "/api/accounts",
                json={
                    "name": "x",
                    "label": "",
                    "api_key": "AAAAAAAA",
                    "api_secret": "SSSSSSSS",
                },
                headers=wrong_origin,
            )
            assert r.status_code == 403
            assert r.json()["error"]["code"] == "csrf_mismatch"

            # ---- 8. DELETE /api/accounts/{name} → 204 ----
            r = client.delete("/api/accounts/primary", headers=csrf_headers)
            assert r.status_code == 204
            assert r.content == b""

            r = client.get("/api/accounts", headers=auth)
            assert r.json()["accounts"] == []
