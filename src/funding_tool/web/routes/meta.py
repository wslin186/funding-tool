"""GET /api/health (anonymous) and GET /api/symbols (auth-only, cached 1h)."""
from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from funding_tool.web.dependencies import get_exchange_factory, require_auth

router = APIRouter()

_CACHE_TTL = 3600.0
_cache: dict[str, tuple[float, list[str]]] = {}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/symbols")
async def symbols(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=20)] = "",
    _user: str = Depends(require_auth),
) -> dict[str, list[str]]:
    now = time.monotonic()
    cached = _cache.get("all")
    if cached and now - cached[0] < _CACHE_TTL:
        all_symbols = cached[1]
    else:
        factory = get_exchange_factory(request)
        ex = factory()
        all_symbols = await ex.fetch_symbols()
        _cache["all"] = (now, all_symbols)
    q_upper = q.upper()
    return {"symbols": [s for s in all_symbols if q_upper in s][:50]}
