"""MagpieLabs branding assets for MCP connectors."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from mcp.types import Icon

FAVICON_PATH = Path(__file__).resolve().parent / "static" / "favicon.svg"


@lru_cache(maxsize=1)
def favicon_bytes() -> bytes:
    return FAVICON_PATH.read_bytes()


@lru_cache(maxsize=1)
def server_icons() -> list[Icon]:
    encoded = base64.b64encode(favicon_bytes()).decode("ascii")
    return [
        Icon(
            src=f"data:image/svg+xml;base64,{encoded}",
            mimeType="image/svg+xml",
            sizes=["any"],
        )
    ]
