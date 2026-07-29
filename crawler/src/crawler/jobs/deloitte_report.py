"""Deloitte US Insights list-while-download job (template search + detail PDF)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from crawler import collection_jobs_store, reports_store
from crawler.asset_id import DOWNLOADS_ROOT, downloads_dir, make_asset_id
from crawler.jobs.media_pace import (
    DEFAULT_ITEM_DELAY_SECONDS,
    clamp_item_delay_seconds,
    pace_after_item,
)
from crawler.sources.deloitte_http import (
    DEFAULT_CATALOG,
    DeloitteListItem,
    SOURCE,
    download_pdf,
    fetch_detail_meta,
    fetch_list_page,
    get_catalog,
    make_session,
    months_ago_cutoff,
    pdf_page_count,
)

DEFAULT_PERIOD_MONTHS = 3
MIN_PERIOD_MONTHS = 1
MAX_PERIOD_MONTHS = 24
DEFAULT_MAX_PAGES = 20
MAX_MAX_PAGES = 50
STALE_PAGES_TO_STOP = 2


@dataclass
class DeloitteJobSummary:
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


def run_deloitte_search_job(
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
            message=f"source {source!r} is not deloitte",
        )

    try:
        cat = get_catalog(catalog)
    except ValueError as exc:
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message=str(exc),
        )

    period_months = max(
        MIN_PERIOD_MONTHS, min(int(period_months), MAX_PERIOD_MONTHS)
    )
    max_pages = max(1, min(int(max_pages), MAX_MAX_PAGES))
    item_delay_seconds = clamp_item_delay_seconds(item_delay_seconds)
    if limit is not None and limit < 1:
        limit = None

    asset_id = make_asset_id("deloitte")
    download_dir = downloads_dir(asset_id, root=download_root or DOWNLOADS_ROOT)
    download_dir.mkdir(parents=True, exist_ok=True)
    cutoff = months_ago_cutoff(period_months)
    already = reports_store.downloaded_keys(SOURCE)
    summary = DeloitteJobSummary()
    page_size = cat.page_size
    consecutive_stale = 0
    session = make_session()

    progress: dict[str, Any] = {
        "stage": "list_download",
        "source": SOURCE,
        "capability": "search",
        "catalog": cat.id,
        "catalog_label": cat.label,
        "query": cat.query,
        "period_months": period_months,
        "item_delay_seconds": item_delay_seconds,
        "cutoff": cutoff.isoformat(),
        "asset_id": asset_id,
        "page": 1,
        "page_size": page_size,
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
        f"deloitte search 시작 ({cat.label}, query={cat.query!r}, "
        f"최근 {period_months}개월, max_pages={max_pages}, "
        f"item_delay={item_delay_seconds}s)",
    )

    def stop() -> bool:
        return bool(collection_jobs_store.stop_requested(job_id))

    try:
        for page_idx in range(max_pages):
            if stop():
                summary.stopped = True
                break
            if limit is not None and len(summary.downloaded) >= limit:
                break

            page = page_idx + 1
            progress["stage"] = "list"
            progress["page"] = page
            collection_jobs_store.set_progress(job_id, progress)

            items, has_more = fetch_list_page(
                page, catalog=cat, session=session
            )
            if not items:
                progress["stop_reason"] = "empty_page"
                break

            in_period = 0
            for item in items:
                if stop():
                    summary.stopped = True
                    break
                if limit is not None and len(summary.downloaded) >= limit:
                    break

                outcome = _process_item(
                    item,
                    catalog_id=cat.id,
                    cutoff=cutoff,
                    summary=summary,
                    already=already,
                    download_dir=download_dir,
                    progress=progress,
                    job_id=job_id,
                    session=session,
                )
                if outcome != "old":
                    in_period += 1
                if stop():
                    summary.stopped = True
                    break
                pace_after_item(item_delay_seconds)

            summary.pages_done += 1
            progress["pages_done"] = summary.pages_done
            progress["listed"] = summary.listed
            progress["downloaded"] = len(summary.downloaded)
            collection_jobs_store.set_progress(job_id, progress)

            if summary.stopped:
                break
            if limit is not None and len(summary.downloaded) >= limit:
                progress["stop_reason"] = "limit"
                break

            if in_period == 0:
                consecutive_stale += 1
            else:
                consecutive_stale = 0
            if consecutive_stale >= STALE_PAGES_TO_STOP:
                progress["stop_reason"] = "period_exhausted"
                break
            if not has_more:
                progress["stop_reason"] = "end_of_list"
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


def _process_item(
    item: DeloitteListItem,
    *,
    catalog_id: str,
    cutoff,
    summary: DeloitteJobSummary,
    already: set[str],
    download_dir: Path,
    progress: dict[str, Any],
    job_id: UUID | str,
    session,
) -> str:
    """Return 'ok' | 'old' | 'skip' for paging heuristics."""
    attrs: dict[str, Any] = {
        "url": item.url,
        "catalog": catalog_id,
        "provider": "Deloitte",
    }
    if item.category:
        attrs["category"] = item.category
    published_at = item.published_at
    if published_at is not None:
        attrs["publish_date"] = published_at.isoformat()

    reports_store.upsert_listed(
        source=SOURCE,
        source_key=item.source_key,
        title=item.title,
        published_at=published_at,
        attrs=attrs,
    )
    summary.listed += 1
    progress["listed"] = summary.listed
    progress["current_title"] = item.title
    progress["current_url"] = item.url
    collection_jobs_store.set_progress(job_id, progress)

    if published_at is not None and published_at < cutoff:
        summary.skipped_old += 1
        progress["skipped_old"] = summary.skipped_old
        return "old"

    if item.source_key in already:
        summary.skipped_existing += 1
        progress["skipped_existing"] = summary.skipped_existing
        return "skip"

    try:
        pdf_url, detail_date = fetch_detail_meta(item.url, session=session)
    except Exception as exc:
        summary.failed += 1
        progress["failed"] = summary.failed
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_FAILED,
            attrs={**attrs, "error": f"detail_fetch: {exc}"},
        )
        return "skip"

    if detail_date is not None:
        published_at = detail_date
        attrs["publish_date"] = published_at.isoformat()
        reports_store.upsert_listed(
            source=SOURCE,
            source_key=item.source_key,
            title=item.title,
            published_at=published_at,
            attrs=attrs,
        )
        if published_at < cutoff:
            summary.skipped_old += 1
            progress["skipped_old"] = summary.skipped_old
            return "old"

    if not pdf_url:
        summary.skipped_no_download += 1
        progress["skipped_no_download"] = summary.skipped_no_download
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_NO_DOWNLOAD,
            attrs={**attrs, "no_pdf": True},
        )
        return "ok" if published_at else "skip"

    safe = _safe_filename(item.source_key)
    dest = download_dir / f"{safe}.pdf"
    try:
        size = download_pdf(pdf_url, dest, session=session)
        pages = pdf_page_count(dest)
        reports_store.mark_downloaded(
            source=SOURCE,
            source_key=item.source_key,
            title=item.title,
            published_at=published_at,
            page_count=pages,
            file_path=str(dest),
            file_name=dest.name,
            attrs={**attrs, "pdf_url": pdf_url, "bytes": size},
        )
        already.add(item.source_key)
        summary.downloaded.append(str(dest))
        progress["downloaded"] = len(summary.downloaded)
        progress["last_pdf"] = pdf_url
        return "ok" if published_at else "skip"
    except Exception as exc:
        summary.failed += 1
        progress["failed"] = summary.failed
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_FAILED,
            attrs={**attrs, "pdf_url": pdf_url, "error": f"download: {exc}"},
        )
        return "skip"


def _safe_filename(key: str) -> str:
    base = key.replace("/", "__")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:180] or "deloitte_report"
