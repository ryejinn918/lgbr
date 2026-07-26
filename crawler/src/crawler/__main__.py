"""CLI entry: python -m crawler"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from crawler import cdp as cdp_ops
from crawler.browser import open_login
from crawler.crawl import run_crawl
from crawler.db import load_database_env
from crawler.feed_job import DEFAULT_MAX_PAGES, run_feed_job
from crawler.fnguide_session import (
    DEFAULT_IDLE_SECONDS,
    DEFAULT_TTL_SECONDS,
)
from crawler.session import (
    DEFAULT_SESSION_PATH,
    login_and_capture,
    session_summary,
    verify_session,
)
from crawler import collection_jobs_store, crawls_store, sessions_store
from crawler.status import DEFAULT_STATUS_PATH, clear_status, get_status, set_status


def _load_env() -> None:
    """Load crawler/.env and repo .env without overriding exports."""
    candidates = [
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[3] / ".env",
        Path.cwd() / "crawler" / ".env",
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
    load_database_env()


def _add_headless(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium without a visible window",
    )


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(description="Fnguide automation")
    sub = parser.add_subparsers(dest="command")

    open_parser = sub.add_parser("open-login", help="Open the login page")
    _add_headless(open_parser)

    login_parser = sub.add_parser(
        "login",
        help="(debug) Log in and capture storage state",
    )
    _add_headless(login_parser)
    login_parser.add_argument("--user-id", default=os.environ.get("FNGUIDE_USER_ID"))
    login_parser.add_argument("--password", default=os.environ.get("FNGUIDE_PASSWORD"))
    login_parser.add_argument("--session", type=Path, default=DEFAULT_SESSION_PATH)
    login_parser.add_argument(
        "--no-force",
        action="store_true",
        help="Do not confirm the single-session conflict dialog",
    )

    verify_parser = sub.add_parser(
        "verify-session",
        help="(debug) Verify a captured session still looks logged in",
    )
    _add_headless(verify_parser)
    verify_parser.add_argument("--session", type=Path, default=DEFAULT_SESSION_PATH)

    crawl_parser = sub.add_parser(
        "crawl",
        help="Crawl worker (started by API with --crawl-id)",
    )
    crawl_sub = crawl_parser.add_subparsers(dest="crawl_command")
    crawl_run = crawl_sub.add_parser(
        "run",
        help="Claim API crawl row, acquire session, hold until stop/idle/ttl",
    )
    _add_headless(crawl_run)
    crawl_run.add_argument("--user-id", default=os.environ.get("FNGUIDE_USER_ID"))
    crawl_run.add_argument("--password", default=os.environ.get("FNGUIDE_PASSWORD"))
    crawl_run.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    crawl_run.add_argument("--idle", type=int, default=DEFAULT_IDLE_SECONDS)
    crawl_run.add_argument(
        "--no-force",
        action="store_true",
        help="Do not confirm the single-session conflict dialog",
    )
    crawl_run.add_argument(
        "--crawl-id",
        required=True,
        help="Crawl row id created by POST /api/crawl/start",
    )
    crawl_sub.add_parser("current", help="Show current crawl")

    feed_parser = sub.add_parser(
        "feed",
        help="List-expansion feed worker (started by API with --job-id)",
    )
    feed_sub = feed_parser.add_subparsers(dest="feed_command")
    feed_run = feed_sub.add_parser(
        "run",
        help="Claim collection_jobs row and run source feed adapter",
    )
    feed_run.add_argument(
        "--job-id",
        required=True,
        help="collection_jobs id created by POST /api/collection/start",
    )
    feed_run.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Max list pages to scan (default {DEFAULT_MAX_PAGES})",
    )
    feed_current = feed_sub.add_parser(
        "current",
        help="Show latest/open feed collection job",
    )
    feed_current.add_argument("--source", default=None)

    session_parser = sub.add_parser(
        "session",
        help="Inspect Fnguide account session (read-only)",
    )
    session_sub = session_parser.add_subparsers(dest="session_command")
    session_sub.add_parser("current", help="Show current DB session")
    session_sub.add_parser("history", help="Show recent session history")

    cdp_parser = sub.add_parser(
        "cdp",
        help="Remote-control open adhoc crawl via CDP",
    )
    cdp_sub = cdp_parser.add_subparsers(dest="cdp_command")
    cdp_sub.add_parser("status", help="Show CDP pages / active URL")
    cdp_goto = cdp_sub.add_parser("goto", help="Navigate active tab")
    cdp_goto.add_argument("--url", required=True)
    cdp_click = cdp_sub.add_parser("click", help="Click by text or selector")
    cdp_click.add_argument("--text", default=None)
    cdp_click.add_argument("--selector", default=None)
    cdp_fill = cdp_sub.add_parser("fill", help="Fill an input")
    cdp_fill.add_argument("--selector", required=True)
    cdp_fill.add_argument("--text", required=True)
    cdp_press = cdp_sub.add_parser("press", help="Press a key")
    cdp_press.add_argument("--key", required=True)
    cdp_press.add_argument("--selector", default=None)
    cdp_shot = cdp_sub.add_parser("screenshot", help="Capture active tab")
    cdp_shot.add_argument(
        "--out",
        type=Path,
        default=Path(".crawler/snapshots/cdp.png"),
    )
    cdp_eval = cdp_sub.add_parser("eval", help="Evaluate JS in active tab")
    cdp_eval.add_argument("--expr", required=True)

    status_parser = sub.add_parser(
        "status",
        help="(legacy) Read or write bot status.json",
    )
    status_sub = status_parser.add_subparsers(dest="status_command")
    status_get = status_sub.add_parser("get", help="Print current status")
    status_get.add_argument("--status", type=Path, default=DEFAULT_STATUS_PATH)
    status_set = status_sub.add_parser("set", help="Write a status payload")
    status_set.add_argument(
        "--state",
        required=True,
        choices=["idle", "logging_in", "active", "logging_out", "error"],
    )
    status_set.add_argument("--user-id", default=None)
    status_set.add_argument("--step", default=None)
    status_set.add_argument("--current-url", default=None)
    status_set.add_argument("--message", default=None)
    status_set.add_argument("--status", type=Path, default=DEFAULT_STATUS_PATH)
    status_clear = status_sub.add_parser("clear", help="Reset status to idle")
    status_clear.add_argument("--status", type=Path, default=DEFAULT_STATUS_PATH)

    args = parser.parse_args()
    command = args.command or "open-login"
    headless = getattr(args, "headless", False)

    if command == "open-login":
        open_login(headless=headless)
        return

    if command == "login":
        if not args.user_id or not args.password:
            parser.error(
                "login requires --user-id/--password or "
                "FNGUIDE_USER_ID/FNGUIDE_PASSWORD"
            )
        summary = login_and_capture(
            user_id=args.user_id,
            password=args.password,
            session_path=args.session,
            headless=headless,
            force_other_session=not args.no_force,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if command == "verify-session":
        result = verify_session(session_path=args.session, headless=headless)
        if args.session.exists():
            result["summary"] = session_summary(args.session)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if command == "crawl":
        crawl_command = args.crawl_command or "current"
        if crawl_command == "current":
            current = crawls_store.get_open_crawl()
            print(
                json.dumps(
                    current or {"state": "ended", "label": "종료", "crawl": None},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        if crawl_command == "run":
            if not args.user_id or not args.password:
                parser.error(
                    "crawl run requires --user-id/--password or "
                    "FNGUIDE_USER_ID/FNGUIDE_PASSWORD"
                )
            try:
                result = run_crawl(
                    user_id=args.user_id,
                    password=args.password,
                    ttl_seconds=args.ttl,
                    idle_seconds=args.idle,
                    headless=headless,
                    force_other_session=not args.no_force,
                    crawl_id=args.crawl_id,
                )
            except Exception as exc:
                print(json.dumps({"state": "error", "message": str(exc)}, ensure_ascii=False))
                raise SystemExit(1) from exc
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result.get("state") == "error":
                raise SystemExit(1)
            return
        parser.error(f"Unknown crawl command: {crawl_command}")

    if command == "feed":
        feed_command = args.feed_command or "current"
        if feed_command == "current":
            source = getattr(args, "source", None)
            open_job = collection_jobs_store.get_open_job(
                source=source, capability="feed"
            )
            latest = open_job or collection_jobs_store.get_latest_job(
                source=source, capability="feed"
            )
            print(
                json.dumps(
                    latest
                    or {
                        "state": "ended",
                        "label": "종료",
                        "job": None,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        if feed_command == "run":
            try:
                result = run_feed_job(args.job_id, max_pages=args.max_pages)
            except Exception as exc:
                print(
                    json.dumps(
                        {"state": "error", "message": str(exc)},
                        ensure_ascii=False,
                    )
                )
                raise SystemExit(1) from exc
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result.get("state") == "error":
                raise SystemExit(1)
            return
        parser.error(f"Unknown feed command: {feed_command}")

    if command == "session":
        session_command = args.session_command or "current"
        if session_command == "current":
            current = sessions_store.get_open_session()
            print(
                json.dumps(
                    current
                    or {"state": "ended", "label": "로그아웃됨", "session": None},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        if session_command == "history":
            print(
                json.dumps(
                    {"items": sessions_store.list_history(limit=50)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        parser.error(f"Unknown session command: {session_command}")

    if command == "cdp":
        cdp_command = args.cdp_command or "status"
        try:
            if cdp_command == "status":
                result = cdp_ops.cdp_status()
            elif cdp_command == "goto":
                result = cdp_ops.cdp_goto(args.url)
            elif cdp_command == "click":
                result = cdp_ops.cdp_click(text=args.text, selector=args.selector)
            elif cdp_command == "fill":
                result = cdp_ops.cdp_fill(selector=args.selector, text=args.text)
            elif cdp_command == "press":
                result = cdp_ops.cdp_press(key=args.key, selector=args.selector)
            elif cdp_command == "screenshot":
                result = cdp_ops.cdp_screenshot(out=args.out)
            elif cdp_command == "eval":
                result = cdp_ops.cdp_eval(args.expr)
            else:
                parser.error(f"Unknown cdp command: {cdp_command}")
        except Exception as exc:
            print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False))
            raise SystemExit(1) from exc
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if command == "status":
        status_command = args.status_command or "get"
        if status_command == "get":
            print(json.dumps(get_status(args.status), ensure_ascii=False, indent=2))
            return
        if status_command == "set":
            payload = set_status(
                state=args.state,
                user_id=args.user_id,
                step=args.step,
                current_url=args.current_url,
                message=args.message,
                path=args.status,
                keep_started_at=args.state != "idle",
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        if status_command == "clear":
            print(json.dumps(clear_status(args.status), ensure_ascii=False, indent=2))
            return
        parser.error(f"Unknown status command: {status_command}")

    parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
