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
    list_crawl_events,
    request_stop,
    shutdown_open_crawl,
    start_crawl,
)
from lgbr_api.db import load_database_env
from lgbr_api.profiles import list_profiles, update_profile
from lgbr_api.reports import get_report_file, list_reports
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


async def crawl(request: Request) -> JSONResponse:
    try:
        event_limit = int(request.query_params.get("events", "50"))
    except ValueError:
        event_limit = 50
    return JSONResponse(get_current_crawl(event_limit=event_limit))


async def crawl_events(request: Request) -> JSONResponse:
    crawl_id = request.query_params.get("crawl_id")
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        limit = 50
    return JSONResponse(list_crawl_events(crawl_id, limit=limit))


async def crawl_start(request: Request) -> JSONResponse:
    mode = "datacenter"
    limit: int | None = None
    debug = False
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
        if "debug" in body:
            debug = bool(body.get("debug"))
    result = start_crawl(mode=mode, limit=limit, debug=debug)
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def crawl_stop(_: Request) -> JSONResponse:
    return JSONResponse(request_stop())


async def cdp_status(_: Request) -> JSONResponse:
    result = get_cdp_status()
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def reports(request: Request) -> JSONResponse:
    try:
        limit = int(request.query_params.get("limit", "30"))
    except ValueError:
        limit = 30
    try:
        offset = int(request.query_params.get("offset", "0"))
    except ValueError:
        offset = 0
    result = list_reports(
        status=request.query_params.get("status"),
        quality=request.query_params.get("quality"),
        q=request.query_params.get("q"),
        crawl_id=request.query_params.get("crawl_id"),
        sort=request.query_params.get("sort"),
        limit=limit,
        offset=offset,
    )
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def report_file(request: Request):
    return get_report_file(str(request.path_params.get("report_id") or ""))


async def crawl_profiles(_: Request) -> JSONResponse:
    result = list_profiles()
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def crawl_profile_patch(request: Request) -> JSONResponse:
    mode = request.path_params.get("mode") or ""
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    result = update_profile(str(mode), body)
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
            Route("/api/crawl/events", crawl_events),
            Route("/api/crawl/start", crawl_start, methods=["POST"]),
            Route("/api/crawl/stop", crawl_stop, methods=["POST"]),
            Route("/api/crawl/profiles", crawl_profiles),
            Route(
                "/api/crawl/profiles/{mode}",
                crawl_profile_patch,
                methods=["PATCH"],
            ),
            Route("/api/cdp", cdp_status),
            Route("/api/reports", reports),
            Route("/api/reports/{report_id}/file", report_file),
        ],
        middleware=[Middleware(ApiKeyMiddleware)],
        lifespan=lifespan,
    )


app = create_app()
