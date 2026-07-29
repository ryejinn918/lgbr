"""Local LGBR API for industry-trend collect and sector consensus."""

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
from lgbr_api.collection import (
    get_current_job,
    reconcile_stale_jobs,
    request_stop as collection_request_stop,
    start_feed,
    start_fetch_body,
    start_search,
)
from lgbr_api.consensus_api import (
    compare_chat,
    continue_run,
    get_current_run,
    get_latest_ended,
    get_outputs,
    get_run_doc_compress,
    get_run_docs,
    list_events as list_consensus_events,
    list_history as list_consensus_history,
    list_inputs,
    reconcile_stale_runs,
    request_stop as consensus_request_stop,
    start_run,
)
from lgbr_api.consensus_chat import iter_compare_chat_sse
from lgbr_api.consensus_eval import get_eval as consensus_get_eval
from lgbr_api.consensus_eval import iter_eval_sse
from lgbr_api.consensus_eval import mark_all_open_evals_interrupted
from lgbr_api.consensus_eval import start_eval as consensus_start_eval
from lgbr_api.crawls import (
    get_cdp_status,
    get_current_crawl,
    list_crawl_events,
    reconcile_stale_crawls,
    request_stop,
    shutdown_open_crawl,
    start_crawl,
)
from lgbr_api.db import load_database_env
from lgbr_api.news_articles import list_articles
from lgbr_api.profiles import list_profiles, update_profile
from lgbr_api.audits import get_audit_status, start_audit
from lgbr_api.reports import (
    coverage_by_week,
    get_report,
    get_report_file,
    list_reports,
)
from lgbr_api.sessions import get_current_session, list_history
from lgbr_api.timeline import list_session_timeline, list_timeline

SHUTDOWN_WAIT_SECONDS = 60.0


@asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    # Eval runs inside the request SSE; anything left open cannot resume.
    await asyncio.to_thread(mark_all_open_evals_interrupted)
    # Detached workers survive API restarts. Reconcile only dead/stale rows;
    # live worker PIDs and human-review consensus pauses remain open.
    await asyncio.to_thread(reconcile_stale_crawls)
    await asyncio.to_thread(reconcile_stale_jobs)
    await asyncio.to_thread(reconcile_stale_runs)
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
    mode = "ai"
    limit: int | None = None
    debug = False
    catalog: str | None = None
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
        if body.get("catalog") is not None:
            catalog = str(body.get("catalog") or "").strip() or None
    result = start_crawl(mode=mode, limit=limit, debug=debug, catalog=catalog)
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def crawl_stop(_: Request) -> JSONResponse:
    return JSONResponse(request_stop())


async def cdp_status(_: Request) -> JSONResponse:
    result = get_cdp_status()
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def collection_status(request: Request) -> JSONResponse:
    source = request.query_params.get("source")
    capability = request.query_params.get("capability") or "feed"
    return JSONResponse(
        get_current_job(
            source=str(source) if source else None,
            capability=str(capability),
        )
    )


