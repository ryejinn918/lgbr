"""BCG theme-profile list-while-download (HTTP + page.pdf fallback)."""

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
from crawler.report_themes import REPORT_THEMES
from crawler.sources.bcg_http import (
    BcgBlockedError,
    BcgCaptureError,
    BcgListItem,
    DEFAULT_PROFILE,
    SOURCE,
    download_pdf,
    fetch_detail_meta,
    fetch_list_items,
    get_profile,
    is_allowlisted_list_url,
    is_publication_article_url,
    make_session,
    months_ago_cutoff,
    pdf_page_count,
)
from crawler.sources.page_pdf_capture import (
    LazyCaptureBrowser,
    process_no_pdf_with_page_capture,
)

DEFAULT_PERIOD_MONTHS = 3
MIN_PERIOD_MONTHS = 1
MAX_PERIOD_MONTHS = 24
DEFAULT_MAX_PAGES = 10
MAX_MAX_PAGES = 50
DEFAULT_CATALOG = "us"


@dataclass
class BcgJobSummary:
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


def run_bcg_search_job(
    job_id: UUID | str,
    *,
    catalog: str = DEFAULT_CATALOG,
    profile: str = DEFAULT_PROFILE,
    period_months: int | None = None,
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
            message=f"source {source!r} is not bcg",
        )

    try:
        prof = get_profile(profile)
    except ValueError as exc:
        return collection_jobs_store.end_job(
            job_id, error=True, message=str(exc)
        )

    catalog_id = (catalog or DEFAULT_CATALOG).strip().lower() or DEFAULT_CATALOG
    months = (
        prof.period_months
        if period_months is None
        else max(MIN_PERIOD_MONTHS, min(int(period_months), MAX_PERIOD_MONTHS))
    )
    max_pages = max(1, min(int(max_pages), MAX_MAX_PAGES))
    item_delay_seconds = clamp_item_delay_seconds(item_delay_seconds)
    if limit is not None and limit < 1:
        limit = None

    asset_id = make_asset_id("bcg")
    download_dir = downloads_dir(asset_id, root=download_root or DOWNLOADS_ROOT)
    download_dir.mkdir(parents=True, exist_ok=True)
    cutoff = months_ago_cutoff(months)
    already = reports_store.downloaded_keys(SOURCE)
    summary = BcgJobSummary()
    seen_keys: set[str] = set()
    session = make_session()

    progress: dict[str, Any] = {
        "stage": "list_download",
        "source": SOURCE,
        "capability": "search",
        "catalog": catalog_id,
        "profile": prof.id,
        "profile_label": prof.label,
        "period_months": months,
        "item_delay_seconds": item_delay_seconds,
        "cutoff": cutoff.isoformat(),
        "asset_id": asset_id,
        "list_urls": list(prof.list_urls),
        "transport": "http",
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
        f"bcg search 시작 (HTTP, profile={prof.id}, 최근 {months}개월, "
        f"max_pages={max_pages}, item_delay={item_delay_seconds}s)",
    )

    def stop() -> bool:
        return bool(collection_jobs_store.stop_requested(job_id))

    # max_pages caps how many allowlisted list_urls we visit (one HTTP GET each).
    list_urls = list(prof.list_urls)[:max_pages]
    capture = LazyCaptureBrowser(SOURCE, downloads_path=download_dir)
    try:
        for list_url in list_urls:
            if stop():
                summary.stopped = True
                break
            if limit is not None and len(summary.downloaded) >= limit:
                break
            if not is_allowlisted_list_url(list_url, prof):
                summary.failed += 1
                progress["failed"] = summary.failed
                progress["stop_reason"] = f"list_url not allowlisted: {list_url}"
                collection_jobs_store.set_progress(job_id, progress)
                break

            progress["list_url"] = list_url
            progress["stage"] = "list"
            collection_jobs_store.set_progress(job_id, progress)

            try:
                items = fetch_list_items(
                    list_url, profile=prof, session=session
                )
            except BcgBlockedError as exc:
                progress["stop_reason"] = f"blocked: {exc}"
                collection_jobs_store.set_progress(job_id, progress)
                return collection_jobs_store.end_job(
                    job_id, error=True, message=str(exc)
                )
            except Exception as exc:
                summary.failed += 1
                progress["failed"] = summary.failed
                progress["stop_reason"] = f"list_error: {exc}"
                collection_jobs_store.set_progress(job_id, progress)
                break

            new_items = [
                it
                for it in items
                if it.source_key not in seen_keys
                and is_publication_article_url(it.url)
            ]
            for it in new_items:
                seen_keys.add(it.source_key)

            if not new_items:
                progress["stop_reason"] = "empty_page"
                summary.pages_done += 1
                progress["pages_done"] = summary.pages_done
                collection_jobs_store.set_progress(job_id, progress)
                continue

            older_than_cutoff = 0
            dated_on_batch = 0
            for item in new_items:
                if stop():
                    summary.stopped = True
                    break
                if limit is not None and len(summary.downloaded) >= limit:
                    break

                outcome = _process_item(
                    item,
                    catalog_id=catalog_id,
                    profile_id=prof.id,
                    list_url=list_url,
                    cutoff=cutoff,
                    summary=summary,
                    already=already,
                    download_dir=download_dir,
                    progress=progress,
                    job_id=job_id,
                    session=session,
                    capture=capture,
                )
                if outcome == "old":
                    older_than_cutoff += 1
                    if item.published_at:
                        dated_on_batch += 1
                elif item.published_at:
                    dated_on_batch += 1
                if stop():
                    summary.stopped = True
                    break
                pace_after_item(item_delay_seconds)

            summary.pages_done += 1
            progress["pages_done"] = summary.pages_done
            progress["listed"] = summary.listed
            progress["downloaded"] = len(summary.downloaded)
            collection_jobs_store.set_progress(job_id, progress)

            if dated_on_batch and older_than_cutoff == dated_on_batch:
                progress["stop_reason"] = "period_cutoff"
                break

        if summary.stopped:
            progress["stop_reason"] = "manual"
        elif limit is not None and len(summary.downloaded) >= limit:
            progress["stop_reason"] = "limit"
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
        capture.close()


