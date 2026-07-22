"""Optional shared API key for external exposure."""

from __future__ import annotations

import hmac
import os
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def configured_api_key() -> str | None:
    key = os.environ.get("LGBR_API_KEY", "").strip()
    return key or None


def extract_api_key(request: Request) -> str | None:
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def key_matches(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


class ApiKeyMiddleware:
    """Require X-API-Key / Bearer when LGBR_API_KEY is set.

    /api/health stays open for probes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        expected = configured_api_key()
        if expected is None or path == "/api/health":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        if key_matches(extract_api_key(request), expected):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            {"ok": False, "message": "Unauthorized"},
            status_code=401,
        )
        await response(scope, receive, send)
