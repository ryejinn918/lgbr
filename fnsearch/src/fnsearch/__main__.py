"""CLI entry: python -m fnsearch"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from fnsearch.browser import open_login
from fnsearch.session import (
    DEFAULT_SESSION_PATH,
    hold_session,
    login_and_capture,
    session_summary,
    verify_session,
)
from fnsearch.status import DEFAULT_STATUS_PATH, clear_status, get_status, set_status


def _add_headless(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium without a visible window",
    )


def main() -> None:
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

    hold_parser = sub.add_parser(
        "hold",
        help="Log in, publish status heartbeats, then logout",
    )
    _add_headless(hold_parser)
    hold_parser.add_argument("--user-id", default=os.environ.get("FNGUIDE_USER_ID"))
    hold_parser.add_argument("--password", default=os.environ.get("FNGUIDE_PASSWORD"))
    hold_parser.add_argument("--seconds", type=int, default=60)
    hold_parser.add_argument("--status", type=Path, default=DEFAULT_STATUS_PATH)
    hold_parser.add_argument(
        "--no-force",
        action="store_true",
        help="Do not confirm the single-session conflict dialog",
    )

    status_parser = sub.add_parser(
        "status",
        help="Read or write bot status.json (no Fnguide connection)",
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

    if command == "hold":
        if not args.user_id or not args.password:
            parser.error(
                "hold requires --user-id/--password or "
                "FNGUIDE_USER_ID/FNGUIDE_PASSWORD"
            )
        result = hold_session(
            user_id=args.user_id,
            password=args.password,
            seconds=args.seconds,
            headless=headless,
            force_other_session=not args.no_force,
            status_path=args.status,
        )
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
