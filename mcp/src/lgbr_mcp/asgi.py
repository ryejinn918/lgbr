"""Combined ASGI: OAuth AS, /mcp/collect, /mcp/consensus, health."""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

from mcp.server.auth.provider import ProviderTokenVerifier
from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from lgbr_mcp.branding import FAVICON_ICO_PATH, FAVICON_PATH, FAVICON_PNG_PATH
from lgbr_mcp.collect import build_collect_server, transport_security_settings
from lgbr_mcp.config import (
    load_env,
    oauth_password,
    oauth_username,
    public_base_url,
    validate_startup,
)
from lgbr_mcp.consensus import build_consensus_server
from lgbr_mcp.oauth_provider import MCP_SCOPE, SimpleOAuthProvider

# Mount() only matches /mcp/collect/…; without a trailing slash Starlette
# issues HTTP 307 which some MCP clients mishandle. Rewrite in-process.
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


async def root_page(_: Request) -> HTMLResponse:
    """Crawlable landing so favicon services can discover icons."""
    return HTMLResponse(
        """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<title>LGBR MCP — MagpieLabs</title>
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.png" type="image/png" sizes="64x64">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/favicon.png">
</head><body>
<h1>LGBR MCP</h1>
<p>MagpieLabs connectors: <code>/mcp/collect</code>, <code>/mcp/consensus</code></p>
</body></html>"""
    )


async def favicon_svg(_: Request) -> FileResponse:
    return FileResponse(FAVICON_PATH, media_type="image/svg+xml")


async def favicon_png(_: Request) -> FileResponse:
    return FileResponse(FAVICON_PNG_PATH, media_type="image/png")


async def favicon_ico(_: Request) -> FileResponse:
    return FileResponse(FAVICON_ICO_PATH, media_type="image/x-icon")


def _client_registration() -> ClientRegistrationOptions:
    return ClientRegistrationOptions(
        enabled=True,
        valid_scopes=[MCP_SCOPE],
        default_scopes=[MCP_SCOPE],
    )


def _resource_auth(issuer: AnyHttpUrl, resource_url: str) -> AuthSettings:
    return AuthSettings(
        issuer_url=issuer,
        resource_server_url=AnyHttpUrl(resource_url),
        required_scopes=[MCP_SCOPE],
        client_registration_options=_client_registration(),
    )


def create_app() -> Starlette:
    load_env()
    validate_startup()
    security = transport_security_settings()
    base = public_base_url()
    issuer = AnyHttpUrl(base)

    oauth_provider = SimpleOAuthProvider(
        username=oauth_username(),
        password=oauth_password(),
        login_url=f"{base}/login",
        scope=MCP_SCOPE,
    )
    token_verifier = ProviderTokenVerifier(oauth_provider)
    collect_auth = _resource_auth(issuer, f"{base}/mcp/collect")
    consensus_auth = _resource_auth(issuer, f"{base}/mcp/consensus")

    async def login_get(request: Request) -> HTMLResponse:
        return await oauth_provider.get_login_page(
            request.query_params.get("state") or ""
        )

    auth_routes: list[Route] = [
        *create_auth_routes(
            provider=oauth_provider,
            issuer_url=issuer,
            client_registration_options=_client_registration(),
        ),
        *create_protected_resource_routes(
            resource_url=AnyHttpUrl(f"{base}/mcp/collect"),
            authorization_servers=[issuer],
            scopes_supported=[MCP_SCOPE],
            resource_name="LGBR Collect",
        ),
        *create_protected_resource_routes(
            resource_url=AnyHttpUrl(f"{base}/mcp/consensus"),
            authorization_servers=[issuer],
            scopes_supported=[MCP_SCOPE],
            resource_name="LGBR Consensus",
        ),
        Route("/login", login_get, methods=["GET"]),
        Route("/login", oauth_provider.handle_login_callback, methods=["POST"]),
    ]

    collect_http = build_collect_server(
        auth=collect_auth, token_verifier=token_verifier
    ).streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        transport_security=security,
        host="0.0.0.0",
    )
    consensus_http = build_consensus_server(
        auth=consensus_auth, token_verifier=token_verifier
    ).streamable_http_app(
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
            Route("/", root_page),
            Route("/health", health),
            Route("/favicon.svg", favicon_svg),
            Route("/favicon.png", favicon_png),
            Route("/favicon.ico", favicon_ico),
            *auth_routes,
            Mount("/mcp/collect", app=collect_http),
            Mount("/mcp/consensus", app=consensus_http),
        ],
        middleware=[Middleware(_McpTrailingSlashMiddleware)],
        lifespan=lifespan,
    )


app = create_app()
