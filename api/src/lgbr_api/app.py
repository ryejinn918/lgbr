"""Local status API for the Fnguide search monitor."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import AsyncIterator

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from lgbr_api.auth import ApiKeyMiddleware
from lgbr_api.consensus_api import (
    compare_chat,
    get_current_run,
    get_latest_ended,
    get_outputs,
    get_run_docs,
    list_events as list_consensus_events,
    list_history as list_consensus_history,
    list_inputs,
    request_stop as consensus_request_stop,
    start_run,
)
from lgbr_api.consensus_chat import iter_compare_chat_sse
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
from lgbr_api.audits import get_audit_status, start_audit
from lgbr_api.reports import get_report, get_report_file, list_reports
from lgbr_api.sessions import get_current_session, list_history
from lgbr_api.timeline import list_session_timeline, list_timeline

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
    try:
        offset = int(request.query_params.get("offset", "0"))
    except ValueError:
        offset = 0
    return JSONResponse(list_history(limit=limit, offset=offset))


async def timeline(request: Request) -> JSONResponse:
    try:
        limit = int(request.query_params.get("limit", "10"))
    except ValueError:
        limit = 10
    try:
        offset = int(request.query_params.get("offset", "0"))
    except ValueError:
        offset = 0
    return JSONResponse(list_timeline(limit=limit, offset=offset))


async def timeline_session(request: Request) -> JSONResponse:
    session_id = str(request.path_params.get("session_id") or "")
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        limit = 50
    try:
        offset = int(request.query_params.get("offset", "0"))
    except ValueError:
        offset = 0
    result = list_session_timeline(
        session_id, limit=limit, offset=offset
    )
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


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
        theme=request.query_params.get("theme"),
        q=request.query_params.get("q"),
        crawl_id=request.query_params.get("crawl_id"),
        sort=request.query_params.get("sort"),
        limit=limit,
        offset=offset,
    )
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def report_detail(request: Request) -> JSONResponse:
    result = get_report(str(request.path_params.get("report_id") or ""))
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def report_file(request: Request):
    return get_report_file(str(request.path_params.get("report_id") or ""))


async def audit_status(_: Request) -> JSONResponse:
    return JSONResponse(get_audit_status())


async def audit_start(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    result = start_audit(
        limit=body.get("limit"),
        force=bool(body.get("force")),
        theme=str(body["theme"]) if body.get("theme") is not None else None,
        concurrency=body.get("concurrency"),
        report_id=(
            str(body["report_id"]) if body.get("report_id") is not None else None
        ),
    )
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


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


async def consensus_status(request: Request) -> JSONResponse:
    try:
        event_limit = int(request.query_params.get("events", "50"))
    except ValueError:
        event_limit = 50
    run_id = request.query_params.get("run_id")
    return JSONResponse(
        get_current_run(run_id=run_id, event_limit=event_limit)
    )


async def consensus_history(request: Request) -> JSONResponse:
    try:
        limit = int(request.query_params.get("limit", "30"))
    except ValueError:
        limit = 30
    theme = request.query_params.get("theme")
    result = list_consensus_history(
        limit=limit, theme=str(theme) if theme else None
    )
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_latest(request: Request) -> JSONResponse:
    theme = request.query_params.get("theme") or "datacenter"
    result = get_latest_ended(theme=str(theme))
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_events(request: Request) -> JSONResponse:
    run_id = request.query_params.get("run_id")
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        limit = 50
    return JSONResponse(list_consensus_events(run_id, limit=limit))


async def consensus_start(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    theme = str(body.get("theme") or "datacenter")
    question = body.get("question")
    result = start_run(
        theme=theme,
        question=str(question) if question is not None else None,
    )
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_stop(_: Request) -> JSONResponse:
    return JSONResponse(consensus_request_stop())


async def consensus_inputs(request: Request) -> JSONResponse:
    theme = request.query_params.get("theme") or "datacenter"
    result = list_inputs(theme=str(theme))
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_outputs(request: Request) -> JSONResponse:
    run_id = str(request.path_params.get("run_id") or "")
    result = get_outputs(run_id)
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_docs(request: Request) -> JSONResponse:
    run_id = str(request.path_params.get("run_id") or "")
    return JSONResponse(get_run_docs(run_id))


async def consensus_chat(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    messages = body.get("messages")
    if not isinstance(messages, list):
        messages = []
    result = compare_chat(
        mode=str(body.get("mode") or "plain"),
        messages=messages,
        run_id=str(body["run_id"]) if body.get("run_id") else None,
        theme=str(body["theme"]) if body.get("theme") else None,
        model=str(body["model"]) if body.get("model") else None,
    )
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_chat_stream(request: Request) -> StreamingResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    messages = body.get("messages")
    if not isinstance(messages, list):
        messages = []

    def gen() -> Iterator[str]:
        yield from iter_compare_chat_sse(
            mode=str(body.get("mode") or "plain"),
            messages=messages,
            run_id=str(body["run_id"]) if body.get("run_id") else None,
            theme=str(body["theme"]) if body.get("theme") else None,
            model=str(body["model"]) if body.get("model") else None,
        )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def create_app() -> Starlette:
    load_database_env()
    return Starlette(
        routes=[
            Route("/api/health", health),
            Route("/api/session", session),
            Route("/api/session/logout", session_logout, methods=["POST"]),
            Route("/api/session/history", session_history),
            Route("/api/timeline", timeline),
            Route("/api/timeline/sessions/{session_id}", timeline_session),
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
            Route("/api/reports/{report_id}", report_detail),
            Route("/api/reports/{report_id}/file", report_file),
            Route("/api/audit", audit_status),
            Route("/api/audit/start", audit_start, methods=["POST"]),
            Route("/api/consensus", consensus_status),
            Route("/api/consensus/history", consensus_history),
            Route("/api/consensus/latest", consensus_latest),
            Route("/api/consensus/events", consensus_events),
            Route("/api/consensus/start", consensus_start, methods=["POST"]),
            Route("/api/consensus/stop", consensus_stop, methods=["POST"]),
            Route("/api/consensus/inputs", consensus_inputs),
            Route("/api/consensus/chat", consensus_chat, methods=["POST"]),
            Route(
                "/api/consensus/chat/stream",
                consensus_chat_stream,
                methods=["POST"],
            ),
            Route("/api/consensus/runs/{run_id}/outputs", consensus_outputs),
            Route("/api/consensus/runs/{run_id}/docs", consensus_docs),
        ],
        middleware=[Middleware(ApiKeyMiddleware)],
        lifespan=lifespan,
    )


app = create_app()
