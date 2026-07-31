#!/usr/bin/env python3
"""Phase-1 smoke: HTTP list (report profile) → one missing PDF → DB downloaded.

Does not start a collection job. Keeps the browser job untouched.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler import reports_store  # noqa: E402
from crawler.asset_id import DOWNLOADS_ROOT, downloads_dir, make_asset_id  # noqa: E402
from crawler.sources.bcg_http import (  # noqa: E402
    SOURCE,
    download_pdf,
    fetch_detail_meta,
    fetch_list_items,
    get_profile,
    make_session,
    pdf_page_count,
)


def _safe_filename(key: str) -> str:
    base = key.replace("/", "__")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:180] or "bcg_report"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="report")
    ap.add_argument("--limit", type=int, default=1)
    args = ap.parse_args()

    prof = get_profile(args.profile)
    list_url = prof.list_urls[0]
    sess = make_session()
    print(f"list_url={list_url} profile={prof.id}")

    items = fetch_list_items(list_url, profile=prof, session=sess)
    print(f"listed={len(items)}")
    if not items:
        print("FAIL: empty list", file=sys.stderr)
        return 1

    already = reports_store.downloaded_keys(SOURCE)
    asset_id = make_asset_id("bcg")
    download_dir = downloads_dir(asset_id, root=DOWNLOADS_ROOT)
    download_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    for item in items:
        if downloaded >= args.limit:
            break
        if item.source_key in already:
            print(f"skip existing {item.source_key}")
            continue

        print(f"detail {item.url}")
        try:
            pdf_url, detail_date = fetch_detail_meta(
                item.url, session=sess, referer=list_url
            )
        except Exception as exc:
            print(f"skip detail error: {exc}")
            continue
        published = detail_date or item.published_at
        if not pdf_url:
            print(f"skip no pdf on detail {item.source_key}")
            continue

        dest = download_dir / f"{_safe_filename(item.source_key)}.pdf"
        print(f"pdf {pdf_url} -> {dest}")
        try:
            nbytes = download_pdf(pdf_url, dest, session=sess, referer=item.url)
        except Exception as exc:
            print(f"FAIL: download {exc}", file=sys.stderr)
            if dest.is_file():
                dest.unlink(missing_ok=True)
            return 1
        if not dest.is_file() or not dest.read_bytes().startswith(b"%PDF"):
            print("FAIL: file missing or not %PDF", file=sys.stderr)
            return 1

        reports_store.upsert_listed(
            source=SOURCE,
            source_key=item.source_key,
            title=item.title,
            published_at=published,
            attrs={
                "url": item.url,
                "catalog": "us",
                "profile": prof.id,
                "crawl_profile": prof.id,
                "list_url": list_url,
                "provider": "BCG",
                "capture": "http_smoke",
                "pdf_href": pdf_url,
            },
        )
        pages = pdf_page_count(dest)
        reports_store.mark_downloaded(
            source=SOURCE,
            source_key=item.source_key,
            title=item.title,
            published_at=published,
            page_count=pages,
            file_path=str(dest),
            file_name=dest.name,
            attrs={
                "url": item.url,
                "catalog": "us",
                "profile": prof.id,
                "crawl_profile": prof.id,
                "list_url": list_url,
                "provider": "BCG",
                "capture": "http_smoke",
                "pdf_href": pdf_url,
                "bytes": nbytes,
            },
        )
        downloaded += 1
        print(
            f"OK downloaded={downloaded} key={item.source_key} "
            f"bytes={nbytes} pages={pages}"
        )

    if downloaded < 1:
        print("FAIL: no new item to download (all existing?)", file=sys.stderr)
        return 1
    print(f"smoke ok downloaded={downloaded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
