"""Manual crawl run: session login is a subtask of the crawl lifecycle.

Fail-closed: any DB/state transition failure ends the crawl in error and
stops further work. Clean completion uses ended; failures use error.

SIGTERM/SIGINT request a cooperative shutdown (logout → crawl ended), not error.
"""

from __future__ import annotations

import signal
import threading
import time
from pathlib import Path
from typing import Any

from crawler import crawls_store, sessions_store
from crawler.browser import allocate_cdp_port
from crawler.fnguide_session import (
    DEFAULT_IDLE_SECONDS,
    DEFAULT_TTL_SECONDS,
    FnguideSession,
)
from crawler.jobs.datacenter import run_datacenter_job

DOWNLOADS_ROOT = Path(".crawler/downloads")

_stop_flag = threading.Event()
_handlers_installed = False


class CrawlStateError(RuntimeError):
    """Raised when crawl cannot continue safely."""


def _signal_requested() -> bool:
    return _stop_flag.is_set()


def _install_signal_handlers() -> None:
    global _handlers_installed
    if _handlers_installed:
        return

    def _on_signal(signum: int, _frame: Any) -> None:
        _stop_flag.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    _handlers_installed = True


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
    _stop_flag.clear()
    _install_signal_handlers()

    crawl = crawls_store.claim_crawl(crawl_id)
    crawl_id = str(crawl["id"])
    mode = str(crawl.get("mode") or "auto")
    cdp_port = allocate_cdp_port() if mode == "adhoc" else None
    touch_step = "adhoc" if mode == "adhoc" else "crawl"
    download_dir: Path | None = None
    if mode == "datacenter":
        download_dir = DOWNLOADS_ROOT / crawl_id
        download_dir.mkdir(parents=True, exist_ok=True)
        touch_step = "datacenter"

    sess = FnguideSession(
        user_id=user_id,
        password=password,
        ttl_seconds=ttl_seconds,
        idle_seconds=idle_seconds,
        headless=headless,
        force_other_session=force_other_session,
        cdp_port=cdp_port,
        downloads_path=download_dir,
    )

    try:
        sess.start()
        if not sess.session_id:
            raise CrawlStateError("Session start returned no session_id")
        if _signal_requested():
            return _graceful_end(
                crawl_id, sess, reason="shutdown", message="shutdown signal"
            )
        if cdp_port is not None:
            crawls_store.set_cdp_port(crawl_id, cdp_port)
        crawls_store.attach_session(crawl_id, sess.session_id)
        crawls_store.mark_active(crawl_id)

        if mode == "datacenter":
            return _run_datacenter(crawl_id, crawl, sess, download_dir)

        reason = "shutdown"
        message: str | None = None
        while True:
            if _signal_requested():
                reason = "shutdown"
                message = "shutdown signal"
                break
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

        return _graceful_end(crawl_id, sess, reason=reason, message=message)
    except KeyboardInterrupt:
        return _graceful_end(
            crawl_id, sess, reason="shutdown", message="shutdown signal"
        )
    except Exception as exc:
        return _fail_closed(crawl_id, sess, message=str(exc))


def _run_datacenter(
    crawl_id: str,
    crawl: dict[str, Any],
    sess: FnguideSession,
    download_dir: Path | None,
) -> dict[str, Any]:
    if sess.page is None:
        raise CrawlStateError("Datacenter crawl has no browser page")
    if download_dir is None:
        raise CrawlStateError("Datacenter crawl missing download_dir")

    try:
        limit = int(crawl.get("report_limit") or 5)
    except (TypeError, ValueError):
        limit = 5

    def should_stop() -> bool:
        if _signal_requested():
            return True
        row = crawls_store.get_crawl(crawl_id)
        if row is None:
            return True
        if row.get("ended_at") or row.get("state") in ("ended", "error"):
            return True
        return bool(row.get("stop_requested_at"))

    summary = run_datacenter_job(
        sess.page,
        limit=limit,
        download_dir=download_dir,
        should_stop=should_stop,
        touch=lambda: sess.touch(step="datacenter"),
    )
    message = summary.as_message()
    if _signal_requested() or summary.stopped:
        message = f"{message}; shutdown signal"
    return _graceful_end(crawl_id, sess, reason="shutdown", message=message)


def _graceful_end(
    crawl_id: str,
    sess: FnguideSession,
    *,
    reason: str,
    message: str | None = None,
) -> dict[str, Any]:
    """Logout and mark crawl ended (not error)."""
    try:
        crawls_store.mark_stopping(crawl_id, message=message)
    except Exception:
        pass

    try:
        ended_session = (
            sess.stop(reason, message=message)
            if sess.session_id or sess.page
            else {"state": "ended", "message": message}
        )
    except Exception as exc:
        return _fail_closed(crawl_id, sess, message=str(exc))

    if ended_session.get("state") == "error":
        return crawls_store.end_crawl(
            crawl_id,
            message=ended_session.get("message") or message or "session ended in error",
            error=True,
        )
    return crawls_store.end_crawl(
        crawl_id,
        message=message or ended_session.get("message"),
        error=False,
    )


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
