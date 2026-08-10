"""Run a list-expansion feed job (no body fill)."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from crawler import collection_jobs_store, news_articles_store
from crawler.sources import FEED_ALLOWLIST
from crawler.sources import arg_feed
from crawler.sources import nikkei_feed
from crawler.sources.arg_http import make_session
from crawler.sources.nikkei_sections import DEFAULT_SECTION, get_section, section_ids

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
    section: str | None = None,
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
    section_id = (section or DEFAULT_SECTION).strip().lower() or DEFAULT_SECTION
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
    if source == "nikkei":
        progress["section"] = section_id
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
        elif source == "nikkei":
            result = _run_nikkei_feed(
                job_id,
                section=section_id,
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

    client = make_session(accept="application/json")
    try:
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
    finally:
        client.close()

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


def _run_nikkei_feed(
    job_id: UUID | str,
    *,
    section: str,
    period_months: int,
    progress: dict[str, Any],
) -> dict[str, Any]:
    try:
        sec = get_section(section)
    except ValueError as exc:
        progress["stop_reason"] = "bad_section"
        progress["message"] = str(exc)
        progress["known_sections"] = sorted(section_ids())
        raise

    inserted = updated = skipped = 0
    cutoff = _months_ago_utc(period_months)
    progress.update(
        {
            "stage": "list_expand",
            "section": sec.id,
            "section_label": sec.label,
            "rss_url": sec.rss_url,
            "category_url": sec.category_url,
            "cutoff": cutoff.isoformat(),
            "period_months": period_months,
            "rss_fetched": False,
            "html_fetched": False,
            "listed": 0,
        }
    )
    collection_jobs_store.set_progress(job_id, progress)
    collection_jobs_store.set_message(
        job_id,
        f"Nikkei feed · {sec.label} ({sec.id}) · 최근 {period_months}개월",
    )

    if collection_jobs_store.stop_requested(job_id):
        progress.update(
            {
                "stage": "done",
                "stop_reason": "stop_requested",
                "message": "사용자 중단",
            }
        )
        return progress

    packed = nikkei_feed.fetch_section_items(sec.id, include_category_html=True)
    items = packed["items"]
    progress.update(
        {
            "rss_fetched": packed["rss_ok"],
            "html_fetched": packed["html_ok"],
            "rss_count": packed["rss_count"],
            "html_count": packed["html_count"],
            "listed": len(items),
            "fetch_errors": packed.get("errors") or [],
        }
    )
    collection_jobs_store.set_progress(job_id, progress)

    stop_reason = "done"
    for item in items:
        if collection_jobs_store.stop_requested(job_id):
            stop_reason = "stop_requested"
            break
        if item.published_at is not None and item.published_at < cutoff:
            skipped += 1
            continue
        attrs = {"section": item.section or sec.id}
        outcome = news_articles_store.upsert_list_item(
            source=nikkei_feed.SOURCE,
            source_key=item.source_key,
            title=item.title,
            url=item.url,
            published_at=item.published_at,
            publisher=nikkei_feed.PUBLISHER,
            attrs=attrs,
        )
        if outcome == "inserted":
            inserted += 1
        elif outcome == "updated":
            updated += 1
        else:
            skipped += 1
        progress.update(
            {
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped,
                "pages_done": 1,
            }
        )
        collection_jobs_store.set_progress(job_id, progress)

    titles_translated = 0
    title_translate_error: str | None = None
    if stop_reason != "stop_requested":
        progress["stage"] = "title_translate"
        collection_jobs_store.set_progress(job_id, progress)
        collection_jobs_store.set_message(
            job_id, f"Nikkei 제목 번역 · {sec.label}"
        )
        try:
            from crawler.article_title_translate import (
                translate_and_store_missing,
            )

            tr = translate_and_store_missing(nikkei_feed.SOURCE, limit=500)
            titles_translated = int(tr.get("translated") or 0)
            progress["titles_translated"] = titles_translated
            progress["titles_pending"] = tr.get("pending")
            collection_jobs_store.set_progress(job_id, progress)
        except Exception as exc:  # noqa: BLE001 — feed must not fail on translate
            title_translate_error = str(exc)
            progress["title_translate_error"] = title_translate_error
            collection_jobs_store.set_progress(job_id, progress)

    message = {
        "done": (
            f"{sec.label} 목록 완료 "
            f"(RSS {packed['rss_count']}, HTML {packed['html_count']}"
            f", 제목번역 {titles_translated})"
        ),
        "stop_requested": "사용자 중단",
    }.get(stop_reason, stop_reason)
    if title_translate_error:
        message = f"{message} · 제목번역 실패: {title_translate_error[:120]}"

    progress.update(
        {
            "stage": "done",
            "section": sec.id,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "pages_done": 1,
            "listed": len(items),
            "period_months": period_months,
            "cutoff": cutoff.isoformat(),
            "stop_reason": stop_reason,
            "titles_translated": titles_translated,
            "message": message,
        }
    )
    return progress
