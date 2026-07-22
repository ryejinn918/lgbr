"""Local status API for the Fnguide search monitor."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from lgbr_api.status_file import read_status


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def session(_: Request) -> JSONResponse:
    return JSONResponse(read_status())


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/api/health", health),
            Route("/api/session", session),
        ]
    )


app = create_app()
