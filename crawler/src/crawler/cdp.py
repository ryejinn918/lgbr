"""Attach to an open adhoc crawl browser via Chrome DevTools Protocol."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from patchright.sync_api import Browser, Page, sync_playwright

from crawler import crawls_store, sessions_store


# Modes that expose CDP for remote control (FnGuide adhoc + PwC adhoc).
CDP_MODES = frozenset({"adhoc", "pwc"})


def resolve_cdp_endpoint() -> tuple[dict[str, Any], str]:
    crawl = crawls_store.get_open_crawl()
    if not crawl:
        raise RuntimeError("No open crawl")
    mode = str(crawl.get("mode") or "")
    if mode not in CDP_MODES and not crawl.get("debug"):
        raise RuntimeError(
            f"Open crawl mode {mode!r} is not CDP-enabled (need adhoc/pwc/debug)"
        )
    port = crawl.get("cdp_port")
    if not port:
        raise RuntimeError("CDP port not set on crawl yet")
    return crawl, f"http://127.0.0.1:{int(port)}"


@contextmanager
def connect_cdp() -> Iterator[tuple[dict[str, Any], Browser, Page]]:
    crawl, endpoint = resolve_cdp_endpoint()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(endpoint)
        try:
            contexts = browser.contexts
            if not contexts:
                raise RuntimeError("No browser contexts on CDP endpoint")
            pages = contexts[0].pages
            if not pages:
                page = contexts[0].new_page()
            else:
                page = pages[0]
            yield crawl, browser, page
        finally:
            browser.close()


def _touch_after(crawl: dict[str, Any], page: Page, step: str) -> None:
    session_id = crawl.get("session_id")
    if not session_id:
        return
    sessions_store.touch(session_id, current_url=page.url, step=step)


def cdp_status() -> dict[str, Any]:
    with connect_cdp() as (crawl, _browser, page):
        contexts = _browser.contexts
        pages_out = []
        for ctx in contexts:
            for p in ctx.pages:
                pages_out.append({"url": p.url, "title": p.title()})
        _touch_after(crawl, page, "cdp:status")
        return {
            "crawl_id": crawl.get("id"),
            "mode": crawl.get("mode"),
            "cdp_port": crawl.get("cdp_port"),
            "cdp_http_url": crawl.get("cdp_http_url"),
            "active_url": page.url,
            "active_title": page.title(),
            "pages": pages_out,
        }


def cdp_goto(url: str) -> dict[str, Any]:
    with connect_cdp() as (crawl, _browser, page):
        page.goto(url, wait_until="domcontentloaded")
        _touch_after(crawl, page, "cdp:goto")
        return {"url": page.url, "title": page.title()}


def cdp_click(*, text: str | None = None, selector: str | None = None) -> dict[str, Any]:
    if not text and not selector:
        raise ValueError("Provide --text or --selector")
    with connect_cdp() as (crawl, _browser, page):
        if selector:
            page.locator(selector).first.click()
        else:
            page.get_by_text(text or "", exact=False).first.click()
        page.wait_for_load_state("domcontentloaded")
        _touch_after(crawl, page, "cdp:click")
        return {"url": page.url, "title": page.title()}


def cdp_fill(*, selector: str, text: str) -> dict[str, Any]:
    with connect_cdp() as (crawl, _browser, page):
        page.locator(selector).first.fill(text)
        _touch_after(crawl, page, "cdp:fill")
        return {"url": page.url, "selector": selector}


def cdp_press(*, key: str, selector: str | None = None) -> dict[str, Any]:
    with connect_cdp() as (crawl, _browser, page):
        if selector:
            page.locator(selector).first.press(key)
        else:
            page.keyboard.press(key)
        _touch_after(crawl, page, "cdp:press")
        return {"url": page.url, "key": key}


def cdp_screenshot(*, out: Path, full_page: bool = True) -> dict[str, Any]:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with connect_cdp() as (crawl, _browser, page):
        page.screenshot(path=str(out), full_page=full_page)
        _touch_after(crawl, page, "cdp:screenshot")
        return {"url": page.url, "path": str(out.resolve())}


def cdp_eval(expr: str) -> dict[str, Any]:
    with connect_cdp() as (crawl, _browser, page):
        value = page.evaluate(expr)
        _touch_after(crawl, page, "cdp:eval")
        return {"url": page.url, "result": value}
