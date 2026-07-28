"""Run a list-expansion feed job (no body fill)."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from crawler import collection_jobs_store, news_articles_store
from crawler.sources import FEED_ALLOWLIST
from crawler.sources import arg_feed

DEFAULT_MAX_PAGES = 50
DEFAULT_LIST_PER_PAGE = 20
DEFAULT_PERIOD_MONTHS = 3
MIN_PERIOD_MONTHS = 1
MAX_PERIOD_MONTHS = 24


def _months_ago_utc(months: int, *, now: datetime | None = None) -> datetime:
    """Return UTC timestamp ``months`` calendar months before ``now``."""
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    else:
        ref = ref.astimezone(timezone.utc)
    y, m = ref.year, ref.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    day = min(ref.day, monthrange(y, m)[1])
    return ref.replace(year=y, month=m, day=day)


def run_feed_job(
    job_id: UUID | str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    period_months: int = DEFAULT_PERIOD_MONTHS,
) -> dict[str, Any]:
    job = collection_jobs_store.claim_job(job_id)
    source = str(job.get("source") or "")
    capability = str(job.get("capability") or "")
    if capability != "feed":
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message=f"expected capability=feed, got {capability!r}",
        )
    if source not in FEED_ALLOWLIST:
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message=f"source {source!r} is not in feed allowlist",
        )

    max_pages = max(1, min(int(max_pages), 200))
    period_months = max(
        MIN_PERIOD_MONTHS, min(int(period_months), MAX_PERIOD_MONTHS)
    )
    progress: dict[str, Any] = {
        "stage": "list_expand",
        "source": source,
        "capability": "feed",
        "page": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "pages_done": 0,
        "period_months": period_months,
    }
    collection_jobs_store.set_progress(job_id, progress)
    collection_jobs_store.set_message(
        job_id, f"{source} feed 목록 확장 시작 (최근 {period_months}개월)"
    )

    try:
        if source == "arg":
            result = _run_arg_feed(
                job_id,
                max_pages=max_pages,
                period_months=period_months,
                progress=progress,
            )
        else:
            return collection_jobs_store.end_job(
                job_id,
                error=True,
                message=f"no feed adapter for source={source!r}",
                progress=progress,
            )
    except Exception as exc:
        progress["error"] = str(exc)
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message=str(exc),
            progress=progress,
        )

    if collection_jobs_store.stop_requested(job_id):
        return collection_jobs_store.end_job(
            job_id,
            message="사용자 중단",
            progress=result,
        )
    return collection_jobs_store.end_job(
        job_id,
        message=result.get("message") or "목록 확장 완료",
        progress=result,
    )


def _run_arg_feed(
    job_id: UUID | str,
    *,
    max_pages: int,
    period_months: int,
    progress: dict[str, Any],
) -> dict[str, Any]:
    inserted = updated = skipped = 0
    pages_done = 0
    stop_reason = "max_pages"
    cutoff = _months_ago_utc(period_months)
    progress["cutoff"] = cutoff.isoformat()
    collection_jobs_store.set_progress(job_id, progress)

    with httpx.Client(
        timeout=30.0,
        headers={
            "User-Agent": "lgbr-feed/0.1 (+local; list-meta only)",
            "Accept": "application/json",
            "Referer": arg_feed.LIST_URL,
            "X-Requested-With": "XMLHttpRequest",
        },
    ) as client:
        for page in range(1, max_pages + 1):
            if collection_jobs_store.stop_requested(job_id):
                stop_reason = "stop_requested"
                break

            progress.update(
                {
                    "stage": "list_expand",
                    "page": page,
                    "inserted": inserted,
                    "updated": updated,
                    "skipped": skipped,
                    "pages_done": pages_done,
                    "period_months": period_months,
                    "cutoff": cutoff.isoformat(),
                }
            )
            collection_jobs_store.set_progress(job_id, progress)
            collection_jobs_store.set_message(
                job_id,
                f"ARG feed page {page}/{max_pages} · 최근 {period_months}개월",
            )

            items = arg_feed.fetch_page(
                page,
                client=client,
                list_per_page=DEFAULT_LIST_PER_PAGE,
            )
            if not items:
                stop_reason = "empty_page"
                break

            page_new = 0
            hit_cutoff = False
            for item in items:
                if collection_jobs_store.stop_requested(job_id):
                    stop_reason = "stop_requested"
                    break
                if (
                    item.published_at is not None
                    and item.published_at < cutoff
                ):
                    hit_cutoff = True
                    continue
                attrs = {}
                if item.section:
                    attrs["section"] = item.section
                outcome = news_articles_store.upsert_list_item(
                    source=arg_feed.SOURCE,
                    source_key=item.source_key,
                    title=item.title,
                    url=item.url,
                    published_at=item.published_at,
                    publisher=item.publisher,
                    attrs=attrs or None,
                )
                if outcome == "inserted":
                    inserted += 1
                    page_new += 1
                elif outcome == "updated":
                    updated += 1
                else:
                    skipped += 1

            pages_done += 1
            progress.update(
                {
                    "page": page,
                    "inserted": inserted,
                    "updated": updated,
                    "skipped": skipped,
                    "pages_done": pages_done,
                    "page_new": page_new,
                    "period_months": period_months,
                    "cutoff": cutoff.isoformat(),
                }
            )
            collection_jobs_store.set_progress(job_id, progress)

            if stop_reason == "stop_requested":
                break
            if hit_cutoff:
                stop_reason = "older_than_period"
                break

    message = {
        "older_than_period": f"최근 {period_months}개월 구간 도달",
        "empty_page": "빈 페이지 — 중단",
        "stop_requested": "사용자 중단",
        "max_pages": f"최대 페이지 {max_pages} 도달",
    }.get(stop_reason, stop_reason)

    progress.update(
        {
            "stage": "done",
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "pages_done": pages_done,
            "period_months": period_months,
            "cutoff": cutoff.isoformat(),
            "stop_reason": stop_reason,
            "message": message,
        }
    )
    return progress
