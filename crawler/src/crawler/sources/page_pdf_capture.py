"""Playwright page.pdf capture for consulting media when no PDF href exists."""

from __future__ import annotations

import re
import shutil
import subprocess
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from patchright.sync_api import BrowserContext, Page

from crawler.browser import launch_context
from crawler.paths import browser_profile_dir

DEFAULT_MIN_BODY_CHARS = 200
DEFAULT_MIN_PDF_BYTES = 20_000
DEFAULT_MIN_PDF_TEXT_CHARS = 120
# Short settle after readiness signals (not the primary wait).
DEFAULT_SETTLE_MS = 300
DEFAULT_NETWORK_IDLE_TIMEOUT_MS = 15_000
DEFAULT_BODY_READY_TIMEOUT_MS = 15_000

# Prefer the longest candidate. `querySelector('article') || …` is wrong on
# pages that put related-content cards in <article> ahead of the real body
# (PwC Global M&A trends / podcasts: first article ≈200 chars, body ≫10k).
_BODY_LEN_JS = """() => {
  const lengths = [];
  for (const sel of ['main', 'article', '[role=main]']) {
    for (const el of document.querySelectorAll(sel)) {
      lengths.push((el.innerText || '').trim().length);
    }
  }
  const body = document.body
    ? (document.body.innerText || '').trim().length
    : 0;
  lengths.push(body);
  return {
    body_len: lengths.length ? Math.max(...lengths) : 0,
    title: (document.title || '').trim(),
  };
}"""

# Prefer specific consent CTAs; bare "Accept" can hit unrelated buttons and
# blank the print layer (seen on EY probes).
_COOKIE_SELECTORS = (
    "#onetrust-accept-btn-handler",
    ".onetrust-accept-btn-handler",
    "#accept-recommended-btn-handler",
    "button:has-text('I accept all cookies')",
    "button:has-text('Accept all cookies')",
    "button:has-text('Accept All Cookies')",
    "button:has-text('Accept all')",
    "button:has-text('Allow all')",
)


class EmptyPagePdfError(RuntimeError):
    """Page body or PDF output too small — treat as no_download / capture_empty."""


