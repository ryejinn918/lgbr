#!/usr/bin/env python3
"""Re-download Deloitte reports cleared by cleanup_deloitte_bad_pdfs.

Guards (no third-party PDFs / no blank page.pdf):
- ``find_pdf_url`` / ``download_pdf`` only accept ``*.deloitte.com``
- ``page.pdf`` uses opacity unstick + byte/text gates
- paced delay between items; one shared capture browser
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler import reports_store  # noqa: E402
from crawler.asset_id import DOWNLOADS_ROOT, downloads_dir, make_asset_id  # noqa: E402
from crawler.db import connect  # noqa: E402
from crawler.jobs.media_pace import pace_after_item  # noqa: E402
from crawler.sources.deloitte_http import (  # noqa: E402
    SOURCE,
    download_pdf,
    fetch_detail_meta,
    make_session,
    pdf_page_count,
)
from crawler.sources.page_pdf_capture import (  # noqa: E402
    EmptyPagePdfError,
    LazyCaptureBrowser,
    capture_url_as_pdf,
    pdf_extract_char_count,
)

LOG_DIR = Path(".crawler/snapshots/deloitte-backfill")


def _safe_filename(key: str) -> str:
    base = key.replace("/", "__")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:180] or "deloitte_report"


def fetch_targets(*, cleaned_only: bool, limit: int | None) -> list[dict[str, Any]]:
    where = [
        "source = 'deloitte'",
        "status = 'listed'",
        "attrs ? 'url'",
        "file_path IS NULL",
    ]
    if cleaned_only:
        where.append("attrs->>'cleanup' = 'deloitte_bad_pdfs'")
    sql = f"""
        SELECT id, source_key, title, published_at,
               attrs->>'url' AS url,
               attrs
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


def _is_deloitte_host(url: str) -> bool:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host == "deloitte.com" or host.endswith(".deloitte.com")


