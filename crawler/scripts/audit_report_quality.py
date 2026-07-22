#!/usr/bin/env python3
"""Batch quality-audit downloaded reports (sector-framework pass)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow `uv run python scripts/audit_report_quality.py` from crawler/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.quality_audit import (  # noqa: E402
    DEFAULT_CONCURRENCY,
    DEFAULT_MODEL,
    run_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max reports to audit (default: all pending)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-audit even if quality_at is set",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Parallel OpenRouter requests (default {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenRouter model id (default {DEFAULT_MODEL})",
    )
    args = parser.parse_args()
    stats = asyncio.run(
        run_audit(
            force=args.force,
            limit=args.limit,
            concurrency=args.concurrency,
            model=args.model,
        )
    )
    print("stats", stats)


if __name__ == "__main__":
    main()
