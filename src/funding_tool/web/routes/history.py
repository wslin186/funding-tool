"""POST /api/history (async submit) + GET /api/history/result/{id} (poll).

The history endpoint can run for tens of seconds against Binance's funding
income API, so it is dispatched to the in-process TaskManager instead of
blocking the request. The submit endpoint returns 202 with a task_id; the
client polls /api/history/result/{task_id} until status is terminal.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from funding_tool.core.account import run_account_history
from funding_tool.web.dependencies import (
    get_exchange_factory,
    get_secret_store,
    require_auth,
    require_csrf,
)
from funding_tool.web.models import (
    HistoryPayload,
    HistoryRequest,
    HistorySubmitResponse,
    HistoryTaskStatus,
    to_history_payload,
)
from funding_tool.web.secret_store import SecretStore
from funding_tool.web.tasks import TaskManager

router = APIRouter()

_MAX_RANGE_DAYS = 1095


def _task_manager(request: Request) -> TaskManager:
    """Lazy-init the TaskManager on app.state on first use.

    Lifespan sets up tasks_dir but does not eagerly create the manager —
    we wait until a request actually needs it so unit tests that never
    submit a history job don't pay any setup cost.
    """
    tm = getattr(request.app.state, "task_manager", None)
    if tm is None:
        tm = TaskManager(request.app.state.settings.tasks_dir)
        request.app.state.task_manager = tm
    return tm


@router.post("/history", status_code=202)
async def submit_history(
    request: Request,
    body: HistoryRequest,
    store: SecretStore = Depends(get_secret_store),
    _user: str = Depends(require_auth),
    _csrf: None = Depends(require_csrf),
) -> HistorySubmitResponse:
    if (body.end - body.start) > timedelta(days=_MAX_RANGE_DAYS):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "range_too_large",
                "message": f"查询时间范围超过 {_MAX_RANGE_DAYS} 天上限",
            },
        )

    try:
        creds = await store.get_credentials(body.account_name)
    except KeyError as e:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "validation_error",
                "message": "账户不存在",
                "field": "account_name",
            },
        ) from e

    factory = get_exchange_factory(request)
    ex = factory(creds=creds)
    tm = _task_manager(request)

    async def _job() -> dict[str, Any]:
        result = await run_account_history(
            creds=creds,
            exchange=ex,
            start=body.start,
            end=body.end,
            symbol=body.symbol,
        )
        # mode="json" so Decimals are emitted as strings — matches
        # HistoryPayload's PlainSerializer and keeps the persisted JSON
        # consistent with the API response shape.
        return to_history_payload(result).model_dump(mode="json")

    task_id = tm.submit(_job)
    return HistorySubmitResponse(task_id=task_id, status="pending")


@router.get("/history/result/{task_id}")
async def history_result(
    task_id: str,
    request: Request,
    _user: str = Depends(require_auth),
) -> HistoryTaskStatus:
    tm = _task_manager(request)
    try:
        st = await tm.status(task_id)
    except KeyError as e:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "validation_error",
                "message": "任务不存在或已过期",
            },
        ) from e
    return HistoryTaskStatus(
        status=st["status"],
        progress=st.get("progress"),
        result=HistoryPayload.model_validate(st["result"]) if st.get("result") else None,
        error=st.get("error"),
    )
