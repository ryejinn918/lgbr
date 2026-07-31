"""Nikkei ID (www.nikkei.com) two-step login / logout."""

from __future__ import annotations

from pathlib import Path

from patchright.sync_api import Page

from crawler.session import LoginPageError, capture_login_failure

LOGIN_URL = "https://www.nikkei.com/login"
HUB_URL = "https://www.nikkei.com/"


def is_login_url(url: str | None) -> bool:
    u = (url or "").lower()
    return (
        "/login" in u
        or "id.nikkei.com" in u
        or "auth" in u and "nikkei.com" in u
    ) and "www.nikkei.com/article" not in u


def is_logged_in(page: Page) -> bool:
    """True when chrome no longer offers a primary ログイン entry."""
    try:
        url = (page.url or "").lower()
    except Exception:
        return False
    if "id.nikkei.com" in url and "/login" in url:
        return False
    try:
        # Logged-out header exposes an account nav link to /login.
        login_links = page.locator('a[href="/login"], a[href*="nikkei.com/login"]')
        for i in range(min(login_links.count(), 6)):
            link = login_links.nth(i)
            try:
                if not link.is_visible():
                    continue
                text = (link.inner_text() or "").strip()
            except Exception:
                continue
            if text == "ログイン" or text == "ログインする":
                return False
        # Positive signals
        for label in ("ログアウト", "マイページ", "アカウント設定", "登録情報"):
            if page.get_by_text(label, exact=False).count() > 0:
                return True
        # If we are on www.nikkei.com without a visible ログイン CTA, treat as in.
        if "www.nikkei.com" in url and login_links.count() == 0:
            return True
    except Exception:
        return False
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
        logged_in = is_logged_in(page)
    except Exception:
        logged_in = False
    return {
        "url": url,
        "title": title,
        "has_email": has_email,
        "has_password": has_password,
        "logged_in": logged_in,
    }


def capture_nikkei_login_failure(
    page: Page,
    directory: Path,
    *,
    prefix: str = "login-fail",
) -> dict:
    detail = capture_login_failure(page, directory, prefix=prefix)
    detail.update(login_diagnostics(page))
    return detail


def login(
    page: Page,
    *,
    user_id: str,
    password: str,
    force_other_session: bool = True,
    login_url: str = LOGIN_URL,
) -> dict:
    """Two-step Nikkei ID: email → 次に進む → password → submit."""
    _ = force_other_session  # reserved (device/session prompts)

    if is_logged_in(page):
        return {"conflict_accepted": False, "url": page.url, "logged_in": True}

    page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(800)

    if is_logged_in(page):
        return {"conflict_accepted": False, "url": page.url, "logged_in": True}

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

    pw.first.fill(password)
    submitted = False
    for label in ("ログイン", "次に進む", "ログインする", "Sign in"):
        btn = page.get_by_role("button", name=label)
        if btn.count() == 0:
            continue
        btn.first.click()
        submitted = True
        break
    if not submitted:
        page.locator('button[type="submit"]').first.click()

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)
    try:
        page.wait_for_url(
            lambda url: "www.nikkei.com" in (url or "")
            and "id.nikkei.com" not in (url or ""),
            timeout=30_000,
        )
    except Exception:
        pass

    # Land on hub if still on ID host without clear failure.
    if "id.nikkei.com" in (page.url or "") and not is_logged_in(page):
        page.goto(HUB_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1000)

    logged_in = is_logged_in(page)
    if not logged_in:
        detail = login_diagnostics(page)
        raise LoginPageError(
            f"Login failed; not logged in at {page.url}",
            detail=detail,
        )
    return {
        "conflict_accepted": False,
        "url": page.url,
        "logged_in": True,
    }


def logout(page: Page) -> None:
    """Best-effort logout via account UI or known lounge URL."""
    for url in (
        "https://www.nikkei.com/logout",
        "https://id.nikkei.com/logout",
        "https://www.nikkei.com/lounge/member/logout/",
    ):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(600)
        except Exception:
            continue
        if not is_logged_in(page):
            return

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
    if is_logged_in(page):
        # Soft-fail: clear cookies via hub login CTA presence after goto hub.
        page.goto(HUB_URL, wait_until="domcontentloaded", timeout=60_000)
        if is_logged_in(page):
            raise RuntimeError(f"Logout failed; still logged in at {page.url}")
