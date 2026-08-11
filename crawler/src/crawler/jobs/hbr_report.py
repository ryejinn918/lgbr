"""HBR.org list-while-download (login browser, one URL at a time)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from crawler import collection_jobs_store, reports_store
from crawler.asset_id import DOWNLOADS_ROOT, downloads_dir, make_asset_id
from crawler.hbr_session import HbrSession
from crawler.jobs.media_pace import clamp_item_delay_seconds, pace_after_item
from crawler.paths import browser_profile_dir
from crawler.sources.hbr_browser import (
    KIND_BLIND,
    HbrBlockedError,
    HbrCaptureError,
    HbrListItem,
    SOURCE,
    capture_article_pdf,
    click_load_more,
    collect_list_items,
    months_ago_cutoff,
    open_latest,
    pdf_page_count,
)

DEFAULT_PERIOD_MONTHS = 3
MIN_PERIOD_MONTHS = 1
MAX_PERIOD_MONTHS = 24
DEFAULT_MAX_PAGES = 10
MAX_MAX_PAGES = 50
DEFAULT_CATALOG = "us"
DEFAULT_ITEM_DELAY_SECONDS = 5.0
SEARCH_PROFILE = browser_profile_dir("browser-profile-hbr-search")


@dataclass
class HbrJobSummary:
    listed: int = 0
    downloaded: list[str] = field(default_factory=list)
    skipped_existing: int = 0
    skipped_blind: int = 0
    skipped_no_download: int = 0
    skipped_old: int = 0
    failed: int = 0
    pages_done: int = 0
    stopped: bool = False

    def as_message(self) -> str:
        return (
            f"downloaded={len(self.downloaded)} listed={self.listed} "
            f"existing={self.skipped_existing} blind={self.skipped_blind} "
            f"no_dl={self.skipped_no_download} "
            f"old={self.skipped_old} failed={self.failed} pages={self.pages_done}"
        )


def run_hbr_search_job(
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
            message=f"source {source!r} is not hbr",
        )

    catalog_id = (catalog or DEFAULT_CATALOG).strip().lower() or DEFAULT_CATALOG
    period_months = max(MIN_PERIOD_MONTHS, min(int(period_months), MAX_PERIOD_MONTHS))
    max_pages = max(1, min(int(max_pages), MAX_MAX_PAGES))
    item_delay_seconds = clamp_item_delay_seconds(item_delay_seconds)
    if limit is not None and limit < 1:
        limit = None

    user_id = (os.environ.get("HBR_USER_ID") or "").strip()
    password = (os.environ.get("HBR_PASSWORD") or "").strip()
    if not user_id or not password:
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message="HBR_USER_ID/HBR_PASSWORD required",
        )

    asset_id = make_asset_id("hbr")
    download_dir = downloads_dir(asset_id, root=download_root or DOWNLOADS_ROOT)
    download_dir.mkdir(parents=True, exist_ok=True)
    cutoff = months_ago_cutoff(period_months)
    already = reports_store.downloaded_keys(SOURCE)
    summary = HbrJobSummary()
    seen_keys: set[str] = set()

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
        "skipped_blind": 0,
        "skipped_no_download": 0,
        "skipped_old": 0,
        "failed": 0,
        "pages_done": 0,
    }
    collection_jobs_store.set_progress(job_id, progress)
    collection_jobs_store.set_message(
        job_id,
        f"hbr search 시작 (최근 {period_months}개월, "
        f"max_pages={max_pages}, item_delay={item_delay_seconds}s)",
    )

    def stop() -> bool:
        return bool(collection_jobs_store.stop_requested(job_id))

    session = HbrSession(
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

        # Phase 1: expand Latest in place (no detail nav) until cutoff / no more.
        progress["stage"] = "list"
        collection_jobs_store.set_progress(job_id, progress)
        open_latest(page)
        pending: list[HbrListItem] = []
        hit_cutoff = False

        for page_num in range(1, max_pages + 1):
            if stop():
                summary.stopped = True
                break

            progress["stage"] = "list"
            progress["page_num"] = page_num
            collection_jobs_store.set_progress(job_id, progress)
            session.touch(step=f"list_page_{page_num}")

            try:
                items = collect_list_items(page)
            except Exception as exc:
                summary.failed += 1
                progress["failed"] = summary.failed
                progress["stop_reason"] = f"list_error: {exc}"
                collection_jobs_store.set_progress(job_id, progress)
                break

            new_items = [it for it in items if it.source_key not in seen_keys]
            for it in new_items:
                seen_keys.add(it.source_key)

            if page_num == 1 and not new_items:
                progress["stop_reason"] = "empty_page"
                break
            if page_num > 1 and not new_items:
                progress["stop_reason"] = "no_new_after_load_more"
                break

            older_than_cutoff = 0
            dated_on_batch = 0
            for item in new_items:
                # Card date preferred; URL month start only for cutoff heuristics.
                effective = item.published_at or item.url_ym
                if effective and effective < cutoff:
                    summary.skipped_old += 1
                    older_than_cutoff += 1
                    dated_on_batch += 1
                    progress["skipped_old"] = summary.skipped_old
                    # Do not persist URL day-1 as published_at.
                    attrs_old: dict[str, Any] = {
                        "url": item.url,
                        "catalog": catalog_id,
                        "publish_date_raw": item.publish_date_raw,
                        "provider": "HBR",
                        "skipped": "period_cutoff",
                    }
                    if item.url_ym is not None:
                        attrs_old["url_ym"] = item.url_ym.isoformat()
                    reports_store.upsert_listed(
                        source=SOURCE,
                        source_key=item.source_key,
                        title=item.title,
                        published_at=item.published_at,
                        attrs=attrs_old,
                    )
                    summary.listed += 1
                    progress["listed"] = summary.listed
                    continue
                if effective:
                    dated_on_batch += 1
                pending.append(item)

            summary.pages_done += 1
            progress["pages_done"] = summary.pages_done
            progress["pending"] = len(pending)
            collection_jobs_store.set_progress(job_id, progress)

            if dated_on_batch and older_than_cutoff == dated_on_batch:
                progress["stop_reason"] = "period_cutoff"
                hit_cutoff = True
                break

            progress["stage"] = "load_more"
            collection_jobs_store.set_progress(job_id, progress)
            if not click_load_more(page):
                progress["stop_reason"] = "no_load_more"
                break
            pace_after_item(min(item_delay_seconds, 3.0))

        if summary.stopped:
            progress["stop_reason"] = "manual"
            progress["stage"] = "done"
            collection_jobs_store.set_progress(job_id, progress)
            return collection_jobs_store.end_job(
                job_id,
                error=False,
                message=summary.as_message(),
            )

        # Phase 2: one-by-one page.pdf with item delay (skips existing).
        if limit is not None:
            pending = pending[:limit]
        progress["stage"] = "download"
        progress["pending"] = len(pending)
        collection_jobs_store.set_progress(job_id, progress)
        collection_jobs_store.set_message(
            job_id,
            f"hbr 목록 {len(pending)}건 확보"
            f"{' (cutoff)' if hit_cutoff else ''} → page.pdf 수집",
        )

        for item in pending:
            if stop():
                summary.stopped = True
                break
            if limit is not None and len(summary.downloaded) >= limit:
                break
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
    progress["current_title"] = item.title
    progress["current_url"] = item.url

    # Skip before upsert: stale list dates (or missing card dates) would
    # regress published_at via COALESCE over a good detail date.
    if item.source_key in already:
        summary.skipped_existing += 1
        progress["skipped_existing"] = summary.skipped_existing
        collection_jobs_store.set_progress(job_id, progress)
        return

    attrs: dict[str, Any] = {
        "url": item.url,
        "catalog": catalog_id,
        "publish_date_raw": item.publish_date_raw,
        "provider": "HBR",
    }
    if item.url_ym is not None:
        attrs["url_ym"] = item.url_ym.isoformat()
    published = item.published_at
    reports_store.upsert_listed(
        source=SOURCE,
        source_key=item.source_key,
        title=item.title,
        published_at=published,
        attrs=attrs,
    )
    summary.listed += 1
    progress["listed"] = summary.listed
    collection_jobs_store.set_progress(job_id, progress)

    safe = _safe_filename(item.source_key)
    dest = download_dir / f"{safe}.pdf"
    try:
        meta = capture_article_pdf(page, item.url, dest)
        title = str(meta.get("title") or "").strip() or item.title
        detail_pub = meta.get("published_at")
        detail_raw = str(meta.get("date_raw") or "").strip()
        # Detail page date beats sparse/missing list dates.
        if detail_pub is not None:
            published = detail_pub
            if detail_raw:
                attrs["publish_date_raw"] = detail_raw
        pages = pdf_page_count(dest)
        reports_store.mark_downloaded(
            source=SOURCE,
            source_key=item.source_key,
            title=title,
            published_at=published,
            page_count=pages,
            file_path=str(dest),
            file_name=dest.name,
            attrs={
                **attrs,
                "bytes": meta.get("bytes"),
                "body_len": meta.get("body_len"),
                "capture": meta.get("capture"),
            },
        )
        already.add(item.source_key)
        summary.downloaded.append(str(dest))
        progress["downloaded"] = len(summary.downloaded)
        progress["last_pdf"] = str(dest)
        progress["capture"] = meta.get("capture")
    except HbrBlockedError as exc:
        if dest.is_file():
            dest.unlink(missing_ok=True)
        detail_title = (exc.title or "").strip() or None
        # Paywall / entitlement gate → blind (본문제한), same role as FnGuide.
        if exc.kind == KIND_BLIND:
            summary.skipped_blind += 1
            progress["skipped_blind"] = summary.skipped_blind
            status = reports_store.STATUS_BLIND
        else:
            summary.skipped_no_download += 1
            progress["skipped_no_download"] = summary.skipped_no_download
            status = reports_store.STATUS_NO_DOWNLOAD
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=status,
            title=detail_title,
            attrs={
                **attrs,
                "error": str(exc),
                "blind": status == reports_store.STATUS_BLIND,
                "block_kind": exc.kind,
            },
        )
    except (HbrCaptureError, Exception) as exc:
        summary.failed += 1
        progress["failed"] = summary.failed
        if dest.is_file():
            dest.unlink(missing_ok=True)
        reports_store.mark_status(
            source=SOURCE,
            source_key=item.source_key,
            status=reports_store.STATUS_FAILED,
            attrs={**attrs, "error": f"capture: {exc}"},
        )


def _safe_filename(key: str) -> str:
    base = key.replace("/", "__")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:180] or "hbr_report"
