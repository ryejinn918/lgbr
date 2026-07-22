"""Patchright browser helpers tuned to look like a normal Chrome user."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from browserforge.fingerprints import FingerprintGenerator
from patchright.sync_api import Browser, BrowserContext, Page, sync_playwright

LOGIN_URL = "https://www.fnguide.com/Users/Login"
DEFAULT_PROFILE_DIR = Path(".crawler/browser-profile")
ACCEPT_LANGUAGE = "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"

_CHROME_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+|\d+\.\d+\.\d+|\d+)")


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _chrome_version() -> str | None:
    binary = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if not binary:
        return None
    try:
        out = subprocess.check_output([binary, "--version"], text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    match = _CHROME_VERSION_RE.search(out)
    return match.group(1) if match else None


def _human_chrome_user_agent(version: str | None = None) -> str:
    """Headed Chrome UA on Linux so TLS/OS/UA stay in the same family."""
    ver = version or _chrome_version() or "147.0.0.0"
    major = ver.split(".", 1)[0]
    reduced = f"{major}.0.0.0"
    return (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{reduced} Safari/537.36"
    )


def generate_human_fingerprint() -> Any:
    """Browserforge Chrome/Linux/desktop fingerprint (ko-KR)."""
    return FingerprintGenerator(
        browser="chrome",
        os="linux",
        device="desktop",
        locale="ko-KR",
    ).generate()


def human_context_options(fingerprint: Any | None = None) -> dict[str, Any]:
    fingerprint = fingerprint or generate_human_fingerprint()
    return _context_options_from_fingerprint(fingerprint)


def _context_options_from_fingerprint(fingerprint: Any) -> dict[str, Any]:
    # Prefer installed Chrome major version for UA so it lines up with channel=chrome TLS.
    # Browserforge supplies realistic desktop viewport/screen metrics.
    screen = fingerprint.screen
    return {
        "user_agent": _human_chrome_user_agent(),
        "locale": "ko-KR",
        "timezone_id": "Asia/Seoul",
        "viewport": {
            "width": min(int(screen.width), 1920),
            "height": min(int(screen.height), 1080),
        },
        "device_scale_factor": float(getattr(screen, "devicePixelRatio", 1) or 1),
        "color_scheme": "light",
        "extra_http_headers": {"Accept-Language": ACCEPT_LANGUAGE},
    }


def _launch_args() -> list[str]:
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-default-browser-check",
        "--no-first-run",
    ]


@contextmanager
def launch_browser(*, headless: bool | None = None) -> Iterator[Browser]:
    """Launch Chrome (preferred) for callers that still need a Browser object."""
    if headless is None:
        headless = not _has_display()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel="chrome",
            headless=headless,
            args=_launch_args(),
            ignore_default_args=["--enable-automation"],
        )
        try:
            yield browser
        finally:
            browser.close()


@contextmanager
def launch_context(
    *,
    headless: bool | None = None,
    user_data_dir: Path | None = None,
) -> Iterator[BrowserContext]:
    """Launch a human-like Chrome persistent context.

    Follows Patchright guidance (channel=chrome, persistent profile) and uses
    Browserforge for Chrome/Linux UA + locale when headless would otherwise
    advertise HeadlessChrome.
    """
    if headless is None:
        headless = not _has_display()

    profile = user_data_dir or DEFAULT_PROFILE_DIR
    profile.mkdir(parents=True, exist_ok=True)
    fingerprint = generate_human_fingerprint()
    options = _context_options_from_fingerprint(fingerprint)

    # Headed Chrome: avoid forcing a custom viewport/UA when possible.
    # Headless: apply Browserforge-aligned Chrome UA so we don't send HeadlessChrome.
    launch_kwargs: dict[str, Any] = {
        "user_data_dir": str(profile),
        "channel": "chrome",
        "headless": headless,
        "locale": options["locale"],
        "timezone_id": options["timezone_id"],
        "color_scheme": options["color_scheme"],
        "args": _launch_args(),
        "ignore_default_args": ["--enable-automation"],
    }
    if headless:
        # Strip HeadlessChrome advertisement while keeping Linux Chrome identity.
        launch_kwargs["user_agent"] = options["user_agent"]
        launch_kwargs["viewport"] = options["viewport"]
        launch_kwargs["device_scale_factor"] = options["device_scale_factor"]
        launch_kwargs["extra_http_headers"] = options["extra_http_headers"]
    else:
        # Patchright recommendation: headed Chrome + no_viewport, no custom UA.
        launch_kwargs["no_viewport"] = True
        launch_kwargs["extra_http_headers"] = {
            "Accept-Language": ACCEPT_LANGUAGE,
        }

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        try:
            yield context
        finally:
            context.close()


def new_human_context(browser: Browser) -> BrowserContext:
    """Create a non-persistent context with Browserforge Chrome/Linux fingerprint."""
    return browser.new_context(**human_context_options())


def goto_login(browser: Browser) -> Page:
    context = new_human_context(browser)
    page = context.new_page()
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    return page


def open_login(*, headless: bool | None = None) -> None:
    """Launch Chrome, open the Fnguide login page, and wait until Enter."""
    with launch_context(headless=headless) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print(f"Opened: {page.url}")
        print(f"UA: {page.evaluate('() => navigator.userAgent')}")
        try:
            input("Press Enter to close the browser...")
        except EOFError:
            page.wait_for_timeout(3000)
