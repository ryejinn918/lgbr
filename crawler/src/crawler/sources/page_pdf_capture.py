"""Playwright page.pdf capture for consulting media when no PDF href exists."""

from __future__ import annotations

import shutil
import subprocess
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from patchright.sync_api import BrowserContext, Page

from crawler.browser import launch_context
from crawler.paths import browser_profile_dir


class EmptyPagePdfError(RuntimeError):
    """Page body or PDF output too small — treat as no_download / capture_empty."""


def capture_url_as_pdf(
    page: Page,
    url: str,
    dest: Path,
    *,
    min_body_chars: int = 200,
    min_pdf_bytes: int = 1000,
) -> dict[str, Any]:
    """Open ``url`` and write a print PDF to ``dest``.

    Raises ``EmptyPagePdfError`` when the main content is too short or the
    written PDF is too small. Other failures (navigation, etc.) propagate as
    ordinary exceptions for ``failed`` status.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(500)
    detail = page.evaluate(
        """() => {
          const pick = (sel) => {
            const el = document.querySelector(sel);
            return el ? (el.innerText || '').trim() : '';
          };
          const text =
            pick('main') ||
            pick('article') ||
            pick('[role=main]') ||
            (document.body ? (document.body.innerText || '').trim() : '');
          return {
            body_len: text.length,
            title: (document.title || '').trim(),
          };
        }"""
    )
    body_len = int(detail.get("body_len") or 0)
    if body_len < min_body_chars:
        raise EmptyPagePdfError(f"empty body at {url} (len={body_len})")
    dest.parent.mkdir(parents=True, exist_ok=True)
    page.pdf(path=str(dest), format="A4", print_background=True)
    if not dest.is_file() or dest.stat().st_size < min_pdf_bytes:
        raise EmptyPagePdfError(f"page.pdf too small: {dest}")
    return {
        "bytes": dest.stat().st_size,
        "body_len": body_len,
        "title": detail.get("title"),
    }


def pdf_page_count(path: Path | str) -> int | None:
    """Return page count via pdfinfo, or None if unavailable."""
    p = Path(path)
    if not p.is_file() or shutil.which("pdfinfo") is None:
        return None
    proc = subprocess.run(
        ["pdfinfo", str(p)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    for line in (proc.stdout or "").splitlines():
        if line.lower().startswith("pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


class LazyCaptureBrowser:
    """One Chrome persistent context per search job, opened on first capture."""

    def __init__(
        self,
        source_id: str,
        *,
        downloads_path: Path | None = None,
        headless: bool | None = True,
    ) -> None:
        self.source_id = source_id
        self.downloads_path = downloads_path
        self.headless = headless
        self._stack: ExitStack | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is not None:
            return self._page
        profile = browser_profile_dir(f"browser-profile-{self.source_id}-capture")
        self._stack = ExitStack()
        self._context = self._stack.enter_context(
            launch_context(
                headless=self.headless,
                user_data_dir=profile,
                downloads_path=self.downloads_path,
            )
        )
        self._page = (
            self._context.pages[0]
            if self._context.pages
            else self._context.new_page()
        )
        return self._page

    def close(self) -> None:
        if self._stack is not None:
            try:
                self._stack.close()
            except Exception:
                pass
        self._stack = None
        self._context = None
        self._page = None


def process_no_pdf_with_page_capture(
    *,
    capture: LazyCaptureBrowser,
    source: str,
    source_key: str,
    title: str,
    published_at: Any,
    url: str,
    dest: Path,
    attrs: dict[str, Any],
    already: set[str],
    summary: Any,
    progress: dict[str, Any],
) -> None:
    """When detail has no PDF href: page.pdf → downloaded, or no_download/failed.

    ``summary`` must expose ``downloaded`` (list), ``skipped_no_download``,
    and ``failed`` counters (consulting job summary dataclasses).
    """
    from crawler import reports_store

    try:
        meta = capture_url_as_pdf(capture.page, url, dest)
        pages = pdf_page_count(dest)
        reports_store.mark_downloaded(
            source=source,
            source_key=source_key,
            title=title,
            published_at=published_at,
            page_count=pages,
            file_path=str(dest),
            file_name=dest.name,
            attrs={
                **attrs,
                "no_pdf": True,
                "capture": "page.pdf",
                "bytes": meta["bytes"],
                "body_len": meta.get("body_len"),
            },
        )
        already.add(source_key)
        summary.downloaded.append(str(dest))
        progress["downloaded"] = len(summary.downloaded)
        progress["last_pdf"] = url
        progress["capture"] = "page.pdf"
    except EmptyPagePdfError as exc:
        summary.skipped_no_download += 1
        progress["skipped_no_download"] = summary.skipped_no_download
        reports_store.mark_status(
            source=source,
            source_key=source_key,
            status=reports_store.STATUS_NO_DOWNLOAD,
            attrs={
                **attrs,
                "no_pdf": True,
                "capture_empty": True,
                "error": str(exc),
            },
        )
    except Exception as exc:
        summary.failed += 1
        progress["failed"] = summary.failed
        reports_store.mark_status(
            source=source,
            source_key=source_key,
            status=reports_store.STATUS_FAILED,
            attrs={
                **attrs,
                "no_pdf": True,
                "error": f"page_pdf: {exc}",
            },
        )
