"""Combined ASGI: /mcp/collect, /mcp/consensus, signed PDF, health."""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from lgbr_mcp.auth_middleware import ApiKeyMiddleware
from lgbr_mcp.collect import build_collect_server, transport_security_settings
from lgbr_mcp.config import load_env, validate_startup
from lgbr_mcp.consensus import build_consensus_server
from lgbr_mcp.files import serve_report_pdf

# Mount() only matches /mcp/collect/…; without a trailing slash Starlette
# issues HTTP 307 which some MCP clients mishandle (Auth header). Rewrite
# in-process instead of redirecting.
_MCP_MOUNT_ROOTS = ("/mcp/collect", "/mcp/consensus")


class _McpTrailingSlashMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path") or ""
            if path in _MCP_MOUNT_ROOTS:
                scope = dict(scope)
                scope["path"] = path + "/"
                raw = scope.get("raw_path")
                if isinstance(raw, (bytes, bytearray)):
                    scope["raw_path"] = raw + b"/"
        await self.app(scope, receive, send)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "lgbr-mcp"})


def create_app() -> Starlette:
    load_env()
    validate_startup()
    security = transport_security_settings()

    collect_mcp = build_collect_server()
    consensus_mcp = build_consensus_server()

    collect_http = collect_mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        transport_security=security,
        host="0.0.0.0",
    )
    consensus_http = consensus_mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        transport_security=security,
        host="0.0.0.0",
    )

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(
                collect_http.router.lifespan_context(collect_http)
            )
            await stack.enter_async_context(
                consensus_http.router.lifespan_context(consensus_http)
            )
            yield

    return Starlette(
        routes=[
            Route("/health", health),
            Route(
                "/files/reports/{report_id}",
                serve_report_pdf,
                methods=["GET"],
            ),
            Mount("/mcp/collect", app=collect_http),
            Mount("/mcp/consensus", app=consensus_http),
        ],
        middleware=[
            Middleware(_McpTrailingSlashMiddleware),
            Middleware(ApiKeyMiddleware),
        ],
        lifespan=lifespan,
    )


app = create_app()
