"""HBR Korea account login / logout and single-session conflict handling."""

from __future__ import annotations

from pathlib import Path

from patchright.sync_api import Page

from crawler.session import LoginPageError, capture_login_failure

LOGIN_URL = "https://www.hbrkorea.com/member/login"
HUB_URL = "https://www.hbrkorea.com/"

# Phrases that may appear on the single-session conflict UI.
_CONFLICT_TEXT_HINTS = (
    "이미 로그인",
    "다른 기기",
    "다른 곳",
    "다른곳",
    "중복 로그인",
    "접속 중",
    "사용 중",
    "기존 접속",
    "기존 로그인",
    "강제 로그아웃",
    "로그아웃 하시겠습니까",
)

_CONFIRM_LABELS = (
    "확인",
    "예",
    "로그인",
    "계속",
    "로그인 계속",
    "기존 접속 종료",
    "강제 로그인",
    "네",
    "OK",
    "Yes",
)


def is_login_url(url: str | None) -> bool:
    u = (url or "").lower()
    return "/member/login" in u


def is_logged_in(page: Page) -> bool:
    """True when the page shows a logged-in chrome control."""
    if is_login_url(page.url):
        return False
    logout = page.get_by_text("로그아웃", exact=False)
    return logout.count() > 0


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
        has_email = page.locator("#email").count() > 0
    except Exception:
        has_email = False
    try:
        has_password = page.locator("#password").count() > 0
    except Exception:
        has_password = False
    try:
        has_logout = page.get_by_text("로그아웃", exact=False).count() > 0
    except Exception:
        has_logout = False
    try:
        logged_in = is_logged_in(page)
    except Exception:
        logged_in = False
    return {
        "url": url,
        "title": title,
        "has_email": has_email,
        "has_password": has_password,
        "has_logout": has_logout,
        "logged_in": logged_in,
    }


def capture_hbr_login_failure(
    page: Page,
    directory: Path,
    *,
    prefix: str = "login-fail",
) -> dict:
    detail = capture_login_failure(page, directory, prefix=prefix)
    detail.update(login_diagnostics(page))
    return detail


def _install_dialog_acceptor(page: Page) -> list[str]:
    """Accept native alert/confirm dialogs; record messages."""
    accepted: list[str] = []

    def _on_dialog(dialog: object) -> None:
        try:
            message = str(getattr(dialog, "message", "") or "")
        except Exception:
            message = ""
        accepted.append(message)
        try:
            dialog.accept()  # type: ignore[attr-defined]
        except Exception:
            try:
                dialog.dismiss()  # type: ignore[attr-defined]
            except Exception:
                pass

    page.on("dialog", _on_dialog)
    return accepted


def _looks_like_conflict_text(text: str) -> bool:
    return any(hint in text for hint in _CONFLICT_TEXT_HINTS)


def dismiss_session_conflict(page: Page, *, timeout_ms: int = 5_000) -> bool:
    """Click confirm if a single-session conflict modal/dialog is visible."""
    # 1) Text-hinted visible modal/body copy.
    for hint in _CONFLICT_TEXT_HINTS:
        locator = page.get_by_text(hint, exact=False)
        try:
            if locator.count() == 0:
                continue
            locator.first.wait_for(state="visible", timeout=timeout_ms)
        except Exception:
            continue
        for label in _CONFIRM_LABELS:
            btn = page.get_by_role("button", name=label)
            if btn.count() == 0:
                btn = page.locator("button, a, input[type=button], input[type=submit]", has_text=label)
            if btn.count() == 0:
                continue
            try:
                btn.first.click(timeout=3_000)
                return True
            except Exception:
                continue

    # 2) Generic confirm button near common modal containers.
    for sel in (
        ".modal button",
        ".layer button",
        ".popup button",
        "#popup button",
        ".ui-dialog button",
        "[role=dialog] button",
    ):
        buttons = page.locator(sel)
        try:
            count = min(buttons.count(), 8)
        except Exception:
            continue
        for i in range(count):
            btn = buttons.nth(i)
            try:
                if not btn.is_visible():
                    continue
                label = (btn.inner_text() or "").strip()
            except Exception:
                continue
            if label in _CONFIRM_LABELS or _looks_like_conflict_text(label):
                try:
                    btn.click(timeout=3_000)
                    return True
                except Exception:
                    continue
    return False


def login(
    page: Page,
    *,
    user_id: str,
    password: str,
    force_other_session: bool = True,
    login_url: str = LOGIN_URL,
) -> dict:
    """Fill credentials, submit, optionally accept session conflict.

    Returns ``{"conflict_accepted": bool, "url": str, "logged_in": bool}``.
    """
    dialog_messages = _install_dialog_acceptor(page)
    conflict_accepted = False

    if is_logged_in(page):
        return {
            "conflict_accepted": False,
            "url": page.url,
            "logged_in": True,
        }

    if not is_login_url(page.url):
        page.goto(login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

    if is_logged_in(page):
        return {
            "conflict_accepted": False,
            "url": page.url,
            "logged_in": True,
        }

    if not is_login_url(page.url):
        page.goto(login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

    email = page.locator("#email")
    try:
        email.wait_for(state="visible", timeout=30_000)
    except Exception as exc:
        detail = login_diagnostics(page)
        raise LoginPageError(
            f"Login form not found (#email) at {detail.get('url')}",
            detail=detail,
        ) from exc

    email.fill(user_id)
    page.locator("#password").fill(password)
    submit = page.locator("button.btn_member_login")
    if submit.count() == 0:
        submit = page.get_by_role("button", name="로그인")
    if submit.count() == 0:
        page.evaluate("typeof do_login === 'function' && do_login()")
    else:
        submit.first.click()

    page.wait_for_timeout(800)

    if force_other_session:
        if dismiss_session_conflict(page, timeout_ms=5_000):
            conflict_accepted = True
        if dialog_messages:
            # Native confirm/alert was accepted by the dialog handler.
            conflict_accepted = True

    page.wait_for_load_state("domcontentloaded")
    try:
        page.wait_for_url(lambda url: not is_login_url(url), timeout=15_000)
    except Exception:
        if force_other_session:
            if dismiss_session_conflict(page, timeout_ms=2_000):
                conflict_accepted = True
            try:
                page.wait_for_url(lambda url: not is_login_url(url), timeout=15_000)
            except Exception:
                pass

    logged_in = is_logged_in(page)
    if not logged_in and is_login_url(page.url):
        detail = login_diagnostics(page)
        detail["conflict_accepted"] = conflict_accepted
        detail["dialog_messages"] = list(dialog_messages)
        raise LoginPageError(
            f"Login failed; still on {page.url}",
            detail=detail,
        )

    return {
        "conflict_accepted": conflict_accepted,
        "url": page.url,
        "logged_in": logged_in or not is_login_url(page.url),
        "dialog_messages": list(dialog_messages),
    }


def logout(page: Page) -> None:
    """Log out via member/logout (preferred) or the header link."""
    # Direct endpoint is more reliable than clicking chrome that may be
    # covered by banners/modals after login redirect.
    page.goto(
        "https://www.hbrkorea.com/member/logout",
        wait_until="domcontentloaded",
    )
    page.wait_for_timeout(500)
    if not is_logged_in(page):
        return

    link = page.get_by_role("link", name="로그아웃")
    if link.count() == 0:
        link = page.get_by_text("로그아웃", exact=False)
    if link.count() > 0:
        link.first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)
    if is_logged_in(page):
        raise RuntimeError(f"Logout failed; still logged in at {page.url}")