def run(*, cleaned_only: bool, limit: int | None, delay: float, dry_run: bool) -> dict[str, int]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rows = fetch_targets(cleaned_only=cleaned_only, limit=limit)
    stats = {
        "candidates": len(rows),
        "pdf_href": 0,
        "page_pdf": 0,
        "no_download": 0,
        "failed": 0,
        "skipped_dry": 0,
    }
    asset_id = make_asset_id("deloitte")
    download_dir = downloads_dir(asset_id, root=DOWNLOADS_ROOT)
    download_dir.mkdir(parents=True, exist_ok=True)
    session = make_session()
    capture = LazyCaptureBrowser(SOURCE, downloads_path=download_dir)
    results: list[dict[str, Any]] = []

    try:
        for i, row in enumerate(rows, 1):
            url = str(row.get("url") or "").strip()
            key = str(row["source_key"])
            title = str(row.get("title") or key)
            published_at = row.get("published_at")
            attrs = dict(row.get("attrs") or {})
            attrs.pop("cleanup", None)
            attrs.pop("cleanup_reason", None)
            attrs["backfill"] = "deloitte_downloads"
            dest = download_dir / f"{_safe_filename(key)}.pdf"
            entry: dict[str, Any] = {
                "i": i,
                "source_key": key,
                "url": url,
                "title": title[:120],
            }
            print(f"[{i}/{len(rows)}] {title[:70]}", flush=True)

            if dry_run:
                stats["skipped_dry"] += 1
                entry["status"] = "dry_run"
                results.append(entry)
                continue

            if not url or not _is_deloitte_host(url):
                stats["failed"] += 1
                entry["status"] = "bad_page_url"
                results.append(entry)
                print(f"  fail bad_page_url", flush=True)
                continue

            try:
                pdf_url, detail_date = fetch_detail_meta(url, session=session)
            except Exception as exc:
                stats["failed"] += 1
                entry["status"] = "detail_error"
                entry["error"] = str(exc)[:240]
                reports_store.mark_status(
                    source=SOURCE,
                    source_key=key,
                    status=reports_store.STATUS_FAILED,
                    attrs={**attrs, "error": f"detail_fetch: {exc}"[:300]},
                )
                results.append(entry)
                print(f"  fail detail: {exc}", flush=True)
                pace_after_item(delay)
                continue

            if detail_date is not None:
                published_at = detail_date
                attrs["publish_date"] = published_at.isoformat()

            if pdf_url:
                if not _is_deloitte_host(pdf_url):
                    # Should be unreachable after find_pdf_url fix; refuse anyway.
                    stats["no_download"] += 1
                    entry["status"] = "rejected_non_deloitte_pdf"
                    entry["pdf_url"] = pdf_url
                    reports_store.mark_status(
                        source=SOURCE,
                        source_key=key,
                        status=reports_store.STATUS_NO_DOWNLOAD,
                        clear_download=True,
                        attrs={
                            **attrs,
                            "no_pdf": True,
                            "rejected_pdf_url": pdf_url,
                            "error": "non-deloitte pdf refused",
                        },
                    )
                    results.append(entry)
                    print(f"  reject non-deloitte {pdf_url[:80]}", flush=True)
                    pace_after_item(delay)
                    continue
                try:
                    size = download_pdf(pdf_url, dest, session=session)
                    pages = pdf_page_count(dest)
                    reports_store.mark_downloaded(
                        source=SOURCE,
                        source_key=key,
                        title=title,
                        published_at=published_at,
                        page_count=pages,
                        file_path=str(dest),
                        file_name=dest.name,
                        attrs={
                            **attrs,
                            "pdf_url": pdf_url,
                            "bytes": size,
                            "capture": "pdf_href",
                        },
                    )
                    stats["pdf_href"] += 1
                    entry.update(
                        {"status": "pdf_href", "bytes": size, "pdf_url": pdf_url}
                    )
                    print(f"  ok pdf_href bytes={size}", flush=True)
                except Exception as exc:
                    stats["failed"] += 1
                    dest.unlink(missing_ok=True)
                    entry["status"] = "pdf_download_error"
                    entry["error"] = str(exc)[:240]
                    reports_store.mark_status(
                        source=SOURCE,
                        source_key=key,
                        status=reports_store.STATUS_FAILED,
                        attrs={**attrs, "pdf_url": pdf_url, "error": f"download: {exc}"[:300]},
                    )
                    print(f"  fail pdf: {exc}", flush=True)
                results.append(entry)
                pace_after_item(delay)
                continue

            # No Deloitte PDF href → page.pdf with gates.
            try:
                meta = capture_url_as_pdf(capture.page, url, dest)
                # Extra belt: refuse if still thin after gates (paranoia).
                text_len = int(meta.get("pdf_text_len") or pdf_extract_char_count(dest))
                if text_len < 120 or int(meta.get("bytes") or 0) < 20_000:
                    dest.unlink(missing_ok=True)
                    raise EmptyPagePdfError(
                        f"post-check thin page.pdf text_len={text_len} "
                        f"bytes={meta.get('bytes')}"
                    )
                pages = pdf_page_count(dest)
                reports_store.mark_downloaded(
                    source=SOURCE,
                    source_key=key,
                    title=title,
                    published_at=published_at,
                    page_count=pages,
                    file_path=str(dest),
                    file_name=dest.name,
                    attrs={
                        **attrs,
                        "no_pdf": True,
                        "capture": "page.pdf",
                        "bytes": meta["bytes"],
                        "body_len": meta.get("body_len"),
                        "pdf_text_len": text_len,
                        "opacity_forced": meta.get("opacity_forced"),
                    },
                )
                stats["page_pdf"] += 1
                entry.update(
                    {
                        "status": "page_pdf",
                        "bytes": meta["bytes"],
                        "pdf_text_len": text_len,
                        "opacity_forced": meta.get("opacity_forced"),
                    }
                )
                print(
                    f"  ok page.pdf bytes={meta['bytes']} text={text_len} "
                    f"opacity_forced={meta.get('opacity_forced')}",
                    flush=True,
                )
            except EmptyPagePdfError as exc:
                stats["no_download"] += 1
                dest.unlink(missing_ok=True)
                entry["status"] = "no_download"
                entry["error"] = str(exc)[:240]
                reports_store.mark_status(
                    source=SOURCE,
                    source_key=key,
                    status=reports_store.STATUS_NO_DOWNLOAD,
                    clear_download=True,
                    attrs={
                        **attrs,
                        "no_pdf": True,
                        "capture_empty": True,
                        "error": str(exc)[:300],
                    },
                )
                print(f"  no_download: {exc}", flush=True)
            except Exception as exc:
                stats["failed"] += 1
                dest.unlink(missing_ok=True)
                entry["status"] = "page_pdf_error"
                entry["error"] = str(exc)[:240]
                reports_store.mark_status(
                    source=SOURCE,
                    source_key=key,
                    status=reports_store.STATUS_FAILED,
                    attrs={**attrs, "no_pdf": True, "error": f"page_pdf: {exc}"[:300]},
                )
                print(f"  fail page.pdf: {exc}", flush=True)
            results.append(entry)
            pace_after_item(delay)
    finally:
        capture.close()

    (LOG_DIR / "results.json").write_text(
        json.dumps({"stats": stats, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--all-listed",
        action="store_true",
        help="Include all listed rows without file (default: cleanup-marked only)",
    )
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--delay",
        type=float,
        default=4.0,
        help="Seconds between items (default 4)",
    )
    args = ap.parse_args()
    stats = run(
        cleaned_only=not bool(args.all_listed),
        limit=args.limit,
        delay=max(2.0, float(args.delay)),
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
