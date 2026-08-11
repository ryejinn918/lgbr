#!/usr/bin/env python3
"""Fill HBR reports for a publish cutoff using an open adhoc CDP session.

Requires: API-started HBR adhoc (`POST /api/crawl/start` mode=hbr) with CDP.
Does not change the search job — probes list surfaces and captures missing page.pdf.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]  # crawler/
sys.path.insert(0, str(ROOT / "src"))

from crawler import reports_store, sessions_store  # noqa: E402
from crawler.asset_id import DOWNLOADS_ROOT, downloads_dir, make_asset_id  # noqa: E402
from crawler.cdp import connect_cdp, resolve_cdp_endpoint  # noqa: E402
from crawler.jobs.media_pace import pace_after_item  # noqa: E402
from crawler.sources.hbr_browser import (  # noqa: E402
    HbrBlockedError,
    HbrCaptureError,
    HbrListItem,
    SOURCE,
    capture_article_pdf,
    click_load_more,
    collect_list_items,
    parse_article_url,
    parse_publish_date,
    pdf_page_count,
    source_key_from_url,
)


DEFAULT_CUTOFF = "2026-04-01"
OUT_DEFAULT = Path(".crawler/snapshots/hbr-fill-3m")


def _parse_cutoff(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def _summarize(items: list[HbrListItem]) -> dict[str, Any]:
    pubs = [i.published_at for i in items if i.published_at]
    return {
        "count": len(items),
        "min_pub": min(pubs).isoformat() if pubs else None,
        "max_pub": max(pubs).isoformat() if pubs else None,
    }


def _safe_filename(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", key).strip("-")[:180] or "item"


def _touch(crawl: dict[str, Any], page, step: str) -> None:
    sid = crawl.get("session_id")
    if not sid:
        return
    sessions_store.touch(sid, current_url=page.url, step=step)


def probe_and_collect(
    page,
    crawl: dict[str, Any],
    *,
    cutoff: date,
    out_dir: Path,
    item_delay: float,
    urls_file: Path | None,
    download: bool,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    findings: dict[str, Any] = {
        "cutoff": cutoff.isoformat(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "surfaces": [],
    }
    by_url: dict[str, HbrListItem] = {}

    def add_items(items: list[HbrListItem], surface: str, **extra: Any) -> None:
        for it in items:
            by_url[it.url] = it
        row = {"surface": surface, **_summarize(items), **extra}
        findings["surfaces"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    # 1) Latest + Load More
    page.goto("https://hbr.org/the-latest", wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2500)
    _touch(crawl, page, "fill:latest")
    expands = 0
    for _ in range(40):
        if not click_load_more(page):
            break
        expands += 1
        page.wait_for_timeout(2000)
        _touch(crawl, page, f"fill:load_more_{expands}")
    items = collect_list_items(page)
    page.screenshot(path=str(out_dir / "latest.png"), full_page=True)
    still = page.get_by_text(re.compile(r"^\s*Load More Items\s*$", re.I)).count()
    add_items(
        items,
        "the-latest",
        load_more_clicks=expands,
        load_more_still_present=still > 0,
    )

    # 2) Magazine + archive-toc months in window
    page.goto("https://hbr.org/magazine", wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2500)
    _touch(crawl, page, "fill:magazine")
    page.screenshot(path=str(out_dir / "magazine.png"), full_page=True)
    mag_items = collect_list_items(page)
    issue_links = page.evaluate(
        """() => {
          const out=[]; const seen=new Set();
          for (const a of document.querySelectorAll('a[href]')) {
            const h=(a.href||'').split('#')[0];
            if (/hbr\\.org\\/archive-toc\\//i.test(h)) {
              if (seen.has(h)) continue; seen.add(h);
              out.push(h);
            }
          }
          return out.slice(0, 30);
        }"""
    )
    add_items(mag_items, "magazine", issue_links=issue_links)
    findings["magazine_issue_links"] = issue_links

    archive_targets = list(issue_links or [])
    y, m = cutoff.year, cutoff.month
    # months from cutoff through current month
    now = date.today()
    while (y, m) <= (now.year, now.month):
        archive_targets.append(f"https://hbr.org/archive-toc/{y:04d}/{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    archive_targets = list(dict.fromkeys(archive_targets))[:12]
    archive_probes = []
    for url in archive_targets:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(2000)
        except Exception as exc:
            archive_probes.append({"url": url, "error": str(exc)[:200]})
            continue
        _touch(crawl, page, "fill:archive")
        its = collect_list_items(page)
        row = {
            "requested": url,
            "final_url": page.url,
            "title": page.title(),
            **_summarize(its),
        }
        archive_probes.append(row)
        for it in its:
            by_url[it.url] = it
        print(json.dumps(row, ensure_ascii=False), flush=True)
        slug = re.sub(r"[^a-z0-9]+", "-", page.url.split("hbr.org/")[-1])[:50]
        try:
            page.screenshot(path=str(out_dir / f"archive-{slug}.png"), full_page=True)
        except Exception:
            pass
    findings["archive_probes"] = archive_probes

    # 3) Topics from hub
    page.goto("https://hbr.org/", wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(1500)
    topic_links = page.evaluate(
        """() => {
          const out=[]; const seen=new Set();
          for (const a of document.querySelectorAll('a[href*="/topic/"]')) {
            const h=(a.href||'').split('#')[0];
            if (!/hbr\\.org\\/topic\\//i.test(h)) continue;
            if (seen.has(h)) continue; seen.add(h);
            out.push(h);
          }
          return out.slice(0, 8);
        }"""
    )
    findings["topic_links"] = topic_links
    topic_probes = []
    for url in topic_links or []:
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(2000)
        for _ in range(8):
            if not click_load_more(page):
                break
            page.wait_for_timeout(1500)
        its = collect_list_items(page)
        row = {"surface": url, **_summarize(its)}
        topic_probes.append(row)
        for it in its:
            by_url[it.url] = it
        print(json.dumps(row, ensure_ascii=False), flush=True)
        _touch(crawl, page, "fill:topic")
    findings["topic_probes"] = topic_probes

    # 4) Search queries for missing months
    search_probes = []
    for q in ("April 2026", "May 2026", "2026/04", "2026/05"):
        surl = "https://hbr.org/search?term=" + q.replace(" ", "+")
        try:
            page.goto(surl, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(2500)
        except Exception as exc:
            search_probes.append({"q": q, "error": str(exc)[:160]})
            continue
        its = collect_list_items(page)
        row = {"q": q, "url": page.url, **_summarize(its)}
        search_probes.append(row)
        for it in its:
            by_url[it.url] = it
        print(json.dumps(row, ensure_ascii=False), flush=True)
        _touch(crawl, page, "fill:search")
    findings["search_probes"] = search_probes

    # Optional URL file merge
    if urls_file and urls_file.is_file():
        raw = json.loads(urls_file.read_text())
        rows = raw if isinstance(raw, list) else raw.get("apr_may") or raw.get("all") or []
        for row in rows:
            url = str(row.get("url") or row).strip()
            if not url or url in by_url:
                continue
            parsed = parse_article_url(url)
            if not parsed:
                continue
            slug, url_ym = parsed
            pub_raw = str(row.get("pub") or "")
            by_url[url] = HbrListItem(
                source_key=slug,
                url=url,
                title=str(row.get("title") or slug),
                published_at=parse_publish_date(pub_raw),
                publish_date_raw=pub_raw,
                url_ym=url_ym,
            )

    months: dict[str, int] = {}
    for it in by_url.values():
        if it.published_at:
            key = it.published_at.isoformat()[:7]
            months[key] = months.get(key, 0) + 1
    findings["pub_months"] = dict(sorted(months.items()))
    findings["all_unique"] = len(by_url)

    in_window = [
        it
        for it in by_url.values()
        if it.published_at and it.published_at >= cutoff
    ]
    findings["in_window"] = len(in_window)
    findings["before_june"] = sum(
        1 for it in in_window if it.published_at and it.published_at < date(2026, 6, 1)
    )

    (out_dir / "findings.json").write_text(
        json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "candidate_urls.json").write_text(
        json.dumps(
            [
                {
                    "url": it.url,
                    "title": it.title,
                    "pub": it.published_at.isoformat() if it.published_at else None,
                    "source_key": it.source_key,
                }
                for it in sorted(
                    in_window,
                    key=lambda x: x.published_at or date.max,
                )
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result: dict[str, Any] = {
        "findings": findings,
        "downloaded": 0,
        "skipped_existing": 0,
        "skipped_old": 0,
        "no_download": 0,
        "failed": 0,
    }
    if not download:
        return result

    already = reports_store.downloaded_keys(SOURCE)
    asset_id = make_asset_id("hbr")
    download_dir = downloads_dir(asset_id, root=DOWNLOADS_ROOT)
    download_dir.mkdir(parents=True, exist_ok=True)
    result["asset_id"] = asset_id

    # Prefer missing months first, then rest of window
    ordered = sorted(
        in_window,
        key=lambda it: (
            0 if (it.published_at and it.published_at < date(2026, 6, 1)) else 1,
            it.published_at or date.max,
            it.url,
        ),
    )

    for it in ordered:
        if it.published_at and it.published_at < cutoff:
            result["skipped_old"] += 1
            continue
        key = it.source_key or source_key_from_url(it.url)
        attrs: dict[str, Any] = {
            "url": it.url,
            "catalog": "us",
            "publish_date_raw": it.publish_date_raw,
            "provider": "HBR",
            "fill": "adhoc_period",
        }
        reports_store.upsert_listed(
            source=SOURCE,
            source_key=key,
            title=it.title,
            published_at=it.published_at,
            attrs=attrs,
        )
        if key in already:
            result["skipped_existing"] += 1
            continue
        dest = download_dir / f"{_safe_filename(key)}.pdf"
        try:
            meta = capture_article_pdf(page, it.url, dest)
            title = str(meta.get("title") or "").strip() or it.title
            published = meta.get("published_at") or it.published_at
            detail_raw = str(meta.get("date_raw") or "").strip()
            if detail_raw:
                attrs["publish_date_raw"] = detail_raw
            pages = pdf_page_count(dest)
            reports_store.mark_downloaded(
                source=SOURCE,
                source_key=key,
                title=title,
                published_at=published,
                file_path=str(dest),
                page_count=pages,
                attrs={**attrs, "capture": "page.pdf", "asset_id": asset_id},
            )
            already.add(key)
            result["downloaded"] += 1
            print(
                f"downloaded {result['downloaded']} {published} {title[:70]}",
                flush=True,
            )
        except HbrBlockedError as exc:
            reports_store.mark_status(
                source=SOURCE,
                source_key=key,
                status="no_download",
                attrs={**attrs, "error": str(exc)[:300]},
                clear_download=True,
            )
            result["no_download"] += 1
            print(f"no_download {it.url}: {exc}", flush=True)
        except (HbrCaptureError, Exception) as exc:
            reports_store.mark_status(
                source=SOURCE,
                source_key=key,
                status="failed",
                attrs={**attrs, "error": str(exc)[:300]},
            )
            result["failed"] += 1
            print(f"failed {it.url}: {exc}", flush=True)
        _touch(crawl, page, f"fill:item_{key}")
        pace_after_item(item_delay)

    findings["fill_result"] = {
        k: result[k]
        for k in (
            "downloaded",
            "skipped_existing",
            "skipped_old",
            "no_download",
            "failed",
            "asset_id",
        )
        if k in result
    }
    (out_dir / "findings.json").write_text(
        json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cutoff", default=DEFAULT_CUTOFF)
    ap.add_argument("--item-delay-seconds", type=float, default=3.0)
    ap.add_argument("--out-dir", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--urls-file", type=Path, default=None)
    ap.add_argument(
        "--probe-only",
        action="store_true",
        help="Only discover lists; do not download",
    )
    args = ap.parse_args()
    cutoff = _parse_cutoff(args.cutoff)

    crawl, endpoint = resolve_cdp_endpoint()
    print(
        json.dumps(
            {
                "crawl_id": crawl.get("id"),
                "mode": crawl.get("mode"),
                "endpoint": endpoint,
                "cutoff": cutoff.isoformat(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    with connect_cdp() as (crawl, _browser, page):
        result = probe_and_collect(
            page,
            crawl,
            cutoff=cutoff,
            out_dir=args.out_dir,
            item_delay=args.item_delay_seconds,
            urls_file=args.urls_file,
            download=not args.probe_only,
        )
    print(json.dumps({"ok": True, **{k: result[k] for k in result if k != "findings"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
