"""GET /api/csrf — issue token + Set-Cookie."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from funding_tool.web.csrf import CsrfGuard
from funding_tool.web.dependencies import get_csrf, require_auth

router = APIRouter()


@router.get("/csrf")
async def issue_csrf(
    response: Response,
    csrf: Annotated[CsrfGuard, Depends(get_csrf)],
    _user: str = Depends(require_auth),
) -> dict[str, str]:
    token = csrf.issue_token()
    # Build the Set-Cookie header manually so SameSite uses the canonical
    # title-case "Strict" form (Starlette emits lowercase "strict").
    response.headers["set-cookie"] = (
        f"{csrf.cookie_name}={token}; Max-Age=3600; Path=/funding/; "
        f"SameSite=Strict; Secure"
    )
    return {"token": token}