async def collection_start(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    source = str(body.get("source") or "arg")
    capability = str(body.get("capability") or "feed").strip().lower()

    if capability == "fetch_body":
        limit_raw = body.get("limit")
        delay_raw = body.get("delay_seconds")
        try:
            limit = int(limit_raw) if limit_raw is not None else None
        except (TypeError, ValueError):
            return JSONResponse(
                {
                    "ok": False,
                    "label": "오류",
                    "message": "limit must be an integer",
                    "job": None,
                    "can_start": False,
                },
                status_code=400,
            )
        try:
            delay = float(delay_raw) if delay_raw is not None else None
        except (TypeError, ValueError):
            return JSONResponse(
                {
                    "ok": False,
                    "label": "오류",
                    "message": "delay_seconds must be a number",
                    "job": None,
                    "can_start": False,
                },
                status_code=400,
            )
        result = start_fetch_body(
            source=source, limit=limit, delay_seconds=delay
        )
        status = int(result.pop("status", 200 if result.get("ok") else 400))
        return JSONResponse(result, status_code=status)

    if capability == "search":
        max_pages = body.get("max_pages")
        period_months = body.get("period_months")
        limit_raw = body.get("limit")
        catalog_raw = body.get("catalog")
        delay_raw = body.get("item_delay_seconds")
        try:
            pages = int(max_pages) if max_pages is not None else None
        except (TypeError, ValueError):
            return JSONResponse(
                {
                    "ok": False,
                    "label": "오류",
                    "message": "max_pages must be an integer",
                    "job": None,
                    "can_start": False,
                },
                status_code=400,
            )
        try:
            months = int(period_months) if period_months is not None else None
        except (TypeError, ValueError):
            return JSONResponse(
                {
                    "ok": False,
                    "label": "오류",
                    "message": "period_months must be an integer",
                    "job": None,
                    "can_start": False,
                },
                status_code=400,
            )
        try:
            lim = int(limit_raw) if limit_raw is not None else None
        except (TypeError, ValueError):
            return JSONResponse(
                {
                    "ok": False,
                    "label": "오류",
                    "message": "limit must be an integer",
                    "job": None,
                    "can_start": False,
                },
                status_code=400,
            )
        try:
            delay = float(delay_raw) if delay_raw is not None else None
        except (TypeError, ValueError):
            return JSONResponse(
                {
                    "ok": False,
                    "label": "오류",
                    "message": "item_delay_seconds must be a number",
                    "job": None,
                    "can_start": False,
                },
                status_code=400,
            )
        catalog = (
            str(catalog_raw).strip() if catalog_raw is not None else None
        )
        result = start_search(
            source=source,
            max_pages=pages,
            period_months=months,
            limit=lim,
            catalog=catalog,
            item_delay_seconds=delay,
        )
        status = int(result.pop("status", 200 if result.get("ok") else 400))
        return JSONResponse(result, status_code=status)

    if capability != "feed":
        return JSONResponse(
            {
                "ok": False,
                "label": "오류",
                "message": "capability must be 'feed', 'search', or 'fetch_body'",
                "job": None,
                "can_start": False,
            },
            status_code=400,
        )

    max_pages = body.get("max_pages")
    period_months = body.get("period_months")
    try:
        pages = int(max_pages) if max_pages is not None else None
    except (TypeError, ValueError):
        return JSONResponse(
            {
                "ok": False,
                "label": "오류",
                "message": "max_pages must be an integer",
                "job": None,
                "can_start": False,
            },
            status_code=400,
        )
    try:
        months = int(period_months) if period_months is not None else None
    except (TypeError, ValueError):
        return JSONResponse(
            {
                "ok": False,
                "label": "오류",
                "message": "period_months must be an integer",
                "job": None,
                "can_start": False,
            },
            status_code=400,
        )
    result = start_feed(source=source, max_pages=pages, period_months=months)
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def collection_stop(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    source = body.get("source")
    capability = body.get("capability") or "feed"
    return JSONResponse(
        collection_request_stop(
            source=str(source) if source else None,
            capability=str(capability) if capability else "feed",
        )
    )


async def news_articles(request: Request) -> JSONResponse:
    try:
        limit = int(request.query_params.get("limit", "30"))
    except ValueError:
        limit = 30
    try:
        offset = int(request.query_params.get("offset", "0"))
    except ValueError:
        offset = 0
    result = list_articles(
        source=request.query_params.get("source") or "all",
        q=request.query_params.get("q"),
        has_body=request.query_params.get("has_body") or "all",
        limit=limit,
        offset=offset,
    )
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
        source=request.query_params.get("source"),
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


async def reports_coverage(request: Request) -> JSONResponse:
    try:
        weeks = int(request.query_params.get("weeks", "13"))
    except ValueError:
        weeks = 13
    return JSONResponse(coverage_by_week(weeks=weeks))


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
    theme = request.query_params.get("theme") or "ai"
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
    theme = str(body.get("theme") or "ai")
    question = body.get("question")
    until_raw = body.get("until")
    until = str(until_raw).strip() if until_raw is not None else None
    result = start_run(
        theme=theme,
        question=str(question) if question is not None else None,
        until=until,
    )
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_continue(request: Request) -> JSONResponse:
    run_id = str(request.path_params.get("run_id") or "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    pillars = body.get("pillar_sketch")
    if pillars is not None and not isinstance(pillars, list):
        pillars = None
    until_raw = body.get("until")
    until = str(until_raw).strip() if until_raw is not None else None
    resume_raw = body.get("resume_from")
    resume_from = str(resume_raw).strip() if resume_raw is not None else None
    result = continue_run(
        run_id,
        thesis=str(body["thesis"]) if body.get("thesis") is not None else None,
        cut_logic=str(body["cut_logic"]) if body.get("cut_logic") is not None else None,
        pillar_sketch=[str(p) for p in pillars] if pillars is not None else None,
        until=until,
        resume_from=resume_from,
    )
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_stop(_: Request) -> JSONResponse:
    return JSONResponse(consensus_request_stop())


async def consensus_inputs(request: Request) -> JSONResponse:
    theme = request.query_params.get("theme") or "ai"
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


async def consensus_doc_compress(request: Request) -> JSONResponse:
    run_id = str(request.path_params.get("run_id") or "")
    report_id = str(request.path_params.get("report_id") or "")
    result = get_run_doc_compress(run_id, report_id)
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_eval_get(request: Request) -> JSONResponse:
    run_id = str(request.path_params.get("run_id") or "")
    result = consensus_get_eval(run_id)
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_eval_start(request: Request) -> JSONResponse:
    run_id = str(request.path_params.get("run_id") or "")
    result = consensus_start_eval(run_id)
    status = int(result.pop("status", 200 if result.get("ok") else 400))
    return JSONResponse(result, status_code=status)


async def consensus_eval_stream(request: Request) -> StreamingResponse:
    run_id = str(request.path_params.get("run_id") or "")

    def gen() -> Iterator[str]:
        yield from iter_eval_sse(run_id)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
            Route("/api/collection", collection_status),
            Route("/api/collection/start", collection_start, methods=["POST"]),
            Route("/api/collection/stop", collection_stop, methods=["POST"]),
            Route("/api/news-articles", news_articles),
            Route("/api/reports", reports),
            Route("/api/reports/coverage", reports_coverage),
            Route("/api/reports/{report_id}", report_detail),
            Route("/api/reports/{report_id}/file", report_file),
            Route("/api/audit", audit_status),
            Route("/api/audit/start", audit_start, methods=["POST"]),
            Route("/api/consensus", consensus_status),
            Route("/api/consensus/history", consensus_history),
            Route("/api/consensus/latest", consensus_latest),
            Route("/api/consensus/events", consensus_events),
            Route("/api/consensus/start", consensus_start, methods=["POST"]),
            Route(
                "/api/consensus/runs/{run_id}/continue",
                consensus_continue,
                methods=["POST"],
            ),
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
            Route(
                "/api/consensus/runs/{run_id}/docs/{report_id}/compress",
                consensus_doc_compress,
            ),
            Route("/api/consensus/runs/{run_id}/eval", consensus_eval_get),
            Route(
                "/api/consensus/runs/{run_id}/eval",
                consensus_eval_start,
                methods=["POST"],
            ),
            Route(
                "/api/consensus/runs/{run_id}/eval/stream",
                consensus_eval_stream,
                methods=["POST"],
            ),
        ],
        middleware=[Middleware(ApiKeyMiddleware)],
        lifespan=lifespan,
    )


app = create_app()
