"""CLI: python -m lgbr_mcp"""

from __future__ import annotations

import argparse
import os

import uvicorn

from lgbr_mcp.config import clear_config_caches, load_env, validate_startup


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="LGBR MCP connectors (read-only)")
    parser.add_argument(
        "--host",
        default=os.environ.get("LGBR_MCP_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("LGBR_MCP_PORT", "8788")),
    )
    args = parser.parse_args()
    os.environ.setdefault("LGBR_MCP_HOST", args.host)
    os.environ.setdefault("LGBR_MCP_PORT", str(args.port))
    clear_config_caches()
    validate_startup()

    uvicorn.run(
        "lgbr_mcp.asgi:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
