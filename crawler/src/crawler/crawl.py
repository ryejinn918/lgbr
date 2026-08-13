"""Manual crawl run: session login is a subtask of the crawl lifecycle.

Fail-closed: any DB/state transition failure ends the crawl in error and
stops further work. Clean completion uses ended; failures use error.

SIGTERM/SIGINT request a cooperative shutdown (logout → crawl ended), not error.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path
from typing import Any

from crawler import crawls_store, sessions_store
from crawler.asset_id import downloads_dir
from crawler.browser import allocate_cdp_port
from crawler.crawl_log import CrawlLogger
from crawler.fnguide_session import (
    DEFAULT_IDLE_SECONDS,
    DEFAULT_TTL_SECONDS,
    FnguideSession,
)
from crawler.adhoc_session import AdhocBrowserSession
from crawler.hbr_session import HbrSession
from crawler.hbrkorea_session import HbrKoreaSession
from crawler.jobs.search_report import (
    ALL_PROFILES_MODE,
    SEARCH_MODES,
    SEARCH_PROFILE_ORDER,
    SearchJobSummary,
    get_profile,
    run_search_report_job,
)
from crawler.nikkei_session import NikkeiSession
from crawler.nikkeixtech_session import NikkeixtechSession
from crawler.session import LoginPageError
from crawler.sources.registry import get_source, is_adhoc_source, source_requires_login

LoggedInAdhocSession = HbrSession | HbrKoreaSession | NikkeiSession | NikkeixtechSession


def _adhoc_hold_modes() -> frozenset[str]:
    from crawler.sources.registry import adhoc_source_ids

    return frozenset({"adhoc"}) | adhoc_source_ids()


# Legacy name: modes that open CDP and hold the browser for remote inspection.
ADHOC_HOLD_MODES = _adhoc_hold_modes()

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
    if is_adhoc_source(mode):
        if source_requires_login(mode):
            return _run_logged_in_source_adhoc(
                crawl_id=crawl_id,
                crawl=crawl,
                mode=mode,
                user_id=user_id,
                password=password,
                ttl_seconds=ttl_seconds,
                idle_seconds=idle_seconds,
                headless=headless,
                force_other_session=force_other_session,
                poll_seconds=poll_seconds,
            )
        return _run_source_adhoc(
            crawl_id=crawl_id,
            crawl=crawl,
            mode=mode,
            ttl_seconds=ttl_seconds,
            idle_seconds=idle_seconds,
            headless=headless,
            poll_seconds=poll_seconds,
        )

    debug = bool(crawl.get("debug"))
    asset_id = str(crawl.get("asset_id") or "")
    if not asset_id:
        raise CrawlStateError(f"Crawl {crawl_id} missing asset_id")
    log = CrawlLogger(crawl_id)
    log.emit(
        level="info",
        stage="crawl",
        event="claimed",
        mode=mode,
        asset_id=asset_id,
        debug=debug,
    )
    log.set_progress(stage="login", mode=mode, asset_id=asset_id, debug=debug)

    is_search = mode in SEARCH_MODES or mode == ALL_PROFILES_MODE
    want_cdp = mode in ADHOC_HOLD_MODES or (mode in SEARCH_MODES and debug)
    cdp_port = allocate_cdp_port() if want_cdp else None
    touch_step = "adhoc" if mode == "adhoc" else "crawl"
    if mode in SEARCH_MODES:
        touch_step = mode
    elif mode == ALL_PROFILES_MODE:
        touch_step = ALL_PROFILES_MODE
    download_dir = downloads_dir(asset_id)
    download_dir.mkdir(parents=True, exist_ok=True)

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
        log.emit(
            level="info",
            stage="login",
            event="stage_start",
            mode=mode,
            asset_id=asset_id,
            debug=debug,
        )
        log.set_progress(stage="login", mode=mode, asset_id=asset_id, debug=debug)
        try:
            sess.start()
        except LoginPageError as exc:
            log.emit(
                level="error",
                stage="login",
                event="error",
                error=str(exc),
                **(exc.detail or {}),
            )
            raise
        log.emit(level="info", stage="login", event="stage_end", mode=mode)
        if not sess.session_id:
            raise CrawlStateError("Session start returned no session_id")
        if _signal_requested():
            return _graceful_end(
                crawl_id,
                sess,
                log,
                reason="shutdown",
                message="shutdown signal",
            )
        if cdp_port is not None:
            crawls_store.set_cdp_port(crawl_id, cdp_port)
            log.emit(level="info", stage="crawl", event="cdp_ready", cdp_port=cdp_port)
        crawls_store.attach_session(crawl_id, sess.session_id)
        crawls_store.mark_active(crawl_id)
        log.emit(
            level="info",
            stage="crawl",
            event="active",
            mode=mode,
            asset_id=asset_id,
            debug=debug,
        )
        log.set_progress(stage="active", mode=mode, asset_id=asset_id, debug=debug)

        if is_search:
            if mode == ALL_PROFILES_MODE:
                summary = _run_all_profiles_job(
                    crawl_id, crawl, sess, download_dir, log
                )
            else:
                summary = _run_search_job(
                    crawl_id, crawl, sess, download_dir, log
                )
            message = summary.as_message()
            if _signal_requested() or summary.stopped:
                message = f"{message}; shutdown signal"
                return _graceful_end(
                    crawl_id, sess, log, reason="shutdown", message=message
                )
            if debug and mode in SEARCH_MODES:
                return _handoff_to_adhoc(
                    crawl_id,
                    sess,
                    log,
                    cdp_port=cdp_port,
                    job_message=message,
                    poll_seconds=poll_seconds,
                )
            return _graceful_end(
                crawl_id, sess, log, reason="shutdown", message=message
            )

        return _hold_until_stop(
            crawl_id,
            sess,
            log,
            touch_step=touch_step,
            poll_seconds=poll_seconds,
        )
    except KeyboardInterrupt:
        return _graceful_end(
            crawl_id,
            sess,
            log,
            reason="shutdown",
            message="shutdown signal",
        )
    except LoginPageError as exc:
        log.emit(
            level="error",
            stage="crawl",
            event="error",
            error=str(exc),
            **(exc.detail or {}),
        )
        return _fail_closed(crawl_id, sess, log, message=str(exc))
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        if isinstance(detail, dict):
            log.emit(
                level="error",
                stage="crawl",
                event="error",
                error=str(exc),
                **detail,
            )
        else:
            log.emit(level="error", stage="crawl", event="error", error=str(exc))
        return _fail_closed(crawl_id, sess, log, message=str(exc))


def _resolve_adhoc_hub_url(mode: str) -> str:
    override = (os.environ.get("ADHOC_START_URL") or "").strip()
    if override:
        return override
    src = get_source(mode)
    if mode == "pwc":
        from crawler.sources.pwc_http import get_catalog

        catalog_id = os.environ.get("PWC_CATALOG") or "kr"
        try:
            return get_catalog(catalog_id).hub_url
        except ValueError:
            return get_catalog("kr").hub_url
    return src.hub_url


def _run_logged_in_source_adhoc(
    *,
    crawl_id: str,
    crawl: dict[str, Any],
    mode: str,
    user_id: str,
    password: str,
    ttl_seconds: int,
    idle_seconds: int,
    headless: bool | None,
    force_other_session: bool,
    poll_seconds: float,
) -> dict[str, Any]:
    """Account media adhoc: site login + CDP hold (e.g. HBR Korea)."""
    asset_id = str(crawl.get("asset_id") or "")
    if not asset_id:
        raise CrawlStateError(f"Crawl {crawl_id} missing asset_id")
    if not user_id or not password:
        raise CrawlStateError(f"{mode} crawl requires account credentials")
    src = get_source(mode)
    log = CrawlLogger(crawl_id)
    log.emit(
        level="info",
        stage="crawl",
        event="claimed",
        mode=mode,
        asset_id=asset_id,
    )
    cdp_port = allocate_cdp_port()
    download_dir = downloads_dir(asset_id)
    download_dir.mkdir(parents=True, exist_ok=True)

    _ = src  # validated via get_source above
    if mode == "hbr":
        sess: LoggedInAdhocSession = HbrSession(
            user_id=user_id,
            password=password,
            ttl_seconds=ttl_seconds,
            idle_seconds=idle_seconds,
            headless=headless,
            force_other_session=force_other_session,
            cdp_port=cdp_port,
            downloads_path=download_dir,
        )
    elif mode == "hbrkorea":
        sess = HbrKoreaSession(
            user_id=user_id,
            password=password,
            ttl_seconds=ttl_seconds,
            idle_seconds=idle_seconds,
            headless=headless,
            force_other_session=force_other_session,
            cdp_port=cdp_port,
            downloads_path=download_dir,
        )
    elif mode == "nikkei":
        sess = NikkeiSession(
            user_id=user_id,
            password=password,
            ttl_seconds=ttl_seconds,
            idle_seconds=idle_seconds,
            headless=headless,
            force_other_session=force_other_session,
            cdp_port=cdp_port,
            downloads_path=download_dir,
        )
    elif mode == "nikkeixtech":
        sess = NikkeixtechSession(
            user_id=user_id,
            password=password,
            ttl_seconds=ttl_seconds,
            idle_seconds=idle_seconds,
            headless=headless,
            force_other_session=force_other_session,
            cdp_port=cdp_port,
            downloads_path=download_dir,
        )
    else:
        raise CrawlStateError(f"unsupported logged-in adhoc source: {mode}")

    try:
        # Publish CDP before login so OTP (xTECH/日経ID) can be entered remotely.
        crawls_store.set_cdp_port(crawl_id, cdp_port)
        log.emit(level="info", stage="crawl", event="cdp_ready", cdp_port=cdp_port)
        log.emit(
            level="info",
            stage="login",
            event="stage_start",
            mode=mode,
            asset_id=asset_id,
        )
        log.set_progress(
            stage="login",
            mode=mode,
            asset_id=asset_id,
            cdp_port=cdp_port,
        )
        try:
            sess.start()
        except LoginPageError as exc:
            log.emit(
                level="error",
                stage="login",
                event="error",
                error=str(exc),
                **(exc.detail or {}),
            )
            raise
        if getattr(sess, "conflict_accepted", False):
            log.emit(
                level="info",
                stage="login",
                event="session_conflict_accepted",
                mode=mode,
            )
        if getattr(sess, "otp_waited", False):
            log.emit(
                level="info",
                stage="login",
                event="otp_completed",
                mode=mode,
            )
        log.emit(level="info", stage="login", event="stage_end", mode=mode)
        if not sess.session_id:
            raise CrawlStateError("Session start returned no session_id")
        if _signal_requested():
            return _graceful_end(
                crawl_id,
                sess,
                log,
                reason="shutdown",
                message="shutdown signal",
            )
        crawls_store.attach_session(crawl_id, sess.session_id)
        crawls_store.mark_active(crawl_id)
        log.emit(
            level="info",
            stage="crawl",
            event="active",
            mode=mode,
            asset_id=asset_id,
            url=sess.page.url if sess.page else None,
        )
        log.set_progress(
            stage="adhoc_hold",
            mode=mode,
            asset_id=asset_id,
            cdp_port=cdp_port,
            url=sess.page.url if sess.page else None,
        )
        return _hold_until_stop(
            crawl_id,
            sess,
            log,
            touch_step=mode,
            poll_seconds=poll_seconds,
        )
    except KeyboardInterrupt:
        return _graceful_end(
            crawl_id,
            sess,
            log,
            reason="shutdown",
            message="shutdown signal",
        )
    except LoginPageError as exc:
        log.emit(
            level="error",
            stage="crawl",
            event="error",
            error=str(exc),
            **(exc.detail or {}),
        )
        return _fail_closed(crawl_id, sess, log, message=str(exc))
    except Exception as exc:
        log.emit(level="error", stage="crawl", event="error", error=str(exc))
        return _fail_closed(crawl_id, sess, log, message=str(exc))


def _run_source_adhoc(
    *,
    crawl_id: str,
    crawl: dict[str, Any],
    mode: str,
    ttl_seconds: int,
    idle_seconds: int,
    headless: bool | None,
    poll_seconds: float,
) -> dict[str, Any]:
    """Media-source adhoc: Patchright Chrome + CDP, no FnGuide login."""
    asset_id = str(crawl.get("asset_id") or "")
    if not asset_id:
        raise CrawlStateError(f"Crawl {crawl_id} missing asset_id")
    src = get_source(mode)
    log = CrawlLogger(crawl_id)
    log.emit(
        level="info",
        stage="crawl",
        event="claimed",
        mode=mode,
        asset_id=asset_id,
    )
    cdp_port = allocate_cdp_port()
    download_dir = downloads_dir(asset_id)
    download_dir.mkdir(parents=True, exist_ok=True)
    hub_url = _resolve_adhoc_hub_url(mode)
    sess = AdhocBrowserSession(
        source_id=src.id,
        start_url=hub_url,
        ttl_seconds=ttl_seconds,
        idle_seconds=idle_seconds,
        headless=headless,
        cdp_port=cdp_port,
        downloads_path=download_dir,
    )
    try:
        log.emit(level="info", stage="browser", event="stage_start", mode=mode)
        log.set_progress(stage="browser", mode=mode, asset_id=asset_id)
        started = sess.start()
        log.emit(
            level="info",
            stage="browser",
            event="stage_end",
            mode=mode,
            url=started.get("url"),
        )
        if _signal_requested():
            return _graceful_end(
                crawl_id,
                sess,
                log,
                reason="shutdown",
                message="shutdown signal",
            )
        crawls_store.set_cdp_port(crawl_id, cdp_port)
        log.emit(level="info", stage="crawl", event="cdp_ready", cdp_port=cdp_port)
        crawls_store.mark_active(crawl_id, require_session=False)
        log.emit(
            level="info",
            stage="crawl",
            event="active",
            mode=mode,
            asset_id=asset_id,
            url=started.get("url"),
        )
        log.set_progress(
            stage="adhoc_hold",
            mode=mode,
            asset_id=asset_id,
            cdp_port=cdp_port,
            url=started.get("url"),
        )
        return _hold_until_stop(
            crawl_id,
            sess,
            log,
            touch_step=mode,
            poll_seconds=poll_seconds,
        )
    except KeyboardInterrupt:
        return _graceful_end(
            crawl_id,
            sess,
            log,
            reason="shutdown",
            message="shutdown signal",
        )
    except Exception as exc:
        log.emit(level="error", stage="crawl", event="error", error=str(exc))
        return _fail_closed(crawl_id, sess, log, message=str(exc))


def _crawl_should_stop(crawl_id: str) -> bool:
    if _signal_requested():
        return True
    row = crawls_store.get_crawl(crawl_id)
    if row is None:
        return True
    if row.get("ended_at") or row.get("state") in ("ended", "error"):
        return True
    return bool(row.get("stop_requested_at"))


def _run_search_job(
    crawl_id: str,
    crawl: dict[str, Any],
    sess: FnguideSession,
    download_dir: Path | None,
    log: CrawlLogger,
    *,
    profile_mode: str | None = None,
) -> SearchJobSummary:
    crawl_mode = str(crawl.get("mode") or "")
    mode = profile_mode or crawl_mode
    if sess.page is None:
        raise CrawlStateError(f"{mode} crawl has no browser page")
    if download_dir is None:
        raise CrawlStateError(f"{mode} crawl missing download_dir")

    raw_limit = crawl.get("report_limit")
    limit: int | None
    if raw_limit is None:
        limit = None
    else:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = None

    profile = get_profile(mode)

    return run_search_report_job(
        sess.page,
        profile=profile,
        limit=limit,
        download_dir=download_dir,
        should_stop=lambda: _crawl_should_stop(crawl_id),
        touch=lambda: sess.touch(step=mode),
        logger=log,
        crawl_id=crawl_id,
        asset_id=str(crawl.get("asset_id") or "") or None,
    )


def _run_all_profiles_job(
    crawl_id: str,
    crawl: dict[str, Any],
    sess: FnguideSession,
    download_dir: Path | None,
    log: CrawlLogger,
) -> SearchJobSummary:
    modes = SEARCH_PROFILE_ORDER
    total = len(modes)
    aggregate = SearchJobSummary()
    asset_id = str(crawl.get("asset_id") or "")

    for index, profile_mode in enumerate(modes, start=1):
        if _crawl_should_stop(crawl_id):
            aggregate.stopped = True
            break

        log.emit(
            level="info",
            stage="download",
            event="profile_start",
            mode=profile_mode,
            profile_index=index,
            profile_total=total,
            asset_id=asset_id or None,
        )
        log.set_progress(
            stage="active",
            mode=profile_mode,
            profile_index=index,
            profile_total=total,
            asset_id=asset_id or None,
        )

        summary = _run_search_job(
            crawl_id,
            crawl,
            sess,
            download_dir,
            log,
            profile_mode=profile_mode,
        )
        aggregate.downloaded.extend(summary.downloaded)
        aggregate.listed += summary.listed
        aggregate.skipped_blind += summary.skipped_blind
        aggregate.skipped_existing += summary.skipped_existing
        aggregate.skipped_no_download += summary.skipped_no_download
        aggregate.failed += summary.failed

        log.emit(
            level="info",
            stage="download",
            event="profile_end",
            mode=profile_mode,
            profile_index=index,
            profile_total=total,
            **summary.as_detail(),
        )

        if summary.stopped or _crawl_should_stop(crawl_id):
            aggregate.stopped = True
            break

    log.set_progress(
        stage="active",
        mode=ALL_PROFILES_MODE,
        profile_total=total,
        downloaded=len(aggregate.downloaded),
        listed=aggregate.listed,
        skipped_blind=aggregate.skipped_blind,
        skipped_existing=aggregate.skipped_existing,
        skipped_no_download=aggregate.skipped_no_download,
        failed=aggregate.failed,
        stopped=aggregate.stopped,
    )
    return aggregate


def _handoff_to_adhoc(
    crawl_id: str,
    sess: FnguideSession,
    log: CrawlLogger,
    *,
    cdp_port: int | None,
    job_message: str,
    poll_seconds: float,
) -> dict[str, Any]:
    """After datacenter job, keep the browser open as adhoc+CDP for inspection."""
    crawls_store.set_mode(crawl_id, "adhoc")
    if cdp_port is not None:
        crawls_store.set_cdp_port(crawl_id, cdp_port)
    log.emit(
        level="info",
        stage="crawl",
        event="debug_handoff",
        mode="adhoc",
        cdp_port=cdp_port,
        message=job_message,
    )
    log.set_progress(
        stage="adhoc_hold",
        mode="adhoc",
        debug=True,
        job_message=job_message,
        cdp_port=cdp_port,
    )
    try:
        crawls_store.set_message(crawl_id, f"job_done: {job_message}")
    except Exception as exc:
        log.emit(
            level="warn",
            stage="crawl",
            event="debug_handoff_message_failed",
            error=str(exc),
        )
    return _hold_until_stop(
        crawl_id,
        sess,
        log,
        touch_step="adhoc",
        poll_seconds=poll_seconds,
    )


def _hold_until_stop(
    crawl_id: str,
    sess: FnguideSession | AdhocBrowserSession | LoggedInAdhocSession,
    log: CrawlLogger,
    *,
    touch_step: str,
    poll_seconds: float,
) -> dict[str, Any]:
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
        sess.touch(step=touch_step)
        time.sleep(max(poll_seconds, 0.5))

    return _graceful_end(crawl_id, sess, log, reason=reason, message=message)


def _graceful_end(
    crawl_id: str,
    sess: FnguideSession | AdhocBrowserSession | LoggedInAdhocSession,
    log: CrawlLogger,
    *,
    reason: str,
    message: str | None = None,
) -> dict[str, Any]:
    """Logout and mark crawl ended (not error)."""
    summary = (message or "").strip()
    if len(summary) > 240:
        summary = summary[:237] + "..."
    log.emit(
        level="info",
        stage="shutdown",
        event="stage_start",
        reason=reason,
        **({"summary": summary} if summary else {}),
    )
    log.set_progress(stage="shutdown", reason=reason)
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
        log.emit(level="error", stage="shutdown", event="error", error=str(exc))
        return _fail_closed(crawl_id, sess, log, message=str(exc))

    if ended_session.get("state") == "error":
        err_msg = ended_session.get("message") or message or "session ended in error"
        log.emit(level="error", stage="shutdown", event="crawl_end", error=err_msg)
        return crawls_store.end_crawl(crawl_id, message=err_msg, error=True)
    end_summary = (message or ended_session.get("message") or "").strip()
    if len(end_summary) > 240:
        end_summary = end_summary[:237] + "..."
    log.emit(
        level="info",
        stage="shutdown",
        event="crawl_end",
        reason=reason,
        **({"summary": end_summary} if end_summary else {}),
    )
    log.set_progress(stage="ended")
    return crawls_store.end_crawl(
        crawl_id,
        message=message or ended_session.get("message"),
        error=False,
    )


def _fail_closed(
    crawl_id: str,
    sess: FnguideSession | AdhocBrowserSession | LoggedInAdhocSession,
    log: CrawlLogger | None,
    *,
    message: str,
) -> dict[str, Any]:
    """Stop browser/session best-effort, then force crawl → error. DB must succeed."""
    if log:
        log.emit(level="error", stage="crawl", event="fail_closed", error=message)
        log.set_progress(stage="error", error=message)
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


def _best_effort_stop_session(
    sess: FnguideSession | AdhocBrowserSession | LoggedInAdhocSession,
    *,
    message: str,
) -> None:
    if not sess.session_id and not sess.page:
        return
    try:
        if isinstance(sess, AdhocBrowserSession):
            sess.stop("error", message=message)
            return
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
        if isinstance(
            sess,
            (
                FnguideSession,
                HbrSession,
                HbrKoreaSession,
                NikkeiSession,
                NikkeixtechSession,
            ),
        ):
            sess.session_id = None
