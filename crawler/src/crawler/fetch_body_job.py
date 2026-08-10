"""Run a body-fill collection job (ARG articleView)."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from crawler import collection_jobs_store, news_articles_store
from crawler.sources import FEED_ALLOWLIST
from crawler.sources import arg_body
from crawler.sources import nikkei_body
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
        elif source == "nikkei":
            result = _run_nikkei_bodies(
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


def _attrs_dict(row: dict[str, Any]) -> dict[str, Any]:
    attrs = row.get("attrs")
    if isinstance(attrs, dict):
        return attrs
    if isinstance(attrs, str) and attrs.strip():
        import json

        try:
            parsed = json.loads(attrs)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _run_nikkei_bodies(
    job_id: UUID | str,
    *,
    limit: int,
    delay_seconds: float,
    progress: dict[str, Any],
) -> dict[str, Any]:
    from crawler.article_summary import summarize_article_text, summary_attrs
    from crawler.article_title_translate import ensure_title_ko

    pending = news_articles_store.list_pending_bodies(
        nikkei_body.SOURCE, limit=limit
    )
    total = len(pending)
    fetched = failed = done = summarized = 0
    stop_reason = "done"
    progress.update(
        {
            "total": total,
            "done": 0,
            "fetched": 0,
            "failed": 0,
            "summarized": 0,
        }
    )
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

    def _reuse_body(row: dict[str, Any]) -> bool:
        attrs = _attrs_dict(row)
        existing_body = row.get("body_text")
        return bool(
            existing_body
            and str(existing_body).strip()
            and not attrs.get("summarized_at")
        )

    needs_browser = any(not _reuse_body(r) for r in pending)
    browser: nikkei_body.NikkeiBodyBrowser | None = None
    try:
        if needs_browser:
            browser = nikkei_body.NikkeiBodyBrowser(headless=True)
            collection_jobs_store.set_message(job_id, "Nikkei 로그인 중…")
            browser.start()
        for i, row in enumerate(pending):
            if collection_jobs_store.stop_requested(job_id):
                stop_reason = "stop_requested"
                break

            key = str(row.get("source_key") or "")
            url = str(row.get("url") or "") or None
            article_id = row["id"]
            title = str(row.get("title") or "")
            attrs = _attrs_dict(row)
            reuse_body = _reuse_body(row)
            progress.update(
                {
                    "stage": "fetch_body",
                    "current_key": key,
                    "done": done,
                    "total": total,
                    "fetched": fetched,
                    "failed": failed,
                    "summarized": summarized,
                    "delay_seconds": delay_seconds,
                    "reuse_body": reuse_body,
                }
            )
            collection_jobs_store.set_progress(job_id, progress)
            collection_jobs_store.set_message(
                job_id, f"Nikkei 본문·요약 {done + 1}/{total} · {key}"
            )

            if not attrs.get("title_ko"):
                try:
                    ensure_title_ko(article_id, title)
                except Exception:
                    pass

            raw_text: str | None = None
            err: str | None = None
            if reuse_body:
                raw_text = str(row.get("body_text") or "").strip()
            else:
                if browser is None:
                    news_articles_store.mark_body_failed(
                        article_id, error="browser unavailable"
                    )
                    failed += 1
                else:
                    body, err = nikkei_body.fetch_article_safe(
                        key, url=url, browser=browser
                    )
                    if body is not None:
                        raw_text = body.body_text
                        fetched += 1
                    else:
                        news_articles_store.mark_body_failed(
                            article_id, error=err or "unknown"
                        )
                        failed += 1
                        if err and (
                            "HTTP 429" in err
                            or "logged out" in err.lower()
                            or "Login" in err
                        ):
                            time.sleep(BACKOFF_SECONDS)

            if raw_text:
                try:
                    result = summarize_article_text(
                        title=title,
                        source=nikkei_body.SOURCE,
                        raw_text=raw_text,
                    )
                    news_articles_store.mark_body_fetched(
                        article_id,
                        body_text=str(result["summary"]).strip(),
                        attrs=summary_attrs(result),
                    )
                    summarized += 1
                except Exception as exc:
                    news_articles_store.mark_body_failed(
                        article_id, error=f"summarize: {exc}"
                    )
                    failed += 1

            done += 1
            progress.update(
                {
                    "done": done,
                    "fetched": fetched,
                    "failed": failed,
                    "summarized": summarized,
                    "current_key": key,
                }
            )
            collection_jobs_store.set_progress(job_id, progress)

            if i < total - 1 and not collection_jobs_store.stop_requested(
                job_id
            ):
                time.sleep(
                    delay_seconds if not reuse_body else min(delay_seconds, 1.0)
                )
    finally:
        if browser is not None:
            browser.close()

    message = {
        "done": (
            f"본문 요약 완료 (요약 {summarized}, 추출 {fetched}, 실패 {failed})"
        ),
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
            "summarized": summarized,
            "stop_reason": stop_reason,
            "message": message,
            "delay_seconds": delay_seconds,
        }
    )
    return progress
