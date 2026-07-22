"""Local status API for the Fnguide search monitor."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from lgbr_api.auth import ApiKeyMiddleware
from lgbr_api.crawls import (
    get_cdp_status,
    get_current_crawl,
    request_stop,
    shutdown_open_crawl,
    start_crawl,
)
from lgbr_api.db import load_database_env
from lgbr_api.sessions import get_current_session, list_history

SHUTDOWN_WAIT_SECONDS = 60.0


@asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    yield
    # PM2/uvicorn stop: ask crawl worker to logout before this process exits.
    await asyncio.to_thread(
        shutdown_open_crawl, timeout_seconds=SHUTDOWN_WAIT_SECONDS
    )


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def session(_: Request) -> JSONResponse:
    return JSONResponse(get_current_session())


async def session_logout(_: Request) -> JSONResponse:
    # Logout ends the crawl parent as well (session is a subtask).
    return JSONResponse(request_stop())


async def session_history(request: Request) -> JSONResponse:
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        limit = 50
    return JSONResponse({"items": list_history(limit=limit)})


async def crawl(_: Request) -> JSONResponse:
    return JSONResponse(get_current_crawl())


async def crawl_start(request: Request) -> JSONResponse:
    mode = "datacenter"
    limit: int | None = None
    try:
        body = await request.json()
    except Exception:
        body = {}
    if isinstance(body, dict):
        if body.get("mode"):
            mode = str(body["mode"])
        if "limit" in body and body.get("limit") is not None:
            try:
                limit = int(body["limit"])
            except (TypeError, ValueError):
                return JSONResponse(
                    {
                        "ok": False,
                        "label": "오류",
                        "message": "limit must be an integer",
                        "crawl": None,
                        "can_start": False,
                    },
                    status_code=400,
                )
    result = start_crawl(mode=mode, limit=limit)
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def crawl_stop(_: Request) -> JSONResponse:
    return JSONResponse(request_stop())


async def cdp_status(_: Request) -> JSONResponse:
    result = get_cdp_status()
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


def create_app() -> Starlette:
    load_database_env()
    return Starlette(
        routes=[
            Route("/api/health", health),
            Route("/api/session", session),
            Route("/api/session/logout", session_logout, methods=["POST"]),
            Route("/api/session/history", session_history),
            Route("/api/crawl", crawl),
            Route("/api/crawl/start", crawl_start, methods=["POST"]),
            Route("/api/crawl/stop", crawl_stop, methods=["POST"]),
            Route("/api/cdp", cdp_status),
        ],
        middleware=[Middleware(ApiKeyMiddleware)],
        lifespan=lifespan,
    )


app = create_app()
