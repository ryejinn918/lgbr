"""CLI: python -m lgbr_api"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="LGBR local status API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    uvicorn.run("lgbr_api.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