def _process_item(
    item: BcgListItem,
    *,
    catalog_id: str,
    profile_id: str,
    list_url: str,
    cutoff,
    summary: BcgJobSummary,
    already: set[str],
    download_dir: Path,
    progress: dict[str, Any],
    job_id: UUID | str,
    session,
    capture: LazyCaptureBrowser,
) -> str:
    """Return 'ok' | 'old' | 'skip' for paging heuristics."""
    attrs: dict[str, Any] = {
        "url": item.url,
        "catalog": catalog_id,
        "profile": profile_id,
        "crawl_profile": profile_id,
        "list_url": list_url,
        "publish_date_raw": item.publish_date_raw,
        "provider": "BCG",
        "transport": "http",
    }
    if profile_id in REPORT_THEMES:
        attrs["themes"] = [profile_id]

    if item.source_key in already:
        summary.skipped_existing += 1
        progress["skipped_existing"] = summary.skipped_existing
        progress["current_title"] = item.title
        progress["current_url"] = item.url
        collection_jobs_store.set_progress(job_id, progress)
        return "skip"

    published_at = item.published_at
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

    try:
        pdf_url, detail_date = fetch_detail_meta(
            item.url, session=session, referer=list_url
        )
    except BcgBlockedError as exc:
        summary.skipped_no_download += 1
        progress["skipped_no_download"] = summary.skipped_no_download
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_NO_DOWNLOAD,
            attrs={**attrs, "error": str(exc)},
        )
        return "skip"
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

    if published_at is not None and published_at < cutoff:
        summary.skipped_old += 1
        progress["skipped_old"] = summary.skipped_old
        reports_store.upsert_listed(
            source=SOURCE,
            source_key=item.source_key,
            title=item.title,
            published_at=published_at,
            attrs={**attrs, "skipped": "period_cutoff_detail"},
        )
        return "old"

    safe = _safe_filename(item.source_key)
    dest = download_dir / f"{safe}.pdf"
    if not pdf_url:
        process_no_pdf_with_page_capture(
            capture=capture,
            source=SOURCE,
            source_key=item.source_key,
            title=item.title,
            published_at=published_at,
            url=item.url,
            dest=dest,
            attrs=attrs,
            already=already,
            summary=summary,
            progress=progress,
        )
        return "ok" if published_at else "skip"

    try:
        size = download_pdf(
            pdf_url, dest, session=session, referer=item.url
        )
        pages = pdf_page_count(dest)
        reports_store.mark_downloaded(
            source=SOURCE,
            source_key=item.source_key,
            title=item.title,
            published_at=published_at,
            page_count=pages,
            file_path=str(dest),
            file_name=dest.name,
            attrs={
                **attrs,
                "pdf_href": pdf_url,
                "bytes": size,
                "capture": "http",
            },
        )
        already.add(item.source_key)
        summary.downloaded.append(str(dest))
        progress["downloaded"] = len(summary.downloaded)
        progress["last_pdf"] = pdf_url
        progress["capture"] = "http"
        return "ok" if published_at else "skip"
    except BcgBlockedError as exc:
        summary.skipped_no_download += 1
        progress["skipped_no_download"] = summary.skipped_no_download
        if dest.is_file():
            dest.unlink(missing_ok=True)
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_NO_DOWNLOAD,
            attrs={**attrs, "pdf_href": pdf_url, "error": str(exc)},
        )
        return "skip"
    except (BcgCaptureError, Exception) as exc:
        summary.failed += 1
        progress["failed"] = summary.failed
        if dest.is_file():
            dest.unlink(missing_ok=True)
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_FAILED,
            attrs={**attrs, "pdf_href": pdf_url, "error": f"download: {exc}"},
        )
        return "skip"


def _safe_filename(key: str) -> str:
    base = key.replace("/", "__")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:180] or "bcg_report"
