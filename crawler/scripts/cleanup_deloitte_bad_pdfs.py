#!/usr/bin/env python3
"""Clear Deloitte downloads that are blank page.pdf or non-Deloitte PDF hrefs.

No live HTTP to deloitte.com — DB + local file cleanup only. Quality fields are
cleared so stale「본문없음」summaries are not reused. Re-run search/capture after.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.db import connect  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sql = """
        SELECT id, source_key, title, file_path, status,
               attrs->>'capture' AS capture,
               attrs->>'pdf_url' AS pdf_url,
               coalesce((attrs->>'bytes')::int, 0) AS bytes
        FROM reports
        WHERE source = 'deloitte'
          AND status = 'downloaded'
          AND (
            attrs->>'capture' = 'page.pdf'
            OR (
              attrs ? 'pdf_url'
              AND attrs->>'pdf_url' !~* '(^|://)([^/]*\\.)?deloitte\\.com(/|$)'
            )
          )
        ORDER BY source_key
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = list(cur.fetchall())

    stats = {"candidates": len(rows), "cleared": 0, "files_removed": 0}
    for row in rows:
        reason = (
            "empty_page_pdf"
            if row.get("capture") == "page.pdf"
            else "non_deloitte_pdf"
        )
        path = Path(row["file_path"]) if row.get("file_path") else None
        print(
            f"{reason} bytes={row.get('bytes')} {(row.get('title') or '')[:60]}",
            flush=True,
        )
        if args.dry_run:
            continue
        if path and path.is_file():
            path.unlink(missing_ok=True)
            stats["files_removed"] += 1
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE reports
                SET status = 'listed',
                    file_path = NULL,
                    file_name = NULL,
                    downloaded_at = NULL,
                    page_count = NULL,
                    quality_json = '{}'::jsonb,
                    quality_pass = NULL,
                    quality_confidence = NULL,
                    quality_scope = NULL,
                    quality_model = NULL,
                    quality_at = NULL,
                    attrs = (
                      COALESCE(attrs, '{}'::jsonb)
                      - 'pdf_url' - 'bytes' - 'capture' - 'body_len'
                      - 'pdf_text_len' - 'no_pdf' - 'error' - 'capture_empty'
                    ) || %s::jsonb
                WHERE id = %s
                """,
                (
                    json.dumps(
                        {
                            "cleanup": "deloitte_bad_pdfs",
                            "cleanup_reason": reason,
                        },
                        ensure_ascii=False,
                    ),
                    row["id"],
                ),
            )
            conn.commit()
        stats["cleared"] += 1

    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
