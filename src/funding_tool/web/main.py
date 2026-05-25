"""FastAPI app + lifespan: load master key, init SecretStore, mount routes."""
from __future__ import annotations

import hashlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from funding_tool.web.audit import AuditLogger
from funding_tool.web.auth import AuthVerifier
from funding_tool.web.config import Settings, load_settings
from funding_tool.web.csrf import CsrfGuard
from funding_tool.web.errors import WebError, map_core_exception
from funding_tool.web.secret_store import SecretStore

logger = logging.getLogger("funding_tool.web")


def _load_master_key_from_credentials() -> tuple[bytes, bytes | None]:
    cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not cred_dir:
        raise RuntimeError("CREDENTIALS_DIRECTORY env not set (systemd LoadCredential)")
    active_p = Path(cred_dir) / "master_key"
    if not active_p.exists():
        raise RuntimeError(f"master key missing at {active_p}")
    active = active_p.read_bytes()
    if len(active) != 32:
        raise RuntimeError(f"master key must be 32 bytes, got {len(active)}")
    prev_p = Path(cred_dir) / "master_key_prev"
    prev = prev_p.read_bytes() if prev_p.exists() else None
    if prev is not None and len(prev) != 32:
        raise RuntimeError(f"prev master key must be 32 bytes, got {len(prev)}")
    return active, prev


def _exchange_factory_default(creds: object = None) -> object:
    from funding_tool.core.exchanges.binance_usdm import BinanceUsdmExchange
    return BinanceUsdmExchange(credentials=creds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    active, prev = _load_master_key_from_credentials()
    fp = hashlib.sha256(active).hexdigest()[:8]
    logger.info("master_key_loaded fingerprint=%s prev=%s", fp, "yes" if prev else "no")

    store = SecretStore(settings.db_path, master_key=active, prev_key=prev)
    await store.init_schema()
    await store.verify_canary()
    audit = AuditLogger(settings.audit_log_path)
    auth = AuthVerifier(username=settings.auth_user, password_hash=settings.auth_password_hash)
    csrf = CsrfGuard(public_origin=settings.public_origin)

    app.state.settings = settings
    app.state.secret_store = store
    app.state.audit = audit
    app.state.auth = auth
    app.state.csrf = csrf
    app.state.exchange_factory = _exchange_factory_default
    try:
        settings.tasks_dir.mkdir(parents=True, exist_ok=True)
        yield
    finally:
        audit.close()


def create_app() -> FastAPI:
    app = FastAPI(title="funding-tool web", lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None)

    try:
        from funding_tool.web.routes import meta, csrf as csrf_route, accounts, backtest, history
        app.include_router(meta.router, prefix="/api")
        app.include_router(csrf_route.router, prefix="/api")
        app.include_router(accounts.router, prefix="/api")
        app.include_router(backtest.router, prefix="/api")
        app.include_router(history.router, prefix="/api")
    except ImportError:
        pass

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        web_err = map_core_exception(exc)
        logger.exception("unhandled error_id=%s code=%s", web_err.error_id, web_err.code)
        return JSONResponse(
            status_code=web_err.http_status,
            content={"error": {
                "code": web_err.code, "message": web_err.message,
                "field": web_err.field, "error_id": web_err.error_id,
            }},
        )

    return app


app = create_app()


def run() -> None:
    import uvicorn
    s = load_settings()
    uvicorn.run("funding_tool.web.main:app", host=s.bind_host, port=s.bind_port, workers=1)
