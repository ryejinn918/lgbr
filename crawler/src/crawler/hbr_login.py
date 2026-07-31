"""HBR.org account login / logout via hub Sign In modal."""

from __future__ import annotations

import re
from pathlib import Path

from patchright.sync_api import Page

from crawler.session import LoginPageError, capture_login_failure

HUB_URL = "https://hbr.org/"
# Confirmed: /signin is 404; login is a modal opened from hub Sign In.
LOGIN_URL = HUB_URL


def is_login_url(url: str | None) -> bool:
    """hbr.org has no dedicated login path; modal lives on hub."""
    _ = url
    return False


def is_logged_in(page: Page) -> bool:
    """True when header Sign In is gone and account chrome is present."""
    try:
        url = (page.url or "").lower()
    except Exception:
        return False
    if "hbr.org" not in url:
        return False
    try:
        sign_in = page.locator("#sign-in-button-header")
        if sign_in.count() and sign_in.first.is_visible(timeout=500):
            return False
    except Exception:
        pass
    try:
        for label in ("Sign Out", "Account Settings", "My Library"):
            if page.get_by_text(label, exact=False).count() > 0:
                return True
        # Account settings link in chrome
        if page.locator('a[href*="/my-library/settings"]').count() > 0:
            # Only count as logged in if Sign In header is absent
            if page.locator("#sign-in-button-header").count() == 0:
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
        has_email = page.locator('input[name="emailAddress"]').count() > 0
    except Exception:
        has_email = False
    try:
        has_password = page.locator('input[name="password"]').count() > 0
    except Exception:
        has_password = False
    try:
        has_sign_in_header = page.locator("#sign-in-button-header").count() > 0
    except Exception:
        has_sign_in_header = False
    try:
        logged_in = is_logged_in(page)
    except Exception:
        logged_in = False
    return {
        "url": url,
        "title": title,
        "has_email": has_email,
        "has_password": has_password,
        "has_sign_in_header": has_sign_in_header,
        "logged_in": logged_in,
    }


def capture_hbr_org_login_failure(
    page: Page,
    directory: Path,
    *,
    prefix: str = "login-fail",
) -> dict:
    detail = capture_login_failure(page, directory, prefix=prefix)
    detail.update(login_diagnostics(page))
    return detail


def _open_sign_in_modal(page: Page) -> None:
    if page.locator('input[name="emailAddress"]').count() and page.locator(
        'input[name="emailAddress"]'
    ).first.is_visible(timeout=800):
        return
    btn = page.locator("#sign-in-button-header")
    if btn.count() == 0:
        btn = page.get_by_role("button", name="Sign In")
    btn.first.click(timeout=10_000)
    page.locator('input[name="emailAddress"]').first.wait_for(
        state="visible", timeout=20_000
    )


def login(
    page: Page,
    *,
    user_id: str,
    password: str,
    force_other_session: bool = True,
    login_url: str = LOGIN_URL,
) -> dict:
    """Open hub Sign In modal, fill email/password, submit.

    Returns ``{"conflict_accepted": bool, "url": str, "logged_in": bool}``.
    """
    _ = force_other_session

    if is_logged_in(page):
        return {"conflict_accepted": False, "url": page.url, "logged_in": True}

    page.goto(login_url or HUB_URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(1500)

    if is_logged_in(page):
        return {"conflict_accepted": False, "url": page.url, "logged_in": True}

    try:
        _open_sign_in_modal(page)
    except Exception as exc:
        detail = login_diagnostics(page)
        raise LoginPageError(
            f"Sign In modal not found at {detail.get('url')}",
            detail=detail,
        ) from exc

    # React controlled inputs: click + type (fill alone can leave empty state).
    email = page.locator('input[name="emailAddress"]').first
    email.click()
    email.fill("")
    email.press_sequentially(user_id, delay=40)
    page.wait_for_timeout(400)
    pw = page.locator('input[name="password"]').first
    pw.click()
    pw.fill("")
    pw.press_sequentially(password, delay=40)
    page.wait_for_timeout(600)

    submit = page.locator("[role=dialog] button[type=submit]")
    if submit.count() == 0:
        submit = page.get_by_role("button", name="Sign In")
    try:
        page.wait_for_function(
            """() => {
              const btns = [...document.querySelectorAll(
                '[role=dialog] button[type=submit], button[type=submit]'
              )];
              return btns.some(
                (b) => !b.disabled && /sign in/i.test(b.innerText || '')
              );
            }""",
            timeout=10_000,
        )
    except Exception:
        pass
    submit.first.click(timeout=10_000)
    page.wait_for_timeout(3500)

    # Surface auth errors without retrying (site rate-limits attempts).
    modal_text = ""
    try:
        dlg = page.locator("[role=dialog]")
        if dlg.count():
            modal_text = (dlg.first.inner_text(timeout=2000) or "").strip()
    except Exception:
        modal_text = ""
    if re.search(
        r"invalid email and password|incorrect|try again|tries left",
        modal_text,
        re.I,
    ):
        detail = login_diagnostics(page)
        detail["modal_error"] = modal_text[:400]
        raise LoginPageError(
            "Login rejected by HBR (invalid credentials or captcha)",
            detail=detail,
        )

    try:
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
    except Exception:
        pass
    page.wait_for_timeout(2000)

    if "hbr.org" not in (page.url or "").lower():
        page.goto(HUB_URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(1500)

    logged_in = is_logged_in(page)
    if not logged_in:
        page.goto(HUB_URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(2000)
        logged_in = is_logged_in(page)

    if not logged_in:
        detail = login_diagnostics(page)
        detail["modal_text"] = modal_text[:400]
        raise LoginPageError(
            f"Login failed; Sign In still present at {page.url}",
            detail=detail,
        )

    return {
        "conflict_accepted": False,
        "url": page.url,
        "logged_in": True,
    }


def logout(page: Page) -> None:
    """Sign out via visible Sign Out control if present."""
    page.goto(HUB_URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(1000)
    if not is_logged_in(page):
        return

    # Open account menu if needed, then Sign Out.
    for label in ("Sign Out", "Log Out"):
        loc = page.get_by_role("button", name=label)
        if loc.count() == 0:
            loc = page.get_by_role("link", name=label)
        if loc.count() == 0:
            loc = page.get_by_text(label, exact=False)
        if loc.count() == 0:
            continue
        try:
            loc.first.click(timeout=5_000)
            page.wait_for_timeout(1500)
            break
        except Exception:
            continue

    page.goto(HUB_URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(1000)
    if is_logged_in(page):
        raise RuntimeError(f"Logout failed; still logged in at {page.url}")
