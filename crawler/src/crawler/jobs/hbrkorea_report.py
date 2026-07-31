"""HBR Korea list-while-download job (login + Playwright page.pdf)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from crawler import collection_jobs_store, reports_store
from crawler.asset_id import DOWNLOADS_ROOT, downloads_dir, make_asset_id
from crawler.hbrkorea_session import HbrKoreaSession
from crawler.jobs.media_pace import (
    DEFAULT_ITEM_DELAY_SECONDS,
    clamp_item_delay_seconds,
    pace_after_item,
)
from crawler.paths import browser_profile_dir
from crawler.sources.hbrkorea_browser import (
    HbrListItem,
    SOURCE,
    capture_article_pdf,
    fetch_list_page,
    months_ago_cutoff,
    pdf_page_count,
)

DEFAULT_PERIOD_MONTHS = 3
MIN_PERIOD_MONTHS = 1
MAX_PERIOD_MONTHS = 24
DEFAULT_MAX_PAGES = 10
MAX_MAX_PAGES = 50
DEFAULT_CATALOG = "kr"
SEARCH_PROFILE = browser_profile_dir("browser-profile-hbrkorea-search")


@dataclass
class HbrJobSummary:
    listed: int = 0
    downloaded: list[str] = field(default_factory=list)
    skipped_existing: int = 0
    skipped_no_download: int = 0
    skipped_old: int = 0
    failed: int = 0
    pages_done: int = 0
    stopped: bool = False

    def as_message(self) -> str:
        return (
            f"downloaded={len(self.downloaded)} listed={self.listed} "
            f"existing={self.skipped_existing} no_dl={self.skipped_no_download} "
            f"old={self.skipped_old} failed={self.failed} pages={self.pages_done}"
        )


def run_hbrkorea_search_job(
    job_id: UUID | str,
    *,
    catalog: str = DEFAULT_CATALOG,
    period_months: int = DEFAULT_PERIOD_MONTHS,
    max_pages: int = DEFAULT_MAX_PAGES,
    limit: int | None = None,
    item_delay_seconds: float = DEFAULT_ITEM_DELAY_SECONDS,
    download_root: Path | None = None,
) -> dict[str, Any]:
    job = collection_jobs_store.claim_job(job_id)
    source = str(job.get("source") or "")
    capability = str(job.get("capability") or "")
    if capability != "search":
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message=f"expected capability=search, got {capability!r}",
        )
    if source != SOURCE:
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message=f"source {source!r} is not hbrkorea",
        )

    catalog_id = (catalog or DEFAULT_CATALOG).strip().lower() or DEFAULT_CATALOG
    period_months = max(MIN_PERIOD_MONTHS, min(int(period_months), MAX_PERIOD_MONTHS))
    max_pages = max(1, min(int(max_pages), MAX_MAX_PAGES))
    item_delay_seconds = clamp_item_delay_seconds(item_delay_seconds)
    if limit is not None and limit < 1:
        limit = None

    user_id = (os.environ.get("HBRKOREA_USER_ID") or "").strip()
    password = (os.environ.get("HBRKOREA_PASSWORD") or "").strip()
    if not user_id or not password:
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message="HBRKOREA_USER_ID/HBRKOREA_PASSWORD required",
        )

    asset_id = make_asset_id("hbrkorea")
    download_dir = downloads_dir(asset_id, root=download_root or DOWNLOADS_ROOT)
    download_dir.mkdir(parents=True, exist_ok=True)
    cutoff = months_ago_cutoff(period_months)
    already = reports_store.downloaded_keys(SOURCE)
    summary = HbrJobSummary()

    progress: dict[str, Any] = {
        "stage": "login",
        "source": SOURCE,
        "capability": "search",
        "catalog": catalog_id,
        "period_months": period_months,
        "item_delay_seconds": item_delay_seconds,
        "cutoff": cutoff.isoformat(),
        "asset_id": asset_id,
        "listed": 0,
        "downloaded": 0,
        "skipped_existing": 0,
        "skipped_no_download": 0,
        "skipped_old": 0,
        "failed": 0,
        "pages_done": 0,
    }
    collection_jobs_store.set_progress(job_id, progress)
    collection_jobs_store.set_message(
        job_id,
        f"hbrkorea search 시작 (최근 {period_months}개월, "
        f"max_pages={max_pages}, item_delay={item_delay_seconds}s)",
    )

    def stop() -> bool:
        return bool(collection_jobs_store.stop_requested(job_id))

    session = HbrKoreaSession(
        user_id=user_id,
        password=password,
        headless=True,
        force_other_session=True,
        profile_dir=SEARCH_PROFILE,
        downloads_path=download_dir,
    )

    try:
        session.start()
        page = session.page
        if page is None:
            raise RuntimeError("browser page missing after login")

        progress["stage"] = "list_download"
        collection_jobs_store.set_progress(job_id, progress)

        for page_num in range(1, max_pages + 1):
            if stop():
                summary.stopped = True
                break
            if limit is not None and len(summary.downloaded) >= limit:
                break

            progress["stage"] = "list"
            progress["page_num"] = page_num
            collection_jobs_store.set_progress(job_id, progress)
            session.touch(step=f"list_page_{page_num}")

            try:
                items = fetch_list_page(page, page_num)
            except Exception as exc:
                summary.failed += 1
                progress["failed"] = summary.failed
                progress["stop_reason"] = f"list_error: {exc}"
                collection_jobs_store.set_progress(job_id, progress)
                break

            if not items:
                progress["stop_reason"] = "empty_page"
                break

            older_than_cutoff = 0
            for item in items:
                if stop():
                    summary.stopped = True
                    break
                if limit is not None and len(summary.downloaded) >= limit:
                    break

                if item.published_at and item.published_at < cutoff:
                    summary.skipped_old += 1
                    older_than_cutoff += 1
                    progress["skipped_old"] = summary.skipped_old
                    continue

                _process_item(
                    page,
                    item,
                    catalog_id=catalog_id,
                    summary=summary,
                    already=already,
                    download_dir=download_dir,
                    progress=progress,
                    job_id=job_id,
                )
                session.touch(step=f"item_{item.source_key}")
                pace_after_item(item_delay_seconds)

            summary.pages_done += 1
            progress["pages_done"] = summary.pages_done
            progress["listed"] = summary.listed
            progress["downloaded"] = len(summary.downloaded)
            collection_jobs_store.set_progress(job_id, progress)

            if older_than_cutoff == len(items):
                progress["stop_reason"] = "period_cutoff"
                break

        if summary.stopped:
            progress["stop_reason"] = "manual"
        progress["stage"] = "done"
        collection_jobs_store.set_progress(job_id, progress)
        return collection_jobs_store.end_job(
            job_id,
            error=False,
            message=summary.as_message(),
        )
    except Exception as exc:
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message=str(exc),
        )
    finally:
        try:
            if session.session_id:
                session.stop("shutdown")
        except Exception:
            pass


def _process_item(
    page,
    item: HbrListItem,
    *,
    catalog_id: str,
    summary: HbrJobSummary,
    already: set[str],
    download_dir: Path,
    progress: dict[str, Any],
    job_id: UUID | str,
) -> None:
    attrs: dict[str, Any] = {
        "url": item.url,
        "catalog": catalog_id,
        "publish_date_raw": item.publish_date_raw,
        "post_type": item.post_type,
        "article_no": item.article_no,
        "atype": item.atype,
        "provider": "HBR Korea",
        "capture": "page.pdf",
    }
    reports_store.upsert_listed(
        source=SOURCE,
        source_key=item.source_key,
        title=item.title,
        published_at=item.published_at,
        attrs=attrs,
    )
    summary.listed += 1
    progress["listed"] = summary.listed
    progress["current_title"] = item.title
    progress["current_url"] = item.url
    collection_jobs_store.set_progress(job_id, progress)

    if item.source_key in already:
        summary.skipped_existing += 1
        progress["skipped_existing"] = summary.skipped_existing
        return

    safe = _safe_filename(item.source_key)
    dest = download_dir / f"{safe}.pdf"
    try:
        meta = capture_article_pdf(page, item.url, dest)
        pages = pdf_page_count(dest)
        reports_store.mark_downloaded(
            source=SOURCE,
            source_key=item.source_key,
            title=item.title,
            published_at=item.published_at,
            page_count=pages,
            file_path=str(dest),
            file_name=dest.name,
            attrs={**attrs, "bytes": meta.get("bytes"), "body_len": meta.get("body_len")},
        )
        already.add(item.source_key)
        summary.downloaded.append(str(dest))
        progress["downloaded"] = len(summary.downloaded)
        progress["last_pdf"] = str(dest)
    except Exception as exc:
        summary.failed += 1
        progress["failed"] = summary.failed
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_FAILED,
            attrs={**attrs, "error": f"capture: {exc}"},
        )


def _safe_filename(key: str) -> str:
    base = key.replace("/", "__")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:180] or "hbrkorea_report"
