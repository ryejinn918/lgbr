#!/usr/bin/env python3
"""Backfill HBR reports.published_at from article JSON-LD / PDF byline.

The list crawler previously fell back to URL year/month day-1 when card dates
were missed. Re-read canonical dates and overwrite day-1 (and mismatched) rows.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.db import connect  # noqa: E402
from crawler.sources.hbr_browser import parse_publish_date  # noqa: E402

DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4}\b",
    re.I,
)
LD_RE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
META_RE = re.compile(
    r'(?:property|name)=["\']article:published_time["\'][^>]*content=["\']([^"\']+)'
    r'|content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']article:published_time',
    re.I,
)
UA = "Mozilla/5.0 (compatible; lgbr-hbr-date-backfill/1.0)"


def _from_pdf(path: Path | None) -> tuple[date | None, str]:
    if not path or not path.is_file() or not shutil.which("pdftotext"):
        return None, ""
    proc = subprocess.run(
        ["pdftotext", "-f", "1", "-l", "2", str(path), "-"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    txt = proc.stdout or ""
    m = DATE_RE.search(txt)
    if not m:
        return None, ""
    raw = m.group(0)
    return parse_publish_date(raw), raw


def _from_html(html: str) -> tuple[date | None, str, str]:
    ld = LD_RE.search(html or "")
    if ld:
        raw = ld.group(1).strip()
        pub = parse_publish_date(raw)
        if pub:
            return pub, raw, "json_ld"
    meta = META_RE.search(html or "")
    if meta:
        raw = (meta.group(1) or meta.group(2) or "").strip()
        pub = parse_publish_date(raw)
        if pub:
            return pub, raw, "meta"
    by = DATE_RE.search(html or "")
    if by:
        raw = by.group(0)
        pub = parse_publish_date(raw)
        if pub:
            return pub, raw, "byline"
    return None, "", ""


def _fetch_html(client: httpx.Client, url: str) -> str:
    resp = client.get(url, timeout=45.0)
    resp.raise_for_status()
    return resp.text or ""


def fetch_targets(*, only_day_one: bool, limit: int | None) -> list[dict[str, Any]]:
    where = ["source = 'hbr'", "attrs ? 'url'"]
    if only_day_one:
        where.append("published_at IS NOT NULL AND EXTRACT(DAY FROM published_at) = 1")
    sql = f"""
        SELECT id, source_key, title, published_at, file_path,
               attrs->>'url' AS url,
               attrs->>'publish_date_raw' AS publish_date_raw,
               status
        FROM reports
        WHERE {' AND '.join(where)}
        ORDER BY published_at DESC NULLS LAST, source_key
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s"
        params.append(max(1, int(limit)))
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def apply_update(
    *,
    report_id: Any,
    published_at: date,
    publish_date_raw: str,
    source: str,
    dry_run: bool,
) -> None:
    patch = {
        "publish_date_raw": publish_date_raw,
        "publish_date_backfill": "hbr_dates",
        "publish_date_backfill_source": source,
    }
    if dry_run:
        return
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE reports
            SET published_at = %s,
                attrs = COALESCE(attrs, '{}'::jsonb) || %s::jsonb
            WHERE id = %s
            """,
            (published_at, Jsonb(patch), report_id),
        )
        conn.commit()


def run(
    *,
    dry_run: bool,
    only_day_one: bool,
    limit: int | None,
    delay: float,
    prefer_http: bool,
) -> dict[str, int]:
    rows = fetch_targets(only_day_one=only_day_one, limit=limit)
    stats = {
        "candidates": len(rows),
        "updated": 0,
        "unchanged": 0,
        "skipped_no_date": 0,
        "http_ok": 0,
        "pdf_ok": 0,
        "http_fail": 0,
    }
    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(follow_redirects=True, headers=headers) as client:
        for i, row in enumerate(rows, 1):
            url = str(row.get("url") or "").strip()
            old = row.get("published_at")
            if hasattr(old, "date"):
                old = old.date()
            pub: date | None = None
            raw = ""
            source = ""

            if prefer_http and url:
                try:
                    html = _fetch_html(client, url)
                    pub, raw, source = _from_html(html)
                    if pub:
                        stats["http_ok"] += 1
                        source = f"http:{source}"
                except Exception as exc:
                    stats["http_fail"] += 1
                    print(
                        f"[{i}/{len(rows)}] http_fail {row['source_key']}: {exc}",
                        flush=True,
                    )
                if delay > 0:
                    time.sleep(delay)

            if pub is None:
                pdf_pub, pdf_raw = _from_pdf(
                    Path(row["file_path"]) if row.get("file_path") else None
                )
                if pdf_pub:
                    pub, raw, source = pdf_pub, pdf_raw, "pdf"
                    stats["pdf_ok"] += 1

            if pub is None:
                stats["skipped_no_date"] += 1
                print(
                    f"[{i}/{len(rows)}] no_date {old} {(row.get('title') or '')[:60]}",
                    flush=True,
                )
                continue

            if old == pub:
                stats["unchanged"] += 1
                print(
                    f"[{i}/{len(rows)}] ok {pub} (unchanged) {row['source_key'][:48]}",
                    flush=True,
                )
                continue

            apply_update(
                report_id=row["id"],
                published_at=pub,
                publish_date_raw=raw or pub.isoformat(),
                source=source,
                dry_run=dry_run,
            )
            stats["updated"] += 1
            flag = "DRY " if dry_run else ""
            print(
                f"[{i}/{len(rows)}] {flag}{old} -> {pub} via {source} "
                f"{(row.get('title') or '')[:55]}",
                flush=True,
            )
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--all",
        action="store_true",
        help="Include non day-1 rows (default: only day==1)",
    )
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument(
        "--pdf-first",
        action="store_true",
        help="Try PDF before HTTP (default: HTTP first)",
    )
    args = ap.parse_args()
    stats = run(
        dry_run=bool(args.dry_run),
        only_day_one=not bool(args.all),
        limit=args.limit,
        delay=max(0.0, float(args.delay)),
        prefer_http=not bool(args.pdf_first),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
