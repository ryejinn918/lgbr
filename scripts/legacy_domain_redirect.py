"""301 redirect nest1/chamber1 → universe/shape (Cloudflare tunnel origin)."""

from __future__ import annotations

import argparse

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Route

_HOST_MAP = {
    "nest1.magpielabs.co.kr": "https://universe.lgbr-ai.com",
    "chamber1.magpielabs.co.kr": "https://shape.lgbr-ai.com",
}


async def redirect(request: Request) -> RedirectResponse | PlainTextResponse:
    host = (request.headers.get("host") or "").split(":")[0].lower()
    base = _HOST_MAP.get(host)
    if not base:
        return PlainTextResponse("Unknown host", status_code=404)
    path = request.url.path or "/"
    qs = request.url.query
    target = f"{base}{path}" + (f"?{qs}" if qs else "")
    return RedirectResponse(target, status_code=301)


app = Starlette(
    routes=[
        Route("/", redirect),
        Route("/{path:path}", redirect),
    ]
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8790)
    args = p.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
