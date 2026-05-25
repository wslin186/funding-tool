"""Dependency injection: settings, secret_store, exchange, auth, csrf."""
from __future__ import annotations

from typing import Annotated, Callable

from fastapi import Depends, HTTPException, Request

from funding_tool.web.auth import AuthError, AuthVerifier, extract_client_ip
from funding_tool.web.config import Settings
from funding_tool.web.csrf import CsrfError, CsrfGuard
from funding_tool.web.secret_store import SecretStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_secret_store(request: Request) -> SecretStore:
    return request.app.state.secret_store


def get_auth(request: Request) -> AuthVerifier:
    return request.app.state.auth


def get_csrf(request: Request) -> CsrfGuard:
    return request.app.state.csrf


def get_exchange_factory(request: Request) -> Callable[..., object]:
    return request.app.state.exchange_factory


def require_auth(
    request: Request,
    auth: Annotated[AuthVerifier, Depends(get_auth)],
) -> str:
    ip = extract_client_ip(request)
    try:
        return auth.verify(ip=ip, header=request.headers.get("Authorization"))
    except AuthError as e:
        headers = {"WWW-Authenticate": 'Basic realm="funding-tool"'} if e.code == "web_auth_required" else {}
        status = 401 if e.code == "web_auth_required" else 429
        raise HTTPException(
            status_code=status,
            detail={"code": e.code, "message": "请先登录" if status == 401 else "登录次数过多，5 分钟后重试"},
            headers=headers,
        )


def require_csrf(
    request: Request,
    csrf: Annotated[CsrfGuard, Depends(get_csrf)],
) -> None:
    try:
        csrf.verify(
            cookie_token=request.cookies.get(csrf.cookie_name),
            header_token=request.headers.get(csrf.header_name),
            origin=request.headers.get("Origin"),
            referer=request.headers.get("Referer"),
        )
    except CsrfError as e:
        raise HTTPException(status_code=403, detail={"code": "csrf_mismatch", "message": "安全令牌失效，请刷新页面"}) from e
