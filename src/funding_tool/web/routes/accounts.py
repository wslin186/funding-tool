"""Account CRUD: GET/POST /api/accounts, DELETE /api/accounts/{name}.

verify_credentials runs BEFORE persistence so a bad key never lands in the
encrypted store. Successful permission report is written back via
update_permissions so the list endpoint can surface it without re-calling
the exchange.
"""
from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from funding_tool.core.errors import NetworkError
from funding_tool.core.models import ApiCredentials
from funding_tool.web.dependencies import (
    get_exchange_factory,
    get_secret_store,
    require_auth,
    require_csrf,
)
from funding_tool.web.models import (
    AccountCreateRequest,
    AccountCreateResponse,
    AccountOut,
    AccountPermissions,
    map_permission_report,
)
from funding_tool.web.secret_store import AccountRecord, SecretStore

router = APIRouter()

_VERIFY_TIMEOUT_SEC = 10.0


def _record_to_out(rec: AccountRecord) -> AccountOut:
    return AccountOut(
        name=rec.name,
        label=rec.label,
        created_at=rec.created_at,
        key_first6=rec.key_first6,
        permissions=AccountPermissions(
            read=rec.perm_read,
            trade=rec.perm_trade,
            withdraw=rec.perm_withdraw,
        ),
    )


@router.get("/accounts")
async def list_accounts(
    request: Request,
    _user: str = Depends(require_auth),
) -> dict[str, list[AccountOut]]:
    store: SecretStore = get_secret_store(request)
    records = await store.list_accounts()
    return {"accounts": [_record_to_out(r) for r in records]}


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(
    request: Request,
    payload: AccountCreateRequest,
    _user: str = Depends(require_auth),
    _csrf: None = Depends(require_csrf),
) -> AccountCreateResponse:
    store: SecretStore = get_secret_store(request)
    factory = get_exchange_factory(request)

    creds = ApiCredentials(api_key=payload.api_key, api_secret=payload.api_secret)

    # 1) verify BEFORE persist — bad keys never reach the encrypted store.
    ex = factory(creds)
    try:
        report = await asyncio.wait_for(
            ex.verify_credentials(creds), timeout=_VERIFY_TIMEOUT_SEC
        )
    except asyncio.TimeoutError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "network_error", "message": "网络异常"},
        ) from e
    except NetworkError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "network_error", "message": "网络异常"},
        ) from e

    perms = map_permission_report(report)

    # 2) persist
    try:
        await store.add_account(payload.name, payload.label, creds)
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "validation_error", "message": "账户名已存在", "field": "account_name"},
        ) from e

    # 3) write permissions back
    await store.update_permissions(
        payload.name,
        read=perms.read,
        trade=perms.trade,
        withdraw=perms.withdraw,
    )

    # 4) build response from in-memory data (avoid extra DB round-trip).
    records = await store.list_accounts()
    rec = next((r for r in records if r.name == payload.name), None)
    if rec is None:
        # Shouldn't happen — we just inserted.
        raise HTTPException(
            status_code=500,
            detail={"code": "server_error", "message": "账户创建后无法读取"},
        )
    return AccountCreateResponse(account=_record_to_out(rec))


@router.delete("/accounts/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    request: Request,
    name: str,
    _user: str = Depends(require_auth),
    _csrf: None = Depends(require_csrf),
) -> Response:
    store: SecretStore = get_secret_store(request)
    try:
        await store.delete_account(name)
    except KeyError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "validation_error", "message": "账户不存在", "field": "account_name"},
        ) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
