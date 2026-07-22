"""Manual crawl run: session login is a subtask of the crawl lifecycle.

Fail-closed: any DB/state transition failure ends the crawl in error and
stops further work. Clean completion uses ended; failures use error.
"""

from __future__ import annotations

import time
from typing import Any

from crawler import crawls_store, sessions_store
from crawler.browser import allocate_cdp_port
from crawler.fnguide_session import (
    DEFAULT_IDLE_SECONDS,
    DEFAULT_TTL_SECONDS,
    FnguideSession,
)


class CrawlStateError(RuntimeError):
    """Raised when crawl cannot continue safely."""


def run_crawl(
    *,
    user_id: str,
    password: str,
    crawl_id: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    idle_seconds: int = DEFAULT_IDLE_SECONDS,
    headless: bool | None = True,
    force_other_session: bool = True,
    poll_seconds: float = 2.0,
) -> dict[str, Any]:
    """Claim API crawl row (starting → active → stopping → ended|error) around a session."""
    crawl = crawls_store.claim_crawl(crawl_id)
    crawl_id = str(crawl["id"])
    mode = str(crawl.get("mode") or "auto")
    cdp_port = allocate_cdp_port() if mode == "adhoc" else None
    touch_step = "adhoc" if mode == "adhoc" else "crawl"
    sess = FnguideSession(
        user_id=user_id,
        password=password,
        ttl_seconds=ttl_seconds,
        idle_seconds=idle_seconds,
        headless=headless,
        force_other_session=force_other_session,
        cdp_port=cdp_port,
    )

    try:
        sess.start()
        if not sess.session_id:
            raise CrawlStateError("Session start returned no session_id")
        if cdp_port is not None:
            crawls_store.set_cdp_port(crawl_id, cdp_port)
        crawls_store.attach_session(crawl_id, sess.session_id)
        crawls_store.mark_active(crawl_id)

        reason = "shutdown"
        while True:
            crawl_row = crawls_store.get_crawl(crawl_id)
            if crawl_row is None:
                raise CrawlStateError(f"Crawl row {crawl_id} missing")
            if crawl_row.get("ended_at") or crawl_row.get("state") in ("ended", "error"):
                raise CrawlStateError("Crawl was terminated externally")
            if crawl_row.get("stop_requested_at"):
                reason = "manual"
                break
            stop_reason = sess.poll_should_stop()
            if stop_reason:
                reason = stop_reason
                break
            # touch failure must not leave us "active" while DB is broken
            sess.touch(step=touch_step)
            time.sleep(max(poll_seconds, 0.5))

        crawls_store.mark_stopping(crawl_id)
        ended_session = sess.stop(reason)
        if ended_session.get("state") == "error":
            return crawls_store.end_crawl(
                crawl_id,
                message=ended_session.get("message") or "session ended in error",
                error=True,
            )
        return crawls_store.end_crawl(
            crawl_id, message=ended_session.get("message"), error=False
        )
    except KeyboardInterrupt:
        return _fail_closed(crawl_id, sess, message="interrupted")
    except Exception as exc:
        return _fail_closed(crawl_id, sess, message=str(exc))


def _fail_closed(
    crawl_id: str,
    sess: FnguideSession,
    *,
    message: str,
) -> dict[str, Any]:
    """Stop browser/session best-effort, then force crawl → error. DB must succeed."""
    _best_effort_stop_session(sess, message=message)

    try:
        crawl = crawls_store.get_crawl(crawl_id)
    except Exception as exc:
        raise CrawlStateError(
            f"Crawl failed ({message}); also cannot read crawl row: {exc}"
        ) from exc

    if crawl is None:
        raise CrawlStateError(f"Crawl failed ({message}); crawl row missing")

    if crawl.get("ended_at") and crawl.get("state") in ("ended", "error"):
        if crawl.get("state") == "error":
            return crawl
        # Was clean-ended somehow; upgrade message if needed but keep ended.
        return crawl

    try:
        if crawl.get("state") != "stopping":
            try:
                crawls_store.mark_stopping(crawl_id, message=message)
            except Exception:
                # Still force terminal error below.
                pass
        return crawls_store.end_crawl(crawl_id, message=message, error=True)
    except Exception as exc:
        raise CrawlStateError(
            f"Crawl failed ({message}); cannot mark error in DB: {exc}"
        ) from exc


def _best_effort_stop_session(sess: FnguideSession, *, message: str) -> None:
    if not sess.session_id and not sess.page:
        return
    try:
        if sess.session_id:
            sess.stop("error", message=message)
        else:
            sess._close_browser()
    except Exception:
        try:
            if sess.session_id:
                sessions_store.end_session(
                    sess.session_id,
                    end_reason="error",
                    message=message,
                    event="error",
                )
        except Exception:
            pass
        try:
            sess._close_browser()
        except Exception:
            pass
        sess.session_id = None
