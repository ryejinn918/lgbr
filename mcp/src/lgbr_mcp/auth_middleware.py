"""API key gate for /mcp/* (signed PDF GETs stay header-free)."""

from __future__ import annotations

import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from lgbr_mcp.config import mcp_api_key, require_mcp_api_key


class ApiKeyMiddleware:
    """Require Bearer / X-API-Key on /mcp/* unless local ALLOW_INSECURE."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if not path.startswith("/mcp/"):
            await self.app(scope, receive, send)
            return

        if not require_mcp_api_key():
            await self.app(scope, receive, send)
            return

        expected = mcp_api_key()
        if expected is None:
            response = JSONResponse(
                {"ok": False, "message": "Unauthorized"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        provided = _extract_key(request)
        if provided and hmac.compare_digest(provided, expected):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            {"ok": False, "message": "Unauthorized"},
            status_code=401,
        )
        await response(scope, receive, send)


# Back-compat alias
OptionalApiKeyMiddleware = ApiKeyMiddleware


def _extract_key(request: Request) -> str | None:
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None
