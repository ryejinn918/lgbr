#!/usr/bin/env python3
"""Backfill consulting reports stuck in no_download via page.pdf capture."""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.asset_id import DOWNLOADS_ROOT, downloads_dir, make_asset_id  # noqa: E402
from crawler.db import connect  # noqa: E402
from crawler.sources.page_pdf_capture import (  # noqa: E402
    LazyCaptureBrowser,
    process_no_pdf_with_page_capture,
)

SOURCES = ("pwc", "accenture", "kpmg", "ey", "deloitte")


@dataclass
class _Summary:
    downloaded: list[str] = field(default_factory=list)
    skipped_no_download: int = 0
    failed: int = 0


def _safe_filename(key: str) -> str:
    base = key.replace("/", "__")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:180] or "report"


def _load_rows(sources: list[str], *, limit: int | None) -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source, source_key, title, published_at, attrs
                FROM reports
                WHERE source = ANY(%s)
                  AND status = 'no_download'
                  AND file_path IS NULL
                  AND attrs->>'url' IS NOT NULL
                  AND attrs->>'url' <> ''
                ORDER BY source, last_seen_at DESC NULLS LAST
                """
                + (" LIMIT %s" if limit is not None else ""),
                (sources, limit) if limit is not None else (sources,),
            )
            return [dict(r) for r in cur.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        choices=SOURCES,
        help="Limit to source(s); default all five",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between items")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List candidates only",
    )
    args = parser.parse_args()
    sources = list(args.source) if args.source else list(SOURCES)
    rows = _load_rows(sources, limit=args.limit)
    print(f"candidates={len(rows)} sources={sources}")
    if args.dry_run:
        for r in rows:
            print(f"  {r['source']}\t{r['source_key']}\t{(r.get('attrs') or {}).get('url')}")
        return 0

    by_source: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_source.setdefault(r["source"], []).append(r)

    totals = _Summary()
    for source, items in by_source.items():
        download_dir = downloads_dir(make_asset_id(source), root=DOWNLOADS_ROOT)
        download_dir.mkdir(parents=True, exist_ok=True)
        capture = LazyCaptureBrowser(source, downloads_path=download_dir)
        summary = _Summary()
        already: set[str] = set()
        progress: dict[str, Any] = {}
        try:
            for i, row in enumerate(items, 1):
                attrs = dict(row.get("attrs") or {})
                url = str(attrs.get("url") or "").strip()
                key = str(row["source_key"])
                dest = download_dir / f"{_safe_filename(key)}.pdf"
                print(f"[{source} {i}/{len(items)}] {key}", flush=True)
                process_no_pdf_with_page_capture(
                    capture=capture,
                    source=source,
                    source_key=key,
                    title=str(row.get("title") or key),
                    published_at=row.get("published_at"),
                    url=url,
                    dest=dest,
                    attrs=attrs,
                    already=already,
                    summary=summary,
                    progress=progress,
                )
                if args.delay > 0 and i < len(items):
                    time.sleep(args.delay)
        finally:
            capture.close()
        print(
            f"{source}: downloaded={len(summary.downloaded)} "
            f"empty={summary.skipped_no_download} failed={summary.failed}",
            flush=True,
        )
        totals.downloaded.extend(summary.downloaded)
        totals.skipped_no_download += summary.skipped_no_download
        totals.failed += summary.failed

    print(
        f"done: downloaded={len(totals.downloaded)} "
        f"empty={totals.skipped_no_download} failed={totals.failed}"
    )
    return 0 if totals.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
