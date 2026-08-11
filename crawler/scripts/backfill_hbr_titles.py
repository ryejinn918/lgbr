#!/usr/bin/env python3
"""Backfill HBR report titles polluted by magazine-package list scraping.

Targets rows where the same title appears on 2+ hbr reports, fetches each
article URL over HTTP (no login), and updates title from og:title / h1 / <title>.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from crawler.db import connect  # noqa: E402

load_dotenv(ROOT.parent / ".env", override=False)

SOURCE = "hbr"
UA = (
    "Mozilla/5.0 (compatible; lgbr-hbr-title-backfill/1.0; "
    "+https://github.com/lgbr)"
)
_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_RE_FLIP = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
    re.I,
)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html_text(raw: str) -> str:
    text = _TAG_RE.sub(" ", raw or "")
    text = (
        text.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", text).strip()


def fetch_title(url: str, *, timeout: float = 30.0) -> tuple[str | None, str | None]:
    """Return (title, source_tag) where source_tag is http:og|http:h1|http:title."""
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read(800_000).decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return None, f"error:{exc}"

    m = _OG_RE.search(body) or _OG_RE_FLIP.search(body)
    if m:
        title = _clean_html_text(m.group(1))
        if title:
            return title[:500], "http:og"

    m = _H1_RE.search(body)
    if m:
        title = _clean_html_text(m.group(1))
        if title:
            return title[:500], "http:h1"

    m = _TITLE_RE.search(body)
    if m:
        title = _clean_html_text(m.group(1))
        # Strip common " | Harvard Business Review" suffix.
        title = re.sub(r"\s*[|\-–—]\s*Harvard Business Review\s*$", "", title, flags=re.I)
        title = title.strip()
        if title:
            return title[:500], "http:title"

    return None, "error:no_title"


def load_targets() -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.source_key, r.title, r.attrs, r.published_at
                FROM reports r
                WHERE r.source = %s
                  AND r.title IN (
                    SELECT title
                    FROM reports
                    WHERE source = %s
                    GROUP BY title
                    HAVING count(*) > 1
                  )
                ORDER BY r.title, r.source_key
                """,
                (SOURCE, SOURCE),
            )
            return [dict(row) for row in cur.fetchall()]


def resolve_url(row: dict[str, Any]) -> str:
    attrs = row.get("attrs") or {}
    if isinstance(attrs, str):
        attrs = json.loads(attrs)
    url = str(attrs.get("url") or "").strip()
    if url:
        return url
    pub = row.get("published_at")
    slug = str(row.get("source_key") or "").strip()
    if pub is not None and slug:
        return f"https://hbr.org/{pub.year:04d}/{pub.month:02d}/{slug}"
    return ""


def apply_title(
    *,
    report_id: Any,
    title: str,
    backfill_tag: str,
    attrs: dict[str, Any],
) -> None:
    merged = dict(attrs or {})
    merged["title_backfill"] = backfill_tag
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE reports
                SET title = %s,
                    attrs = COALESCE(attrs, '{}'::jsonb) || %s::jsonb,
                    last_seen_at = now()
                WHERE id = %s
                """,
                (title, json.dumps(merged, ensure_ascii=False), str(report_id)),
            )
        conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write title updates (default: dry-run)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.4,
        help="Seconds between HTTP fetches (default 0.4)",
    )
    args = parser.parse_args()

    rows = load_targets()
    print(f"targets={len(rows)} apply={args.apply}")
    updated = 0
    skipped = 0
    failed = 0
    for row in rows:
        attrs = row.get("attrs") or {}
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
            row["attrs"] = attrs
        url = resolve_url(row)
        if not url:
            print(f"skip no-url {row['source_key']}")
            skipped += 1
            continue
        title, tag = fetch_title(url)
        old = str(row.get("title") or "")
        if not title or not tag or tag.startswith("error:"):
            print(f"fail {row['source_key']}: {tag}")
            failed += 1
            time.sleep(max(args.delay, 0.0))
            continue
        if title == old:
            print(f"same {row['source_key']}: {title}")
            skipped += 1
            time.sleep(max(args.delay, 0.0))
            continue
        print(f"{'APPLY' if args.apply else 'dry'} {row['source_key']}")
        print(f"  {old!r}")
        print(f"  -> {title!r} ({tag})")
        if args.apply:
            apply_title(
                report_id=row["id"],
                title=title,
                backfill_tag=tag,
                attrs=attrs,
            )
            updated += 1
        else:
            updated += 1
        time.sleep(max(args.delay, 0.0))

    print(f"done updated={updated} skipped={skipped} failed={failed}")
    if args.apply:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT title, count(*)::int AS n
                    FROM reports
                    WHERE source = %s
                    GROUP BY title
                    HAVING count(*) > 1
                    ORDER BY n DESC, title
                    """,
                    (SOURCE,),
                )
                dups = cur.fetchall()
        print(f"remaining_duplicate_title_groups={len(dups)}")
        for d in dups[:10]:
            print(f"  {d['n']} | {d['title']}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
