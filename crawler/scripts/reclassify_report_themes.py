#!/usr/bin/env python3
"""Reclassify attrs.themes[] only (preserve quality_* and short_title)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.quality_audit import DEFAULT_CONCURRENCY, DEFAULT_MODEL  # noqa: E402
from crawler.theme_reclassify import run_reclassify  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--report-id", default=None)
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only rows without attrs.themes[]",
    )
    parser.add_argument(
        "--has-themes",
        default=None,
        help="Comma-separated theme ids; only rows whose themes[] contain ALL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify but do not write attrs.themes",
    )
    args = parser.parse_args()

    rid: UUID | str | None = args.report_id
    require: tuple[str, ...] | None = None
    if args.has_themes:
        require = tuple(
            t.strip() for t in str(args.has_themes).split(",") if t.strip()
        )
    stats = asyncio.run(
        run_reclassify(
            limit=args.limit,
            concurrency=args.concurrency,
            model=args.model,
            report_id=rid,
            missing_themes_only=args.missing_only,
            require_themes=require,
            dry_run=args.dry_run,
        )
    )
    print(json.dumps({"ok": True, "stats": stats}, ensure_ascii=False))
    if int(stats.get("quality_drift") or 0) > 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
