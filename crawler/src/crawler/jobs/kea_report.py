"""KEA issue-report list and PDF download job."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from crawler import collection_jobs_store, reports_store
from crawler.asset_id import DOWNLOADS_ROOT, downloads_dir, make_asset_id
from crawler.jobs.media_pace import clamp_item_delay_seconds, pace_after_item
from crawler.sources.kea_http import (
    BASE,
    LIST_URL,
    SOURCE,
    download_pdf,
    fetch_detail_pdf_url,
    fetch_list_page,
    make_session,
)


def run_kea_search_job(
    job_id: UUID | str,
    *,
    catalog: str = "kr",
    period_months: int = 6,
    max_pages: int = 5,
    limit: int | None = None,
    item_delay_seconds: float = 2.0,
    download_root: Path | None = None,
) -> dict[str, Any]:
    del catalog
    period_months = max(1, min(int(period_months), 24))
    cutoff = date.today() - timedelta(days=period_months * 31)
    job = collection_jobs_store.claim_job(job_id)
    if str(job.get("source") or "") != SOURCE:
        return collection_jobs_store.end_job(job_id, error=True, message="source must be kea")
    if str(job.get("capability") or "") != "search":
        return collection_jobs_store.end_job(job_id, error=True, message="expected capability=search")

    asset_id = make_asset_id(SOURCE)
    download_dir = downloads_dir(asset_id, root=download_root or DOWNLOADS_ROOT)
    download_dir.mkdir(parents=True, exist_ok=True)
    already = reports_store.downloaded_keys(SOURCE)
    session = make_session(referer=LIST_URL, origin=BASE)
    delay = clamp_item_delay_seconds(item_delay_seconds)
    listed = downloaded = failed = 0
    try:
        for page in range(1, max(1, min(int(max_pages), 20)) + 1):
            if collection_jobs_store.stop_requested(job_id):
                break
            items = fetch_list_page(page, session=session)
            if not items:
                break
            for item in items:
                if collection_jobs_store.stop_requested(job_id):
                    break
                attrs = {
                    "provider": "KEA",
                    "themes": ["appliance", "display"],
                    "source_url": item.detail_url,
                }
                reports_store.upsert_listed(
                    source=SOURCE,
                    source_key=item.source_key,
                    title=item.title,
                    published_at=item.published_at,
                    status=reports_store.STATUS_LISTED,
                    attrs=attrs,
                )
                if item.published_at is not None and item.published_at < cutoff:
                    continue
                listed += 1
                if item.source_key in already:
                    continue
                try:
                    pdf_url = fetch_detail_pdf_url(item, session=session)
                    if not pdf_url:
                        continue
                    payload = download_pdf(session, pdf_url)
                    if not payload.startswith(b"%PDF"):
                        continue
                    path = download_dir / f"{item.source_key}.pdf"
                    path.write_bytes(payload)
                    reports_store.mark_downloaded(
                        source=SOURCE,
                        source_key=item.source_key,
                        title=item.title,
                        published_at=item.published_at,
                        file_path=str(path),
                        file_name=path.name,
                        attrs={**attrs, "pdf_url": pdf_url},
                    )
                    downloaded += 1
                except Exception:
                    failed += 1
                pace_after_item(delay)
                if limit is not None and downloaded >= limit:
                    break
            if limit is not None and downloaded >= limit:
                break
        return collection_jobs_store.end_job(
            job_id,
            error=False,
            message=f"downloaded={downloaded} listed={listed} failed={failed}",
        )
    except Exception as exc:
        return collection_jobs_store.end_job(job_id, error=True, message=str(exc))
