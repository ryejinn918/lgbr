"""Local status API for the Fnguide search monitor."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from lgbr_api.db import load_database_env
from lgbr_api.sessions import get_current_session, list_history, request_logout


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def session(_: Request) -> JSONResponse:
    return JSONResponse(get_current_session())


async def session_logout(_: Request) -> JSONResponse:
    return JSONResponse(request_logout())


async def session_history(request: Request) -> JSONResponse:
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        limit = 50
    return JSONResponse({"items": list_history(limit=limit)})


def create_app() -> Starlette:
    load_database_env()
    return Starlette(
        routes=[
            Route("/api/health", health),
            Route("/api/session", session),
            Route("/api/session/logout", session_logout, methods=["POST"]),
            Route("/api/session/history", session_history),
        ]
    )


app = create_app()
