"""Shared FastAPI test app builder. Stubs out master key load + exchange."""
import asyncio
import base64
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import bcrypt
import pytest
from fastapi import FastAPI

from funding_tool.core.exchanges.base import ExchangeProtocol
from funding_tool.core.models import (
    BacktestResult, FundingEvent, FundingPayment, HistoryResult,
    IncomeRecord, PermissionReport,
)
from funding_tool.web.audit import AuditLogger
from funding_tool.web.auth import AuthVerifier
from funding_tool.web.config import Settings
from funding_tool.web.csrf import CsrfGuard
from funding_tool.web.main import create_app
from funding_tool.web.secret_store import SecretStore

_PASSWORD = "s3cret"
_USER = "admin"

# ---------------------------------------------------------------------------
# Call-count tracking for list_symbols (used by test_symbols_cached)
# ---------------------------------------------------------------------------
_list_symbols_call_count = 0


def get_list_symbols_call_count() -> int:
    return _list_symbols_call_count


def reset_list_symbols_call_count() -> None:
    global _list_symbols_call_count
    _list_symbols_call_count = 0


# ---------------------------------------------------------------------------
# Safe asyncio bridge: runs a coroutine in a fresh thread so it is safe to
# call from both sync code AND from inside an already-running event loop
# (e.g. pytest-asyncio's auto-mode).
# ---------------------------------------------------------------------------

def _run_sync(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine from sync code, safe even when an event loop
    is already running on the calling thread."""
    result_holder: dict[str, object] = {}
    exc_holder: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result_holder["value"] = asyncio.run(coro)
        except BaseException as exc:
            exc_holder["exc"] = exc

    t = threading.Thread(target=_runner)
    t.start()
    t.join()
    if "exc" in exc_holder:
        raise exc_holder["exc"]
    return result_holder.get("value")


def build_app_for_test(*, tmp_path: Path | None = None) -> FastAPI:
    base = tmp_path or Path("/tmp/funding_test")
    base.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        public_origin="https://example.com",
        auth_user=_USER,
        auth_password_hash=bcrypt.hashpw(_PASSWORD.encode(), bcrypt.gensalt(rounds=4)),
        db_path=base / f"sec_{os.urandom(4).hex()}.sqlite",
        audit_log_path=base / "audit.jsonl",
        tasks_dir=base / "tasks",
    )
    app = create_app()
    app.router.lifespan_context = _noop_lifespan  # type: ignore[attr-defined]

    # Wire app state eagerly (synchronous path) so TestClient works without
    # context-manager entry (no lifespan startup event is sent in that mode).
    async def _init_store() -> SecretStore:
        store = SecretStore(settings.db_path, master_key=os.urandom(32))
        await store.init_schema()
        return store

    # Use _run_sync instead of asyncio.run() so this is safe even when called
    # from inside an already-running event loop (e.g. pytest-asyncio auto mode).
    store = _run_sync(_init_store())
    app.state.settings = settings
    app.state.secret_store = store
    app.state.audit = AuditLogger(settings.audit_log_path)
    app.state.auth = AuthVerifier(username=_USER, password_hash=settings.auth_password_hash)
    app.state.csrf = CsrfGuard(public_origin=settings.public_origin)
    app.state.exchange_factory = _make_fake_exchange_factory()
    settings.tasks_dir.mkdir(parents=True, exist_ok=True)

    @app.on_event("startup")
    async def _wire() -> None:
        # Re-wire when TestClient is used as context manager (lifespan fires).
        # For bare TestClient(app).get(...) usage, state is already set above.
        store2 = SecretStore(settings.db_path, master_key=os.urandom(32))
        await store2.init_schema()
        app.state.settings = settings
        app.state.secret_store = store2
        app.state.audit = AuditLogger(settings.audit_log_path)
        app.state.auth = AuthVerifier(username=_USER, password_hash=settings.auth_password_hash)
        app.state.csrf = CsrfGuard(public_origin=settings.public_origin)
        app.state.exchange_factory = _make_fake_exchange_factory()
        settings.tasks_dir.mkdir(parents=True, exist_ok=True)

    return app


def _noop_lifespan(app):  # type: ignore[no-untyped-def]
    """Replace the real lifespan (loads credentials from disk) with a noop.
    Startup events registered via on_event() are called manually here so that
    context-manager-based TestClient usage also works."""
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def _ls(app):  # type: ignore[no-untyped-def]
        await app.router._startup()
        try:
            yield
        finally:
            await app.router._shutdown()
    return _ls(app)


def _make_fake_exchange_factory():
    def _factory(creds=None):
        # spec=ExchangeProtocol ensures only real protocol methods are accessible;
        # attribute typos (e.g. ex.fetch_symbls) raise AttributeError immediately.
        ex = MagicMock(spec=ExchangeProtocol)

        async def list_symbols() -> list[str]:
            global _list_symbols_call_count
            _list_symbols_call_count += 1
            return ["BTCUSDT", "ETHUSDT", "BTCBUSD"]

        async def fetch_funding_rates(symbol, start, end):
            return [FundingEvent(
                timestamp=datetime(2025, 1, 1, 8, tzinfo=timezone.utc),
                symbol=symbol, rate=Decimal("0.0001"),
                mark_price=Decimal("60000"), interval_hours=8,
            )]

        async def verify_credentials(credentials):
            return PermissionReport(read_ok=True, trading_enabled=False,
                                    withdrawals_enabled=False, spot_trading_enabled=None)

        async def fetch_funding_income(credentials, start, end, symbol=None):
            return [IncomeRecord(
                timestamp=datetime(2025, 1, 15, tzinfo=timezone.utc),
                symbol="BTCUSDT", amount_usdt=Decimal("10"), tran_id="t1",
            )]

        ex.list_symbols = list_symbols
        ex.fetch_funding_rates = fetch_funding_rates
        ex.verify_credentials = verify_credentials
        ex.fetch_funding_income = fetch_funding_income
        return ex
    return _factory


@pytest.fixture
def basic_auth_headers() -> dict[str, str]:
    raw = f"{_USER}:{_PASSWORD}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}
