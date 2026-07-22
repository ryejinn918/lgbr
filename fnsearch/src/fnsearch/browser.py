"""Patchright browser helpers for Fnguide automation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from patchright.sync_api import Browser, Page, sync_playwright

LOGIN_URL = "https://www.fnguide.com/Users/Login"


@contextmanager
def launch_browser(*, headless: bool = False) -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            yield browser
        finally:
            browser.close()


def goto_login(browser: Browser) -> Page:
    page = browser.new_page()
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    return page


def open_login(*, headless: bool = False) -> None:
    """Launch Chromium, open the Fnguide login page, and wait until Enter."""
    with launch_browser(headless=headless) as browser:
        page = goto_login(browser)
        print(f"Opened: {page.url}")
        try:
            input("Press Enter to close the browser...")
        except EOFError:
            page.wait_for_timeout(3000)
