"""Nikkei xTECH (日経クロステック) login via BP SSO → 日経ID (OTP-aware)."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from patchright.sync_api import Page

from crawler.session import LoginPageError, capture_login_failure

HUB_URL = "https://xtech.nikkei.com/"


def bp_sso_login_url(*, return_url: str = HUB_URL) -> str:
    """Build BP SSO entry that lands on id.nikkei.com for xTECH (ts=nxt)."""
    ru = quote(return_url, safe="")
    cookie_ru = quote(f"https://bpsso.nikkei.com/ep/cookie/?ru={ru}", safe="")
    return f"https://bpsso.nikkei.com/ep/auth/prev/?ts=nxt&ru={cookie_ru}"


LOGIN_URL = bp_sso_login_url()

DEFAULT_OTP_WAIT_SECONDS = int(
    os.environ.get("NIKKEIXTECH_OTP_WAIT_SECONDS", "300")
)


def is_login_url(url: str | None) -> bool:
    u = (url or "").lower()
    if "xtech.nikkei.com" in u and "/atcl/" in u:
        return False
    return (
        "id.nikkei.com" in u
        or "bpsso.nikkei.com" in u
        or ("/login" in u and "nikkei.com" in u)
    )


def is_otp_challenge(page: Page) -> bool:
    try:
        url = (page.url or "").lower()
    except Exception:
        return False
    if "/login/challenge" in url:
        return True
    try:
        text = page.locator("body").inner_text(timeout=2_000) or ""
    except Exception:
        return False
    return "ワンタイムパスワード" in text


def is_logged_in(page: Page) -> bool:
    """True when xTECH chrome shows logout (ログイン alone is not enough)."""
    try:
        url = (page.url or "").lower()
    except Exception:
        return False
    if "id.nikkei.com" in url and "/login" in url:
        return False
    if is_otp_challenge(page):
        return False
    try:
        if page.get_by_text("ログアウト", exact=False).count() > 0:
            return True
    except Exception:
        pass
    return False


def login_diagnostics(page: Page) -> dict:
    try:
        title = page.title()
    except Exception:
        title = None
    try:
        url = page.url
    except Exception:
        url = None
    try:
        has_email = page.locator('input[type="email"], input[name="email"]').count() > 0
    except Exception:
        has_email = False
    try:
        has_password = page.locator('input[type="password"]').count() > 0
    except Exception:
        has_password = False
    try:
        otp = is_otp_challenge(page)
    except Exception:
        otp = False
    try:
        logged_in = is_logged_in(page)
    except Exception:
        logged_in = False
    return {
        "url": url,
        "title": title,
        "has_email": has_email,
        "has_password": has_password,
        "otp_challenge": otp,
        "logged_in": logged_in,
    }


def capture_nikkeixtech_login_failure(
    page: Page,
    directory: Path,
    *,
    prefix: str = "login-fail",
) -> dict:
    detail = capture_login_failure(page, directory, prefix=prefix)
    detail.update(login_diagnostics(page))
    return detail


def wait_for_otp_or_login(
    page: Page,
    *,
    timeout_seconds: int = DEFAULT_OTP_WAIT_SECONDS,
    hub_url: str = HUB_URL,
    on_wait: Callable[[Page], None] | None = None,
) -> bool:
    """Poll until logged in (user may enter OTP via CDP). Returns logged_in."""
    deadline = time.time() + max(timeout_seconds, 1)
    while time.time() < deadline:
        if is_logged_in(page):
            return True
        if not is_otp_challenge(page) and not is_login_url(page.url):
            # Cookie redirect may land on hub before chrome updates.
            try:
                page.goto(hub_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(800)
            except Exception:
                pass
            if is_logged_in(page):
                return True
        if on_wait is not None:
            try:
                on_wait(page)
            except Exception:
                pass
        page.wait_for_timeout(1_000)
    return is_logged_in(page)


def login(
    page: Page,
    *,
    user_id: str,
    password: str,
    force_other_session: bool = True,
    login_url: str = LOGIN_URL,
    hub_url: str = HUB_URL,
    otp_wait_seconds: int = DEFAULT_OTP_WAIT_SECONDS,
    on_otp_wait: Callable[[Page], None] | None = None,
) -> dict:
    """BP SSO → email → 次に進む → password → 次に進む → optional OTP wait."""
    _ = force_other_session

    if not is_login_url(page.url) or "xtech.nikkei.com" in (page.url or ""):
        if is_logged_in(page):
            return {
                "conflict_accepted": False,
                "url": page.url,
                "logged_in": True,
                "otp_waited": False,
            }

    page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(800)

    if is_logged_in(page):
        return {
            "conflict_accepted": False,
            "url": page.url,
            "logged_in": True,
            "otp_waited": False,
        }

    email = page.locator('input[type="email"], input[name="email"]')
    try:
        email.first.wait_for(state="visible", timeout=30_000)
    except Exception as exc:
        detail = login_diagnostics(page)
        raise LoginPageError(
            f"Login email field not found at {detail.get('url')}",
            detail=detail,
        ) from exc

    email.first.fill(user_id)
    next_btn = page.get_by_role("button", name="次に進む")
    if next_btn.count() == 0:
        next_btn = page.locator('button[type="submit"]')
    next_btn.first.click()
    page.wait_for_timeout(1500)

    pw = page.locator('input[type="password"]')
    try:
        pw.first.wait_for(state="visible", timeout=20_000)
    except Exception as exc:
        detail = login_diagnostics(page)
        raise LoginPageError(
            f"Login password field not found at {detail.get('url')}",
            detail=detail,
        ) from exc

    # Prefer the visible password field (email may still be on page).
    filled = False
    for i in range(pw.count()):
        el = pw.nth(i)
        try:
            if el.is_visible():
                el.fill(password)
                filled = True
                break
        except Exception:
            continue
    if not filled:
        pw.first.fill(password)

    submitted = False
    for label in ("次に進む", "ログイン", "ログインする", "Sign in"):
        btn = page.get_by_role("button", name=label)
        if btn.count() == 0:
            continue
        try:
            if btn.first.is_visible():
                btn.first.click()
                submitted = True
                break
        except Exception:
            continue
    if not submitted:
        page.locator('button[type="submit"]').first.click()

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)

    otp_waited = False
    if is_otp_challenge(page):
        otp_waited = True
        if on_otp_wait is not None:
            try:
                on_otp_wait(page)
            except Exception:
                pass
        ok = wait_for_otp_or_login(
            page,
            timeout_seconds=otp_wait_seconds,
            hub_url=hub_url,
            on_wait=on_otp_wait,
        )
        if not ok:
            detail = login_diagnostics(page)
            detail["otp_wait_seconds"] = otp_wait_seconds
            raise LoginPageError(
                "Login waiting for one-time password (OTP); "
                f"enter code via CDP within {otp_wait_seconds}s "
                f"(still at {page.url})",
                detail=detail,
            )

    if not is_logged_in(page):
        try:
            page.goto(hub_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(1000)
        except Exception:
            pass

    logged_in = is_logged_in(page)
    if not logged_in:
        detail = login_diagnostics(page)
        detail["otp_waited"] = otp_waited
        raise LoginPageError(
            f"Login failed; not logged in at {page.url}",
            detail=detail,
        )
    return {
        "conflict_accepted": False,
        "url": page.url,
        "logged_in": True,
        "otp_waited": otp_waited,
    }


def logout(page: Page) -> None:
    """Best-effort logout via known endpoints or chrome link."""
    for url in (
        "https://xtech.nikkei.com/",
        "https://id.nikkei.com/logout",
        "https://www.nikkei.com/logout",
    ):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(500)
        except Exception:
            continue
        link = page.get_by_role("link", name="ログアウト")
        if link.count() == 0:
            link = page.get_by_text("ログアウト", exact=False)
        if link.count() > 0:
            try:
                link.first.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(500)
            except Exception:
                pass
        if not is_logged_in(page):
            return
    page.goto(HUB_URL, wait_until="domcontentloaded", timeout=60_000)
    if is_logged_in(page):
        raise RuntimeError(f"Logout failed; still logged in at {page.url}")
