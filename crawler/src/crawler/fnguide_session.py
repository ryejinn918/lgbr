"""Maintain an Fnguide account session until idle/ttl/manual/external end."""

from __future__ import annotations

import os
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from patchright.sync_api import BrowserContext, Page

from crawler import sessions_store
from crawler.browser import LOGIN_URL, launch_context
from crawler.session import _is_logged_in, login, logout

DEFAULT_TTL_SECONDS = int(os.environ.get("FNGUIDE_SESSION_TTL_SECONDS", "28800"))
DEFAULT_IDLE_SECONDS = int(os.environ.get("FNGUIDE_SESSION_IDLE_SECONDS", "600"))


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value)


@dataclass
class FnguideSession:
    user_id: str
    password: str
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    idle_seconds: int = DEFAULT_IDLE_SECONDS
    headless: bool | None = True
    force_other_session: bool = True

    session_id: str | None = None
    page: Page | None = None
    _context: BrowserContext | None = None
    _stack: ExitStack | None = field(default=None, repr=False)

    def start(self) -> dict[str, Any]:
        if self.session_id and self.page:
            return sessions_store.get_session(self.session_id) or {}

        row = sessions_store.create_session(
            fnguide_user_id=self.user_id,
            ttl_seconds=self.ttl_seconds,
        )
        self.session_id = row["id"]
        try:
            self._stack = ExitStack()
            self._context = self._stack.enter_context(
                launch_context(headless=self.headless)
            )
            self.page = (
                self._context.pages[0]
                if self._context.pages
                else self._context.new_page()
            )
            self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
            login(
                self.page,
                user_id=self.user_id,
                password=self.password,
                force_other_session=self.force_other_session,
            )
            if not _is_logged_in(self.page) and "/users/login" in self.page.url.lower():
                raise RuntimeError(f"Login failed; still on {self.page.url}")
            return sessions_store.mark_logged_in(
                self.session_id,
                current_url=self.page.url,
                step="ready",
            )
        except Exception as exc:
            fail_msg = str(exc)
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
            raise

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
        """Return end_reason if the session should stop, else None."""
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
        if not _is_logged_in(self.page):
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
                    # Still attempt browser logout + terminal error write.
                    pass
                if _is_logged_in(self.page):
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

    def run_until_released(self, *, poll_seconds: float = 2.0) -> dict[str, Any]:
        """Start session and keep it until idle/ttl/manual/external.

        Idle countdown uses last_used_at from login/touch; this loop does not
        refresh last_used_at by itself.
        """
        self.start()
        try:
            while True:
                reason = self.poll_should_stop()
                if reason:
                    return self.stop(reason)
                time.sleep(max(poll_seconds, 0.5))
        except KeyboardInterrupt:
            return self.stop("shutdown", message="interrupted")
        except Exception as exc:
            return self.stop("error", message=str(exc))

    def _close_browser(self) -> None:
        if self._stack is not None:
            try:
                self._stack.close()
            except Exception:
                pass
        self._stack = None
        self._context = None
        self.page = None

    def __enter__(self) -> FnguideSession:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.session_id is None:
            return
        if exc is not None:
            self.stop("error", message=str(exc))
        else:
            self.stop("shutdown")
