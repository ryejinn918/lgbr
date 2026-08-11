"""Maintain a Nikkei (www.nikkei.com) account session until idle/ttl/manual/external end."""

from __future__ import annotations

import os
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from patchright.sync_api import BrowserContext, Page

from crawler import sessions_store
from crawler.browser import launch_context
from crawler.nikkei_login import (
    HUB_URL,
    LOGIN_URL,
    capture_nikkei_login_failure,
    is_logged_in,
    login,
    logout,
)
from crawler.paths import browser_profile_dir, downloads_dir_root
from crawler.session import LoginPageError
from crawler.sources.registry import get_source

DEFAULT_TTL_SECONDS = int(
    os.environ.get("NIKKEI_SESSION_TTL_SECONDS")
    or os.environ.get("FNGUIDE_SESSION_TTL_SECONDS", "28800")
)
DEFAULT_IDLE_SECONDS = int(
    os.environ.get("NIKKEI_SESSION_IDLE_SECONDS")
    or os.environ.get("FNGUIDE_SESSION_IDLE_SECONDS", "900")
)

DEFAULT_PROFILE_DIR = browser_profile_dir("browser-profile-nikkei")


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value)


@dataclass
class NikkeiSession:
    user_id: str
    password: str
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    idle_seconds: int = DEFAULT_IDLE_SECONDS
    headless: bool | None = True
    force_other_session: bool = True
    cdp_port: int | None = None
    downloads_path: Path | None = None
    profile_dir: Path | None = None
    login_url: str = LOGIN_URL
    hub_url: str = HUB_URL

    session_id: str | None = None
    page: Page | None = None
    conflict_accepted: bool = False
    _context: BrowserContext | None = None
    _stack: ExitStack | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.profile_dir is None:
            self.profile_dir = DEFAULT_PROFILE_DIR
        try:
            src = get_source("nikkei")
            if src.login_url:
                self.login_url = src.login_url
            if src.hub_url:
                self.hub_url = src.hub_url
        except ValueError:
            pass

    def start(self) -> dict[str, Any]:
        if self.session_id and self.page:
            return sessions_store.get_session(self.session_id) or {}

        row = sessions_store.create_session(
            source="nikkei",
            fnguide_user_id=self.user_id,
            ttl_seconds=self.ttl_seconds,
        )
        self.session_id = row["id"]
        try:
            self._stack = ExitStack()
            self._context = self._stack.enter_context(
                launch_context(
                    headless=self.headless,
                    user_data_dir=self.profile_dir,
                    cdp_port=self.cdp_port,
                    downloads_path=self.downloads_path,
                )
            )
            self.page = (
                self._context.pages[0]
                if self._context.pages
                else self._context.new_page()
            )
            self.page.goto(
                self.login_url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            if is_logged_in(self.page):
                self.conflict_accepted = False
            else:
                result = login(
                    self.page,
                    user_id=self.user_id,
                    password=self.password,
                    force_other_session=self.force_other_session,
                    login_url=self.login_url,
                )
                self.conflict_accepted = bool(result.get("conflict_accepted"))
            if not is_logged_in(self.page):
                self.page.goto(
                    self.hub_url,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
            if not is_logged_in(self.page):
                raise LoginPageError(
                    f"Login failed; no logged-in chrome at {self.page.url}",
                    detail={"url": self.page.url, "logged_in": False},
                )
            if self.hub_url and "www.nikkei.com" not in (self.page.url or ""):
                self.page.goto(
                    self.hub_url,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
            return sessions_store.mark_logged_in(
                self.session_id,
                current_url=self.page.url,
                step="ready",
            )
        except Exception as exc:
            detail: dict[str, Any] = {}
            if isinstance(exc, LoginPageError):
                detail = dict(exc.detail)
            if self.page is not None:
                try:
                    artifact_dir = self.downloads_path or downloads_dir_root() / (
                        self.session_id or "login-fail"
                    )
                    captured = capture_nikkei_login_failure(self.page, artifact_dir)
                    detail = {**captured, **detail}
                except Exception as cap_exc:
                    detail["capture_error"] = str(cap_exc)
            fail_msg = str(exc)
            if detail.get("url"):
                fail_msg = f"{fail_msg} | url={detail.get('url')}"
            if detail.get("screenshot"):
                fail_msg = f"{fail_msg} | screenshot={detail.get('screenshot')}"
            try:
                sessions_store.mark_login_failed(self.session_id, fail_msg)
            except Exception as db_exc:
                self._close_browser()
                self.session_id = None
                raise RuntimeError(
                    f"Login failed ({fail_msg}); also failed to mark session error: {db_exc}"
                ) from db_exc
            self._close_browser()
            self.session_id = None
            raise LoginPageError(fail_msg, detail=detail) from exc

    def touch(
        self,
        *,
        current_url: str | None = None,
        step: str | None = None,
    ) -> dict[str, Any]:
        if not self.session_id or not self.page:
            raise RuntimeError("Session is not started")
        return sessions_store.touch(
            self.session_id,
            current_url=current_url or self.page.url,
            step=step,
        )

    def poll_should_stop(self) -> str | None:
        if not self.session_id or not self.page:
            return "shutdown"
        row = sessions_store.get_session(self.session_id)
        if not row or row.get("ended_at"):
            return "shutdown"
        if row.get("logout_requested_at"):
            return "manual"
        now = datetime.now(timezone.utc)
        lease_until = _parse_dt(row.get("lease_until"))
        last_used = _parse_dt(row.get("last_used_at"))
        if lease_until and now >= lease_until:
            return "ttl"
        if last_used and (now - last_used).total_seconds() >= self.idle_seconds:
            return "idle"
        if not is_logged_in(self.page):
            return "external"
        return None

    def stop(self, end_reason: str, message: str | None = None) -> dict[str, Any]:
        if not self.session_id:
            return {"state": "ended", "label": "로그아웃됨"}
        session_id = self.session_id
        row: dict[str, Any] | None = None
        try:
            if self.page and end_reason != "external":
                try:
                    sessions_store.begin_logout(session_id)
                except Exception:
                    pass
                if is_logged_in(self.page):
                    logout(self.page)
            event = "external_logout" if end_reason == "external" else None
            row = sessions_store.end_session(
                session_id,
                end_reason=end_reason,
                message=message,
                event=event,
            )
        except Exception as exc:
            try:
                row = sessions_store.end_session(
                    session_id,
                    end_reason="error",
                    message=str(exc),
                    event="error",
                )
            except Exception as db_exc:
                self._close_browser()
                self.session_id = None
                raise RuntimeError(
                    f"Session stop failed ({exc}); cannot mark error in DB: {db_exc}"
                ) from db_exc
        finally:
            self._close_browser()
            self.session_id = None
        return row or {"state": "ended", "label": "로그아웃됨"}

    def _close_browser(self) -> None:
        if self._stack is not None:
            try:
                self._stack.close()
            except Exception:
                pass
        self._stack = None
        self._context = None
        self.page = None

    def __enter__(self) -> NikkeiSession:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.session_id is None:
            return
        if exc is not None:
            self.stop("error", message=str(exc))
        else:
            self.stop("shutdown")
