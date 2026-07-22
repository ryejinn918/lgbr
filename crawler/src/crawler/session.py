"""Login, logout, and session run lifecycle for Fnguide."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from patchright.sync_api import Browser, BrowserContext, Page

from crawler.browser import LOGIN_URL, launch_browser, launch_context, new_human_context
from crawler.status import DEFAULT_STATUS_PATH, clear_status, set_status

DEFAULT_SESSION_PATH = Path(".crawler/session.json")
SESSION_CONFLICT_TITLE = "이미 로그인된 다른 기기가 있습니다."


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dismiss_session_conflict(page: Page, *, timeout_ms: int = 5_000) -> bool:
    """Click confirm if the single-session conflict dialog appears."""
    title = page.get_by_text(SESSION_CONFLICT_TITLE, exact=False)
    try:
        title.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        return False

    confirm = page.get_by_role("button", name="확인")
    if confirm.count() == 0:
        confirm = page.locator("button", has_text="확인")
    confirm.first.click()
    return True


def _is_logged_in(page: Page) -> bool:
    url = page.url.lower()
    if "/users/login" in url:
        return False
    logout = page.get_by_text("로그아웃", exact=False)
    return logout.count() > 0


def login(
    page: Page,
    *,
    user_id: str,
    password: str,
    force_other_session: bool = True,
) -> Page:
    """Fill credentials, submit login, and optionally accept session conflict."""
    if "/users/login" not in page.url.lower():
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

    page.locator("#userId").fill(user_id)
    page.locator("#userPw").fill(password)
    page.locator("#loginBtn").click()

    if force_other_session:
        _dismiss_session_conflict(page)

    page.wait_for_load_state("domcontentloaded")
    try:
        page.wait_for_url(lambda url: "/Users/Login" not in url, timeout=15_000)
    except Exception:
        if force_other_session:
            _dismiss_session_conflict(page, timeout_ms=2_000)
            page.wait_for_url(lambda url: "/Users/Login" not in url, timeout=15_000)

    return page


def logout(page: Page) -> None:
    """Click the header logout control and wait until logged out."""
    link = page.get_by_role("link", name="로그아웃")
    if link.count() == 0:
        link = page.get_by_text("로그아웃", exact=False)
    if link.count() == 0:
        raise RuntimeError("Logout control not found")
    link.first.click()
    page.wait_for_load_state("domcontentloaded")
    try:
        page.wait_for_url(lambda url: "/Users/Login" in url, timeout=10_000)
    except Exception:
        if _is_logged_in(page):
            raise RuntimeError(f"Logout failed; still logged in at {page.url}") from None


def capture_session(context: BrowserContext, path: Path = DEFAULT_SESSION_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
    return path


def load_session(
    browser: Browser,
    path: Path = DEFAULT_SESSION_PATH,
) -> BrowserContext:
    if not path.exists():
        raise FileNotFoundError(f"Session file not found: {path}")
    from crawler.browser import human_context_options

    return browser.new_context(**human_context_options(), storage_state=str(path))


def session_summary(path: Path = DEFAULT_SESSION_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    cookies = data.get("cookies", [])
    origins = data.get("origins", [])
    return {
        "path": str(path),
        "cookie_count": len(cookies),
        "cookie_names": sorted({c.get("name", "") for c in cookies}),
        "origin_count": len(origins),
        "origins": [o.get("origin") for o in origins],
    }


@dataclass
class SessionHandle:
    page: Page
    user_id: str
    status_path: Path

    def heartbeat(
        self,
        *,
        current_url: str | None = None,
        step: str | None = None,
        message: str | None = None,
    ) -> None:
        set_status(
            state="active",
            user_id=self.user_id,
            current_url=current_url or self.page.url,
            step=step,
            message=message,
            path=self.status_path,
        )


@contextmanager
def SessionRun(
    *,
    user_id: str,
    password: str,
    headless: bool = True,
    force_other_session: bool = True,
    status_path: Path = DEFAULT_STATUS_PATH,
) -> Iterator[SessionHandle]:
    """Login, yield a handle for work, then always attempt logout and clear status."""
    set_status(
        state="logging_in",
        user_id=user_id,
        started_at=_now_iso(),
        step="login",
        path=status_path,
        keep_started_at=False,
    )
    with launch_context(headless=headless) as context:
        page = context.pages[0] if context.pages else context.new_page()
        handle = SessionHandle(page=page, user_id=user_id, status_path=status_path)
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            login(
                page,
                user_id=user_id,
                password=password,
                force_other_session=force_other_session,
            )
            if not _is_logged_in(page) and "/users/login" in page.url.lower():
                raise RuntimeError(f"Login failed; still on {page.url}")

            set_status(
                state="active",
                user_id=user_id,
                current_url=page.url,
                step="ready",
                path=status_path,
            )
            yield handle
        except Exception as exc:
            set_status(
                state="error",
                user_id=user_id,
                current_url=page.url if page else None,
                step="error",
                message=str(exc),
                path=status_path,
            )
            raise
        finally:
            try:
                set_status(
                    state="logging_out",
                    user_id=user_id,
                    current_url=page.url,
                    step="logout",
                    path=status_path,
                )
                if _is_logged_in(page):
                    logout(page)
            except Exception as logout_exc:
                set_status(
                    state="error",
                    user_id=user_id,
                    current_url=getattr(page, "url", None),
                    step="logout",
                    message=str(logout_exc),
                    path=status_path,
                )
            else:
                clear_status(path=status_path)


def hold_session(
    *,
    user_id: str,
    password: str,
    seconds: int = 60,
    headless: bool = True,
    force_other_session: bool = True,
    status_path: Path = DEFAULT_STATUS_PATH,
) -> dict:
    """Stay logged in for N seconds while publishing heartbeats, then logout."""
    with SessionRun(
        user_id=user_id,
        password=password,
        headless=headless,
        force_other_session=force_other_session,
        status_path=status_path,
    ) as session:
        deadline = time.monotonic() + max(seconds, 0)
        while True:
            session.heartbeat(current_url=session.page.url, step="hold")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(2.0, remaining))
    return {"held_seconds": seconds, "status": "idle"}


def login_and_capture(
    *,
    user_id: str,
    password: str,
    session_path: Path = DEFAULT_SESSION_PATH,
    headless: bool = True,
    force_other_session: bool = True,
) -> dict:
    """Debug helper: login and persist storage_state (not the default workflow)."""
    with launch_browser(headless=headless) as browser:
        context = new_human_context(browser)
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        login(
            page,
            user_id=user_id,
            password=password,
            force_other_session=force_other_session,
        )
        if not _is_logged_in(page) and "/users/login" in page.url.lower():
            raise RuntimeError(f"Login failed; still on {page.url}")

        saved = capture_session(context, session_path)
        summary = session_summary(saved)
        summary["final_url"] = page.url
        summary["logged_in"] = _is_logged_in(page)
        return summary


def verify_session(
    *,
    session_path: Path = DEFAULT_SESSION_PATH,
    headless: bool = True,
) -> dict:
    """Debug helper: open the site with a saved session."""
    with launch_browser(headless=headless) as browser:
        context = load_session(browser, session_path)
        page = context.new_page()
        page.goto("https://www.fnguide.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(1_000)
        logged_in = _is_logged_in(page)
        return {
            "path": str(session_path),
            "url": page.url,
            "logged_in": logged_in,
            "title": page.title(),
        }
