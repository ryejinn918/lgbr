"""Run a body-fill collection job (ARG articleView)."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from crawler import collection_jobs_store, news_articles_store
from crawler.sources import FEED_ALLOWLIST
from crawler.sources import arg_body
from crawler.sources.arg_http import make_session

DEFAULT_LIMIT = 200
MIN_LIMIT = 1
MAX_LIMIT = 1000
DEFAULT_REQUEST_DELAY_SECONDS = 1.0
MIN_DELAY_SECONDS = 0.5
MAX_DELAY_SECONDS = 5.0
BACKOFF_SECONDS = 3.0


def run_fetch_body_job(
    job_id: UUID | str,
    *,
    limit: int = DEFAULT_LIMIT,
    delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
) -> dict[str, Any]:
    job = collection_jobs_store.claim_job(job_id)
    source = str(job.get("source") or "")
    capability = str(job.get("capability") or "")
    if capability != "fetch_body":
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message=f"expected capability=fetch_body, got {capability!r}",
        )
    if source not in FEED_ALLOWLIST:
        return collection_jobs_store.end_job(
            job_id,
            error=True,
            message=f"source {source!r} is not in body-fetch allowlist",
        )

    limit = max(MIN_LIMIT, min(int(limit), MAX_LIMIT))
    delay = max(MIN_DELAY_SECONDS, min(float(delay_seconds), MAX_DELAY_SECONDS))
    progress: dict[str, Any] = {
        "stage": "fetch_body",
        "source": source,
        "capability": "fetch_body",
        "done": 0,
        "total": 0,
        "fetched": 0,
        "failed": 0,
        "delay_seconds": delay,
    }
    collection_jobs_store.set_progress(job_id, progress)
    collection_jobs_store.set_message(
        job_id, f"{source} 본문 채우기 시작 (limit={limit}, delay={delay}s)"
    )

    try:
        if source == "arg":
            result = _run_arg_bodies(
                job_id,
                limit=limit,
                delay_seconds=delay,
                progress=progress,
            )
        else:
            return collection_jobs_store.end_job(
                job_id,
                error=True,
                message=f"no body adapter for source={source!r}",
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
        message=result.get("message") or "본문 채우기 완료",
        progress=result,
    )


def _run_arg_bodies(
    job_id: UUID | str,
    *,
    limit: int,
    delay_seconds: float,
    progress: dict[str, Any],
) -> dict[str, Any]:
    pending = news_articles_store.list_pending_bodies(arg_body.SOURCE, limit=limit)
    total = len(pending)
    fetched = failed = done = 0
    stop_reason = "done"
    progress.update({"total": total, "done": 0, "fetched": 0, "failed": 0})
    collection_jobs_store.set_progress(job_id, progress)

    if total == 0:
        progress.update(
            {
                "stage": "done",
                "stop_reason": "nothing_pending",
                "message": "채울 본문 없음",
            }
        )
        return progress

    sess = make_session(accept="text/html,application/xhtml+xml")
    try:
        for i, row in enumerate(pending):
            if collection_jobs_store.stop_requested(job_id):
                stop_reason = "stop_requested"
                break

            key = str(row.get("source_key") or "")
            url = str(row.get("url") or "") or None
            article_id = row["id"]
            progress.update(
                {
                    "stage": "fetch_body",
                    "current_key": key,
                    "done": done,
                    "total": total,
                    "fetched": fetched,
                    "failed": failed,
                    "delay_seconds": delay_seconds,
                }
            )
            collection_jobs_store.set_progress(job_id, progress)
            collection_jobs_store.set_message(
                job_id, f"ARG 본문 {done + 1}/{total} · idxno={key}"
            )

            body, err = arg_body.fetch_article_safe(key, url=url, client=sess)
            http_fail = False
            if err and (
                "HTTP 429" in err
                or "HTTP 5" in err
                or "status code 429" in err.lower()
            ):
                http_fail = True

            if body is not None:
                news_articles_store.mark_body_fetched(
                    article_id, body_text=body.body_text
                )
                fetched += 1
            else:
                news_articles_store.mark_body_failed(
                    article_id, error=err or "unknown"
                )
                failed += 1
                if http_fail:
                    time.sleep(BACKOFF_SECONDS)

            done += 1
            progress.update(
                {
                    "done": done,
                    "fetched": fetched,
                    "failed": failed,
                    "current_key": key,
                }
            )
            collection_jobs_store.set_progress(job_id, progress)

            if i < total - 1 and not collection_jobs_store.stop_requested(job_id):
                time.sleep(delay_seconds)
    finally:
        sess.close()

    message = {
        "done": f"본문 채우기 완료 (성공 {fetched}, 실패 {failed})",
        "stop_requested": "사용자 중단",
        "nothing_pending": "채울 본문 없음",
    }.get(stop_reason, stop_reason)

    progress.update(
        {
            "stage": "done",
            "done": done,
            "total": total,
            "fetched": fetched,
            "failed": failed,
            "stop_reason": stop_reason,
            "message": message,
            "delay_seconds": delay_seconds,
        }
    )
    return progress
