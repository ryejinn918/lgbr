"""MagpieLabs branding assets for MCP connectors."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from mcp.types import Icon

_STATIC = Path(__file__).resolve().parent / "static"
FAVICON_SVG_PATH = _STATIC / "favicon.svg"
FAVICON_PNG_PATH = _STATIC / "favicon.png"
FAVICON_ICO_PATH = _STATIC / "favicon.ico"

# Back-compat alias used by ASGI SVG route.
FAVICON_PATH = FAVICON_SVG_PATH


def landing_html() -> str:
    from lgbr_mcp.catalog import render_landing_html

    return render_landing_html()


@lru_cache(maxsize=1)
def favicon_bytes() -> bytes:
    return FAVICON_SVG_PATH.read_bytes()


@lru_cache(maxsize=1)
def favicon_png_bytes() -> bytes:
    return FAVICON_PNG_PATH.read_bytes()


@lru_cache(maxsize=1)
def server_icons() -> list[Icon]:
    """Prefer PNG for clients that ignore SVG; keep SVG as scalable fallback."""
    png = base64.b64encode(favicon_png_bytes()).decode("ascii")
    svg = base64.b64encode(favicon_bytes()).decode("ascii")
    return [
        Icon(
            src=f"data:image/png;base64,{png}",
            mimeType="image/png",
            sizes=["64x64"],
        ),
        Icon(
            src=f"data:image/svg+xml;base64,{svg}",
            mimeType="image/svg+xml",
            sizes=["any"],
        ),
    ]
