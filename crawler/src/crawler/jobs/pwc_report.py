"""PwC list-while-download job (FnGuide-style: list and download in one pass)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from crawler import collection_jobs_store, reports_store
from crawler.asset_id import DOWNLOADS_ROOT, downloads_dir, make_asset_id
from crawler.sources.pwc_http import (
    PAGE_SIZE,
    PwcListItem,
    SOURCE,
    download_pdf,
    fetch_detail_pdf_url,
    fetch_list_page,
    months_ago_cutoff,
    pdf_page_count,
)

DEFAULT_PERIOD_MONTHS = 3
MIN_PERIOD_MONTHS = 1
MAX_PERIOD_MONTHS = 24
DEFAULT_MAX_PAGES = 20  # each "page" is PAGE_SIZE items
MAX_MAX_PAGES = 50


@dataclass
class PwcJobSummary:
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


def run_pwc_search_job(
    job_id: UUID | str,
    *,
    period_months: int = DEFAULT_PERIOD_MONTHS,
    max_pages: int = DEFAULT_MAX_PAGES,
    limit: int | None = None,
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
            message=f"source {source!r} is not pwc",
        )

    period_months = max(MIN_PERIOD_MONTHS, min(int(period_months), MAX_PERIOD_MONTHS))
    max_pages = max(1, min(int(max_pages), MAX_MAX_PAGES))
    if limit is not None and limit < 1:
        limit = None

    asset_id = make_asset_id("pwc")
    download_dir = downloads_dir(asset_id, root=download_root or DOWNLOADS_ROOT)
    download_dir.mkdir(parents=True, exist_ok=True)
    cutoff = months_ago_cutoff(period_months)
    already = reports_store.downloaded_keys(SOURCE)
    summary = PwcJobSummary()

    progress: dict[str, Any] = {
        "stage": "list_download",
        "source": SOURCE,
        "capability": "search",
        "period_months": period_months,
        "cutoff": cutoff.isoformat(),
        "asset_id": asset_id,
        "page_offset": 0,
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
        f"pwc search 시작 (최근 {period_months}개월, max_pages={max_pages})",
    )

    def stop() -> bool:
        return bool(collection_jobs_store.stop_requested(job_id))

    try:
        number_hits = 0
        for page_idx in range(max_pages):
            if stop():
                summary.stopped = True
                break
            if limit is not None and len(summary.downloaded) >= limit:
                break

            page_offset = page_idx * PAGE_SIZE
            progress["stage"] = "list"
            progress["page_offset"] = page_offset
            collection_jobs_store.set_progress(job_id, progress)

            items, number_hits = fetch_list_page(page_offset)
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
                    item,
                    summary=summary,
                    already=already,
                    download_dir=download_dir,
                    progress=progress,
                    job_id=job_id,
                )

            summary.pages_done += 1
            progress["pages_done"] = summary.pages_done
            progress["listed"] = summary.listed
            progress["downloaded"] = len(summary.downloaded)
            collection_jobs_store.set_progress(job_id, progress)

            # If every item on the page is older than cutoff, stop paging.
            if older_than_cutoff == len(items):
                progress["stop_reason"] = "period_cutoff"
                break
            if page_offset + len(items) >= number_hits:
                progress["stop_reason"] = "end_of_list"
                break

        if summary.stopped:
            progress["stop_reason"] = "manual"
        progress["stage"] = "done"
        progress["number_hits"] = number_hits
        collection_jobs_store.set_progress(job_id, progress)
        message = summary.as_message()
        return collection_jobs_store.end_job(
            job_id,
            error=False,
            message=message,
        )
    except Exception as exc:
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message=str(exc),
        )


def _process_item(
    item: PwcListItem,
    *,
    summary: PwcJobSummary,
    already: set[str],
    download_dir: Path,
    progress: dict[str, Any],
    job_id: UUID | str,
) -> None:
    attrs = {
        "url": item.url,
        "publish_date_raw": item.publish_date_raw,
        "tags": list(item.tags),
        "provider": "PwC",
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

    try:
        pdf_url = fetch_detail_pdf_url(item.url)
    except Exception as exc:
        summary.failed += 1
        progress["failed"] = summary.failed
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_FAILED,
            attrs={**attrs, "error": f"detail_fetch: {exc}"},
        )
        return

    if not pdf_url:
        summary.skipped_no_download += 1
        progress["skipped_no_download"] = summary.skipped_no_download
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_NO_DOWNLOAD,
            attrs={**attrs, "no_pdf": True},
        )
        return

    safe = _safe_filename(item.source_key)
    dest = download_dir / f"{safe}.pdf"
    try:
        size = download_pdf(pdf_url, dest)
        pages = pdf_page_count(dest)
        reports_store.mark_downloaded(
            source=SOURCE,
            source_key=item.source_key,
            title=item.title,
            published_at=item.published_at,
            page_count=pages,
            file_path=str(dest),
            file_name=dest.name,
            attrs={**attrs, "pdf_url": pdf_url, "bytes": size},
        )
        already.add(item.source_key)
        summary.downloaded.append(str(dest))
        progress["downloaded"] = len(summary.downloaded)
        progress["last_pdf"] = pdf_url
    except Exception as exc:
        summary.failed += 1
        progress["failed"] = summary.failed
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_FAILED,
            attrs={**attrs, "pdf_url": pdf_url, "error": f"download: {exc}"},
        )


def _safe_filename(key: str) -> str:
    base = key.replace("/", "__")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:180] or "pwc_report"
