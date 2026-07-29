"""PwC browser session — no account login; CDP-friendly hold for adhoc analysis."""

from __future__ import annotations

import os
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from patchright.sync_api import BrowserContext, Page

from crawler.browser import launch_context

DEFAULT_TTL_SECONDS = int(os.environ.get("PWC_SESSION_TTL_SECONDS", "28800"))
DEFAULT_IDLE_SECONDS = int(os.environ.get("PWC_SESSION_IDLE_SECONDS", "3600"))
DEFAULT_START_URL = os.environ.get(
    "PWC_START_URL",
    "https://www.pwc.com/gx/en/research-insights.html",
)
PROFILE_DIR = Path(".crawler/browser-profile-pwc")


@dataclass
class PwcSession:
    """Launch Chrome, open PwC, keep alive until stop/idle/ttl.

    Uses the same Patchright ``launch_context`` + CDP path as FnGuide adhoc,
    but never touches fnguide login / ``fnguide_sessions``.
    """

    ttl_seconds: int = DEFAULT_TTL_SECONDS
    idle_seconds: int = DEFAULT_IDLE_SECONDS
    headless: bool | None = True
    cdp_port: int | None = None
    downloads_path: Path | None = None
    start_url: str = DEFAULT_START_URL

    page: Page | None = None
    session_id: str | None = None  # always None; crawl attach skipped
    started_at: datetime | None = None
    last_used_at: datetime | None = None
    _context: BrowserContext | None = None
    _stack: ExitStack | None = field(default=None, repr=False)
    _stop_requested: bool = False

    def start(self) -> dict[str, Any]:
        if self.page is not None:
            return {"url": self.page.url, "state": "active"}

        self._stack = ExitStack()
        self._context = self._stack.enter_context(
            launch_context(
                headless=self.headless,
                user_data_dir=PROFILE_DIR,
                cdp_port=self.cdp_port,
                downloads_path=self.downloads_path,
            )
        )
        self.page = (
            self._context.pages[0] if self._context.pages else self._context.new_page()
        )
        self.page.goto(self.start_url, wait_until="domcontentloaded")
        now = datetime.now(timezone.utc)
        self.started_at = now
        self.last_used_at = now
        return {"url": self.page.url, "state": "active", "start_url": self.start_url}

    def touch(
        self,
        *,
        current_url: str | None = None,
        step: str | None = None,
    ) -> dict[str, Any]:
        _ = current_url, step
        if self.page is None:
            raise RuntimeError("PwC session is not started")
        self.last_used_at = datetime.now(timezone.utc)
        return {"url": self.page.url, "last_used_at": self.last_used_at.isoformat()}

    def request_stop(self) -> None:
        self._stop_requested = True

    def poll_should_stop(self) -> str | None:
        if self.page is None:
            return "shutdown"
        if self._stop_requested:
            return "manual"
        now = datetime.now(timezone.utc)
        if self.started_at and (now - self.started_at).total_seconds() >= self.ttl_seconds:
            return "ttl"
        if (
            self.last_used_at
            and (now - self.last_used_at).total_seconds() >= self.idle_seconds
        ):
            return "idle"
        return None

    def stop(self, end_reason: str, message: str | None = None) -> dict[str, Any]:
        _ = end_reason
        self._close_browser()
        return {"state": "ended", "label": "종료", "message": message}

    def _close_browser(self) -> None:
        if self._stack is not None:
            try:
                self._stack.close()
            except Exception:
                pass
        self._stack = None
        self._context = None
        self.page = None

    def __enter__(self) -> PwcSession:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.page is None:
            return
        if exc is not None:
            self.stop("error", message=str(exc))
        else:
            self.stop("shutdown")