def pdf_extract_char_count(path: Path | str, *, max_pages: int = 2) -> int:
    """Return stripped pdftotext length for the first ``max_pages`` pages.

    Returns 0 when the tool is missing, the file is absent, or extraction fails.
    """
    p = Path(path)
    if not p.is_file() or shutil.which("pdftotext") is None:
        return 0
    proc = subprocess.run(
        ["pdftotext", "-f", "1", "-l", str(max_pages), str(p), "-"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return len(re.sub(r"\s+", " ", (proc.stdout or "")).strip())


def _dismiss_cookie_banner(page: Page) -> str | None:
    for sel in _COOKIE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            if not loc.is_visible(timeout=500):
                continue
            loc.click(timeout=2_000)
            return sel
        except Exception:
            continue
    return None


def _wait_for_print_ready(
    page: Page,
    *,
    min_body_chars: int,
    network_idle_timeout_ms: int = DEFAULT_NETWORK_IDLE_TIMEOUT_MS,
    body_ready_timeout_ms: int = DEFAULT_BODY_READY_TIMEOUT_MS,
) -> None:
    """Wait on load signals rather than a fixed sleep.

    EY probes showed DOM ``body_len`` can already be large at 500ms while
    ``page.pdf`` is still blank; network/fonts readiness correlates better.
    """
    try:
        page.wait_for_load_state(
            "networkidle", timeout=max(1, int(network_idle_timeout_ms))
        )
    except Exception:
        pass
    try:
        page.evaluate(
            """async () => {
              if (document.fonts && document.fonts.ready) {
                await document.fonts.ready;
              }
            }"""
        )
    except Exception:
        pass
    try:
        page.wait_for_function(
            """(minLen) => {
              const lengths = [];
              for (const sel of ['main', 'article', '[role=main]']) {
                for (const el of document.querySelectorAll(sel)) {
                  lengths.push((el.innerText || '').trim().length);
                }
              }
              const body = document.body
                ? (document.body.innerText || '').trim().length
                : 0;
              lengths.push(body);
              const n = lengths.length ? Math.max(...lengths) : 0;
              return n >= minLen;
            }""",
            arg=int(min_body_chars),
            timeout=max(1, int(body_ready_timeout_ms)),
        )
    except Exception:
        pass


def capture_url_as_pdf(
    page: Page,
    url: str,
    dest: Path,
    *,
    min_body_chars: int = DEFAULT_MIN_BODY_CHARS,
    min_pdf_bytes: int = DEFAULT_MIN_PDF_BYTES,
    min_pdf_text_chars: int = DEFAULT_MIN_PDF_TEXT_CHARS,
    settle_ms: int = DEFAULT_SETTLE_MS,
    post_load_wait_ms: int | None = None,
    network_idle_timeout_ms: int = DEFAULT_NETWORK_IDLE_TIMEOUT_MS,
    body_ready_timeout_ms: int = DEFAULT_BODY_READY_TIMEOUT_MS,
) -> dict[str, Any]:
    """Open ``url`` and write a print PDF to ``dest``.

    Raises ``EmptyPagePdfError`` when the main content is too short, the
    written PDF is too small, or extractable PDF text is too thin. Other
    failures (navigation, etc.) propagate as ordinary exceptions for
    ``failed`` status.

    ``post_load_wait_ms`` is accepted as a deprecated alias of ``settle_ms``.
    """
    if post_load_wait_ms is not None:
        settle_ms = post_load_wait_ms

    # "load" (not domcontentloaded): resources/fonts more likely settled for print.
    page.goto(url, wait_until="load", timeout=60_000)
    # Dismiss consent early — OneTrust overlays can blank page.pdf print.
    clicked = _dismiss_cookie_banner(page)
    _wait_for_print_ready(
        page,
        min_body_chars=min_body_chars,
        network_idle_timeout_ms=network_idle_timeout_ms,
        body_ready_timeout_ms=body_ready_timeout_ms,
    )
    # Banner sometimes mounts after networkidle; try once more.
    clicked2 = _dismiss_cookie_banner(page)
    if clicked2:
        clicked = clicked or clicked2
        _wait_for_print_ready(
            page,
            min_body_chars=min_body_chars,
            network_idle_timeout_ms=min(5_000, network_idle_timeout_ms),
            body_ready_timeout_ms=min(5_000, body_ready_timeout_ms),
        )
    if settle_ms > 0:
        page.wait_for_timeout(int(settle_ms))

    detail = page.evaluate(_BODY_LEN_JS)
    body_len = int(detail.get("body_len") or 0)
    if body_len < min_body_chars:
        raise EmptyPagePdfError(f"empty body at {url} (len={body_len})")
    dest.parent.mkdir(parents=True, exist_ok=True)
    page.pdf(path=str(dest), format="A4", print_background=True)
    pdf_bytes = dest.stat().st_size if dest.is_file() else 0
    if pdf_bytes < min_pdf_bytes:
        dest.unlink(missing_ok=True)
        raise EmptyPagePdfError(
            f"page.pdf too small: {dest} (bytes={pdf_bytes})"
        )

    pdf_text_len = pdf_extract_char_count(dest)
    if pdf_text_len < min_pdf_text_chars:
        dest.unlink(missing_ok=True)
        raise EmptyPagePdfError(
            f"page.pdf text too thin at {url} (pdf_text_len={pdf_text_len})"
        )

    return {
        "bytes": dest.stat().st_size,
        "body_len": body_len,
        "pdf_text_len": pdf_text_len,
        "title": detail.get("title"),
        "cookie_clicked": clicked,
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
                "pdf_text_len": meta.get("pdf_text_len"),
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
        dest.unlink(missing_ok=True)
        reports_store.mark_status(
            source=source,
            source_key=source_key,
            status=reports_store.STATUS_NO_DOWNLOAD,
            clear_download=True,
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
