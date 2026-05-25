"""POST /api/backtest — synchronous wrapper around core.run_backtest."""
from __future__ import annotations

import asyncio
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

from funding_tool.core.backtest import run_backtest
from funding_tool.core.models import BacktestInput
from funding_tool.web.dependencies import (
    get_exchange_factory,
    require_auth,
    require_csrf,
)
from funding_tool.web.models import (
    BacktestRequest,
    BacktestResponse,
    to_backtest_response,
)

router = APIRouter()

_MAX_RANGE_DAYS = 730
_BACKTEST_TIMEOUT_S = 120.0


@router.post("/backtest")
async def backtest(
    request: Request,
    body: BacktestRequest,
    _user: str = Depends(require_auth),
    _csrf: None = Depends(require_csrf),
) -> BacktestResponse:
    if (body.end - body.start) > timedelta(days=_MAX_RANGE_DAYS):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "range_too_large",
                "message": f"查询时间范围超过 {_MAX_RANGE_DAYS} 天上限",
            },
        )
    inp = BacktestInput(
        symbol=body.symbol,
        side=body.side,
        start=body.start,
        end=body.end,
        size_mode=body.size_mode,
        size=body.size,
    )
    factory = get_exchange_factory(request)
    ex = factory()
    try:
        result = await asyncio.wait_for(
            run_backtest(inp, exchange=ex), timeout=_BACKTEST_TIMEOUT_S
        )
    except asyncio.TimeoutError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "network_error", "message": "查询超时"},
        ) from e
    return to_backtest_response(result)
